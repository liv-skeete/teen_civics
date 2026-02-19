#!/usr/bin/env python3
"""
Database module for storing congressional bill summaries.
Provides functions for database operations using PostgreSQL.

TODO: Future improvements (SAVE FOR LATER):
- Add deep retry logic with exponential backoff for database inserts
- Implement connection pooling optimization
- Add database query performance monitoring
"""

import os
import logging
import re
import functools
from datetime import datetime
from typing import Dict, Any, Optional, List, Iterator, Tuple
from contextlib import contextmanager

# Import the database connection manager
from .connection import postgres_connect, init_db_tables

# Import psycopg2 for PostgreSQL support
import psycopg2
import psycopg2.extras

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# ── Simulate mode flag (set by orchestrator when --simulate is used) ────────
_SIMULATE = False


def simulate_safe(fn):
    """Decorator that short-circuits DB write functions when _SIMULATE is True.
    Logs what would have happened and returns True (success) without touching DB."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        if _SIMULATE:
            logger.info(f"🧪 SIMULATE: {fn.__name__}({args!r}, {kwargs!r}) — skipped (read-only)")
            return True
        return fn(*args, **kwargs)
    return wrapper

# Bill ID pattern for exact matching
BILL_ID_REGEX = re.compile(r'^[a-z]+[0-9]+(?:-[0-9]+)?$', re.IGNORECASE)

# Columns needed by the archive page (avoids fetching full_text, fts_vector,
# summary_long, summary_detailed, summary_overview which are large and unused).
ARCHIVE_COLUMNS = (
    "id, bill_id, title, short_title, status, normalized_status, "
    "summary_tweet, congress_session, date_introduced, date_processed, "
    "published, source_url, website_slug, tags, "
    "poll_results_yes, poll_results_no, teen_impact_score, "
    "sponsor_name, sponsor_party, sponsor_state, subject_tags, hidden"
)

# Standard exclusion clause for public queries (excludes soft-deleted bills)
NOT_HIDDEN = "(hidden IS NULL OR hidden = FALSE)"

def get_current_congress() -> str:
    """
    Calculate current Congress session based on date.
    118th Congress: 2023-2024 (Jan 3, 2023 - Jan 3, 2025)
    119th Congress: 2025-2026 (Jan 3, 2025 - Jan 3, 2027)
    Each Congress lasts 2 years starting in odd years.
    """
    year = datetime.now().year
    # 118th Congress started in 2023
    congress = 118 + ((year - 2023) // 2)
    return str(congress)

@contextmanager
def db_connect() -> Iterator[psycopg2.extensions.connection]:
    """
    Context manager that yields a PostgreSQL connection and guarantees it is closed.
    Commits on success and rolls back on failure.
    """
    with postgres_connect() as conn:
        yield conn

def init_db() -> None:
    """
    Initialize the PostgreSQL database with the bills table.
    """
    init_db_tables()
    logger.info("PostgreSQL database initialized successfully")

def bill_exists(bill_id: str) -> bool:
    """
    Check if a bill with the given bill_id already exists in the database.
    Automatically normalizes the bill_id before querying.

    Args:
        bill_id: The unique bill identifier from Congress.gov

    Returns:
        bool: True if bill exists, False otherwise
    """
    normalized_id = normalize_bill_id(bill_id)
    try:
        with db_connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute('SELECT 1 FROM bills WHERE bill_id = %s', (normalized_id,))
                return cursor.fetchone() is not None
    except Exception as e:
        logger.error(f"Error checking if bill exists: {e}")
        return False

def bill_already_posted(bill_id: str) -> bool:
    """
    Return True if the bill exists AND has already been published.
    Automatically normalizes the bill_id before querying.

    Args:
        bill_id: The unique bill identifier from Congress.gov

    Returns:
        bool: True if a row exists with published = TRUE, False otherwise
    """
    normalized_id = normalize_bill_id(bill_id)
    try:
        with db_connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute('SELECT 1 FROM bills WHERE bill_id = %s AND published = TRUE', (normalized_id,))
                return cursor.fetchone() is not None
    except Exception as e:
        logger.error(f"Error checking if bill already posted: {e}")
        return False

def has_posted_today() -> bool:
    """
    Check if any bill has been published in the last 24 hours.
    This is used to prevent duplicate posts when running multiple daily scans.
    
    Returns:
        bool: True if a bill was published in the last 24 hours, False otherwise
    """
    try:
        with db_connect() as conn:
            with conn.cursor() as cursor:
                # Check for any bills published in the last 24 hours
                # Using updated_at which is set when published is updated to TRUE
                cursor.execute('''
                SELECT 1 FROM bills
                WHERE published = TRUE
                AND date_processed >= NOW() - INTERVAL '24 hours'
                LIMIT 1
                ''')
                result = cursor.fetchone() is not None
                if result:
                    logger.info("✅ Found bill published in last 24 hours - skipping duplicate post")
                else:
                    logger.info("📭 No bills published in last 24 hours - proceeding with scan")
                return result
    except Exception as e:
        logger.error(f"Error checking if posted today: {e}")
        # On error, return False to allow posting (fail open)
        return False

@simulate_safe
def insert_bill(bill_data: Dict[str, Any]) -> bool:
    """
    Insert a new bill record into the database.
    Pre-calculates and stores short_title if not provided (deterministic, no external calls).
    """
    try:
        with db_connect() as conn:
            with conn.cursor() as cursor:
                current_time = datetime.now().isoformat()
                published = bool(bill_data.get('published', False))
                website_slug = bill_data.get('website_slug')
                logger.info(f"Inserting bill with slug: {website_slug}")

                # Pre-calc short_title if missing
                short_title = bill_data.get('short_title')
                if not short_title:
                    title_val = bill_data.get('title') or ""
                    if title_val:
                        short_title = deterministic_shorten_title(title_val, 80)
                    else:
                        short_title = None

                cursor.execute('''
                INSERT INTO bills (
                    bill_id, title, short_title, status, summary_tweet, summary_long,
                    summary_overview, summary_detailed,
                    congress_session, date_introduced, date_processed, source_url,
                    website_slug, tags, published, full_text,
                    normalized_status, teen_impact_score,
                    sponsor_name, sponsor_party, sponsor_state,
                    subject_tags
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ''', (
                    bill_data.get('bill_id'),
                    bill_data.get('title'),
                    short_title,
                    bill_data.get('status'),
                    bill_data.get('summary_tweet'),
                    bill_data.get('summary_long'),
                    bill_data.get('summary_overview'),
                    bill_data.get('summary_detailed'),
                    bill_data.get('congress_session'),
                    bill_data.get('date_introduced'),
                    current_time,
                    bill_data.get('source_url'),
                    bill_data.get('website_slug'),
                    bill_data.get('tags'),
                    published,
                    bill_data.get('full_text', ''),
                    bill_data.get('normalized_status'),
                    bill_data.get('teen_impact_score'),
                    bill_data.get('sponsor_name'),
                    bill_data.get('sponsor_party'),
                    bill_data.get('sponsor_state'),
                    bill_data.get('subject_tags')
                ))
        logger.info(f"Successfully inserted bill {bill_data.get('bill_id')}")
        return True
    except Exception as e:
        if 'unique constraint' in str(e).lower() or 'duplicate key' in str(e).lower():
            logger.warning(f"Bill {bill_data.get('bill_id')} already exists in database")
            return False
        logger.error(f"Error inserting bill: {e}")
        return False

@simulate_safe
def update_tweet_info(bill_id: str, tweet_url: str) -> bool:
    """
    Mark a bill as published after successful posting to social platforms.
    Also bumps date_processed so the website surfaces the newly published bill.
    Automatically normalizes the bill_id before updating.
    
    This operation is atomic and idempotent - will return True if the bill
    is already marked as published.
    
    Uses row-level locking to prevent race conditions.
    
    Note: tweet_url parameter is kept for API compat but is no longer stored
    (the tweet_url column has been dropped).
    """
    normalized_id = normalize_bill_id(bill_id)
    try:
        with db_connect() as conn:
            with conn.cursor() as cursor:
                # Use SELECT FOR UPDATE to lock the row and prevent race conditions
                logger.debug(f"Acquiring lock on bill {normalized_id} for publish update")
                cursor.execute('''
                SELECT published FROM bills
                WHERE bill_id = %s
                FOR UPDATE
                ''', (normalized_id,))
                
                result = cursor.fetchone()
                if not result:
                    logger.error(f"Bill {normalized_id} not found in database")
                    return False
                
                current_published = result[0]
                
                # Check if already published (idempotent)
                if current_published:
                    logger.info(f"Bill {normalized_id} already published (idempotent success)")
                    return True
                
                # Update the bill (we have the lock, so this is safe)
                logger.debug(f"Marking bill {normalized_id} as published")
                cursor.execute('''
                UPDATE bills
                SET published = TRUE,
                    date_processed = CURRENT_TIMESTAMP
                WHERE bill_id = %s
                ''', (normalized_id,))
                
                if cursor.rowcount == 1:
                    logger.info(f"Successfully marked bill {normalized_id} as published")
                    return True
                else:
                    logger.error(f"Failed to update bill {normalized_id}: no rows affected")
                    return False
                
    except Exception as e:
        logger.error(f"Error updating publish status for {normalized_id}: {e}")
        return False


def normalize_bill_id(bill_id: str) -> str:
    """
    Normalize bill_id to ensure consistent format across the system.
    Converts to lowercase and ensures it includes congress session suffix.
    
    Args:
        bill_id: Raw bill ID from any source
        
    Returns:
        Normalized bill ID in lowercase with congress suffix
    """
    if not bill_id:
        return bill_id
    
    # Convert to lowercase
    normalized = bill_id.lower()
    
    # Ensure it has the congress suffix format (e.g., "-118")
    if not re.search(r'-\d+$', normalized):
        # Try to extract congress from the bill_id pattern
        match = re.match(r'([a-z]+)(\d+)', normalized)
        if match:
            bill_type, bill_number = match.groups()
            # Use current congress if not specified
            congress = get_current_congress()
            normalized = f"{bill_type}{bill_number}-{congress}"
        else:
            # If pattern doesn't match, just return lowercase
            pass
    
    return normalized

def deterministic_shorten_title(title: str, max_length: int = 80) -> str:
    """
    Deterministic, word-boundary title shortener for pre-calculated storage.
    Never calls external services.
    """
    if not title:
        return ""
    if max_length is None:
        max_length = 80
    if max_length <= 0:
        return title
    if len(title) <= max_length:
        return title
    truncated = title[:max_length]
    last_space = truncated.rfind(" ")
    if last_space != -1 and last_space >= int(max_length * 0.6):
        truncated = truncated[:last_space]
    return truncated.rstrip() + "…"


def get_all_bills(limit: int = 100) -> List[Dict[str, Any]]:
    """
    Retrieve all bills from the database, sorted by most recent first.
    """
    try:
        with db_connect() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                cursor.execute('''
                SELECT * FROM bills
                ORDER BY date_processed DESC
                LIMIT %s
                ''', (limit,))
                return [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        logger.error(f"Error retrieving bills: {e}")
        return []

def search_bills_by_title(title_query: str, limit: int = 100) -> List[Dict[str, Any]]:
    """
    Search all bills by title using LIKE query, sorted by most recent first.
    """
    try:
        with db_connect() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                cursor.execute('''
                SELECT * FROM bills
                WHERE LOWER(COALESCE(title, '')) LIKE %s
                ORDER BY date_processed DESC
                LIMIT %s
                ''', (f'%{title_query.lower()}%', limit,))
                return [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        logger.error(f"Error searching bills by title: {e}")
        return []

def get_bill_by_id(bill_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve a specific bill by its bill_id.
    Automatically normalizes the bill_id before querying.
    """
    normalized_id = normalize_bill_id(bill_id)
    try:
        with db_connect() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                cursor.execute('SELECT * FROM bills WHERE bill_id = %s', (normalized_id,))
                row = cursor.fetchone()
                return dict(row) if row else None
    except Exception as e:
        logger.error(f"Error retrieving bill {normalized_id}: {e}")
        return None

def get_latest_bill() -> Optional[Dict[str, Any]]:
    """
    Retrieve the most recently processed bill (regardless of tweet status).
    This is used as a fallback when no tweeted bills are available.
    Excludes problematic/placeholder bills with empty titles.
    """
    try:
        with db_connect() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                cursor.execute(f'''
                SELECT * FROM bills
                WHERE COALESCE(title, '') != ''
                  AND (problematic IS NULL OR problematic = FALSE)
                  AND {NOT_HIDDEN}
                ORDER BY date_processed DESC
                LIMIT 1
                ''')
                row = cursor.fetchone()
                return dict(row) if row else None
    except Exception as e:
        logger.error(f"Error retrieving latest bill: {e}")
        return None

def get_latest_tweeted_bill() -> Optional[Dict[str, Any]]:
    """
    Retrieve the most recently processed bill that has been published (for homepage).
    """
    try:
        with db_connect() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                cursor.execute(f'''
                SELECT * FROM bills
                WHERE published = TRUE
                  AND {NOT_HIDDEN}
                ORDER BY date_processed DESC
                LIMIT 1
                ''')
                row = cursor.fetchone()
                return dict(row) if row else None
    except Exception as e:
        logger.error(f"Error retrieving latest published bill: {e}")

# Alias for backwards compatibility
get_latest_published_bill = get_latest_tweeted_bill
def get_bill_by_slug(slug: str, include_hidden: bool = False) -> Optional[Dict[str, Any]]:
    """
    Retrieve a specific bill by its website_slug.
    Used for bill detail pages. Hidden bills are excluded by default.
    """
    try:
        with db_connect() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                if include_hidden:
                    cursor.execute('SELECT * FROM bills WHERE website_slug = %s', (slug,))
                else:
                    cursor.execute(f'SELECT * FROM bills WHERE website_slug = %s AND {NOT_HIDDEN}', (slug,))
                row = cursor.fetchone()
                return dict(row) if row else None
    except Exception as e:
        logger.error(f"Error retrieving bill by slug {slug}: {e}")
        return None

@simulate_safe
def update_poll_results(bill_id: str, vote_type: str, previous_vote: Optional[str] = None) -> bool:
    """
    Update poll results for a bill based on user vote.
    
    Args:
        bill_id: The bill identifier
        vote_type: Either 'yes' or 'no'
        previous_vote: The user's previous vote if changing their vote (either 'yes' or 'no')
    
    Returns:
        bool: True if update was successful, False otherwise
    """
    normalized_id = normalize_bill_id(bill_id)
    try:
        with db_connect() as conn:
            with conn.cursor() as cursor:
                # If user is changing their vote, decrement the previous vote count
                if previous_vote:
                    previous_vote_lower = previous_vote.lower()
                    if previous_vote_lower == 'yes':
                        cursor.execute('''
                        UPDATE bills
                        SET poll_results_yes = GREATEST(0, COALESCE(poll_results_yes, 0) - 1)
                        WHERE bill_id = %s
                        ''', (normalized_id,))
                    elif previous_vote_lower == 'no':
                        cursor.execute('''
                        UPDATE bills
                        SET poll_results_no = GREATEST(0, COALESCE(poll_results_no, 0) - 1)
                        WHERE bill_id = %s
                        ''', (normalized_id,))
                
                # Increment the new vote count
                vote_type_lower = vote_type.lower()
                if vote_type_lower == 'yes':
                    cursor.execute('''
                    UPDATE bills
                    SET poll_results_yes = COALESCE(poll_results_yes, 0) + 1
                    WHERE bill_id = %s
                    ''', (normalized_id,))
                elif vote_type_lower == 'no':
                    cursor.execute('''
                    UPDATE bills
                    SET poll_results_no = COALESCE(poll_results_no, 0) + 1
                    WHERE bill_id = %s
                    ''', (normalized_id,))
                else:
                    logger.error(f"Invalid vote_type: {vote_type}")
                    return False
                
                if cursor.rowcount > 0:
                    logger.info(f"Successfully updated poll results for bill {normalized_id}: {vote_type}")
                    return True
                else:
                    logger.warning(f"No bill found with id {normalized_id} to update poll results")
                    return False
                    
    except Exception as e:
        logger.error(f"Error updating poll results for {normalized_id}: {e}")
        return False

def get_all_tweeted_bills(limit: int = 100) -> List[Dict[str, Any]]:
    """
    Retrieve all bills that have been published, sorted by most recent first (for archive).
    """
    try:
        with db_connect() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                cursor.execute(f'''
                SELECT * FROM bills
                WHERE published = TRUE
                  AND {NOT_HIDDEN}
                ORDER BY date_processed DESC
                LIMIT %s
                ''', (limit,))
                return [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        logger.error(f"Error retrieving published bills: {e}")
        return []

# Alias for backwards compatibility
get_all_published_bills = get_all_tweeted_bills

# --- Archive Search Functions ---

def fts_available() -> bool:
    """
    Check if PostgreSQL FTS is available.
    For PostgreSQL, we assume FTS is always available.
    This function is included for API consistency with potential SQLite FTS implementation.
    """
    return True

def parse_search_query(q: str) -> Tuple[List[str], List[str]]:
    """
    Parse search query into phrases (quoted) and tokens.
    """
    phrases = re.findall(r'"([^"]*)"', q)
    # Remove phrases from query to get tokens
    q_no_phrases = re.sub(r'"[^"]*"', '', q)
    tokens = [token for token in q_no_phrases.split() if len(token) >= 2]
    # Limit to first 10 tokens to bound complexity
    return phrases, tokens[:10]

def build_fts_query(phrases: List[str], tokens: List[str]) -> str:
    """
    Build a query string for websearch_to_tsquery.
    """
    # websearch_to_tsquery handles 'OR' and prefixes, so we can join simply.
    # Quoted phrases are treated as single terms.
    query_parts = [f'"{p}"' for p in phrases] + tokens
    return ' '.join(query_parts)

def build_status_filter(status: Optional[str]) -> Tuple[str, Dict[str, Any]]:
    """
    Build SQL WHERE clause and parameters for status filtering.
    """
    if status and status != 'all':
        normalized_status = status.lower().replace(' ', '_')
        # Prioritize normalized_status when it exists, only fall back to legacy status when normalized_status is NULL
        return "AND (normalized_status::text = %(status)s OR (normalized_status IS NULL AND REPLACE(LOWER(COALESCE(status, '')), ' ', '_') = %(status)s))", {'status': normalized_status}
    return "", {}

def build_order_clause(sort_by_impact: bool) -> str:
    """
    Build SQL ORDER BY clause for consistent sorting across all query paths.
    
    When sorting by impact score:
    - NULL/0 values are placed last using CASE expression
    - Non-NULL/non-zero values are sorted by teen_impact_score DESC
    - Tiebreaker is date_processed DESC
    """
    if sort_by_impact:
        return """
        ORDER BY
            CASE WHEN teen_impact_score IS NULL OR teen_impact_score = 0 THEN 1 ELSE 0 END,
            teen_impact_score DESC,
            date_processed DESC
        """
    else:
        return "ORDER BY date_processed DESC"

def parse_date_range_from_query(q: str) -> Tuple[str, Optional[str], Optional[str]]:
    """
    Extract a date range from a free-form query string and return a cleaned query.

    Supported formats (parsed from the existing q box):
      - Exact day:           "October 08, 2025"
      - Month + year:        "October 2025"
      - Year only:           "2025"
      - Month + day:         "October 03" (assumes current year)
      - Month only:          "September" (assumes current year)

    Returns:
      (cleaned_q, start_date_str, end_date_str) where dates are 'YYYY-MM-DD' strings
      or None if no date constraint was found.
    """
    if not q:
        return q, None, None

    now = datetime.now()
    current_year = now.year

    month_map = {
        'january': 1, 'february': 2, 'march': 3, 'april': 4, 'may': 5, 'june': 6,
        'july': 7, 'august': 8, 'september': 9, 'october': 10, 'november': 11, 'december': 12
    }
    month_keys = '|'.join(month_map.keys())

    # Patterns (case-insensitive)
    full_date_re = re.compile(fr'\b({month_keys})\s+(\d{{1,2}}),\s*(\d{{4}})\b', re.IGNORECASE)
    month_year_re = re.compile(fr'\b({month_keys})\s+(\d{{4}})\b', re.IGNORECASE)
    month_day_re = re.compile(fr'\b({month_keys})\s+(\d{{1,2}})\b', re.IGNORECASE)
    month_only_re = re.compile(fr'\b({month_keys})\b', re.IGNORECASE)
    # Numerical date patterns
    numerical_full_date_re = re.compile(r'\b(\d{1,2})/(\d{1,2})/(\d{4})\b')
    numerical_month_day_re = re.compile(r'\b(\d{1,2})/(\d{1,2})\b')
    year_re = re.compile(r'\b(19|20)\d{2}\b')

    # Prefer most specific first
    # Check numerical date patterns first
    m = numerical_full_date_re.search(q)
    if m:
        month_str, day_str, year_str = m.groups()
        year, month, day = int(year_str), int(month_str), int(day_str)
        # Validate date
        try:
            import calendar as _cal
            last_day = _cal.monthrange(year, month)[1]
            day = max(1, min(day, last_day))
            start = f"{year:04d}-{month:02d}-{day:02d}"
            end = start
            cleaned_q = (q[:m.start()] + q[m.end():]).strip()
            return re.sub(r'\s{2,}', ' ', cleaned_q), start, end
        except ValueError:
            pass  # Invalid date, continue to other patterns

    m = numerical_month_day_re.search(q)
    if m:
        month_str, day_str = m.groups()
        year, month, day = current_year, int(month_str), int(day_str)
        # Validate date
        try:
            import calendar as _cal
            last_day = _cal.monthrange(year, month)[1]
            day = max(1, min(day, last_day))
            start = f"{year:04d}-{month:02d}-{day:02d}"
            end = start
            cleaned_q = (q[:m.start()] + q[m.end():]).strip()
            return re.sub(r'\s{2,}', ' ', cleaned_q), start, end
        except ValueError:
            pass  # Invalid date, continue to other patterns

    # Then check text-based patterns
    m = full_date_re.search(q)
    if m:
        month_name, day_str, year_str = m.groups()
        year, month, day = int(year_str), month_map[month_name.lower()], int(day_str)
        import calendar as _cal
        last_day = _cal.monthrange(year, month)[1]
        day = max(1, min(day, last_day))
        start = f"{year:04d}-{month:02d}-{day:02d}"
        end = start
        cleaned_q = (q[:m.start()] + q[m.end():]).strip()
        return re.sub(r'\s{2,}', ' ', cleaned_q), start, end

    m = month_year_re.search(q)
    if m:
        month_name, year_str = m.groups()
        year, month = int(year_str), month_map[month_name.lower()]
        import calendar as _cal
        start = f"{year:04d}-{month:02d}-01"
        last_day = _cal.monthrange(year, month)[1]
        end = f"{year:04d}-{month:02d}-{last_day:02d}"
        cleaned_q = (q[:m.start()] + q[m.end():]).strip()
        return re.sub(r'\s{2,}', ' ', cleaned_q), start, end

    m = month_day_re.search(q)
    if m:
        month_name, day_str = m.groups()
        year, month, day = current_year, month_map[month_name.lower()], int(day_str)
        import calendar as _cal
        last_day = _cal.monthrange(year, month)[1]
        day = max(1, min(day, last_day))
        start = f"{year:04d}-{month:02d}-{day:02d}"
        end = start
        cleaned_q = (q[:m.start()] + q[m.end():]).strip()
        return re.sub(r'\s{2,}', ' ', cleaned_q), start, end

    m = month_only_re.search(q)
    if m:
        month_name = m.group(1).lower()
        year, month = current_year, month_map[month_name]
        import calendar as _cal
        start = f"{year:04d}-{month:02d}-01"
        last_day = _cal.monthrange(year, month)[1]
        end = f"{year:04d}-{month:02d}-{last_day:02d}"
        cleaned_q = (q[:m.start()] + q[m.end():]).strip()
        return re.sub(r'\s{2,}', ' ', cleaned_q), start, end

    m = year_re.search(q)
    if m:
        year = int(m.group(0))
        start = f"{year:04d}-01-01"
        end = f"{year:04d}-12-31"
        cleaned_q = (q[:m.start()] + q[m.end():]).strip()
        return re.sub(r'\s{2,}', ' ', cleaned_q), start, end

    return q, None, None

def build_date_filter(start_date: Optional[str], end_date: Optional[str]) -> Tuple[str, Dict[str, Any]]:
    """
    Build SQL WHERE clause and parameters for introduced-date filtering.

    date_introduced is stored as TEXT; we convert it to DATE by parsing the ISO date
    portion (YYYY-MM-DD) before any 'T' using split_part.
    """
    if not start_date and not end_date:
        return "", {}
    elif start_date and end_date:
        clause = "AND to_date(split_part(date_introduced, 'T', 1), 'YYYY-MM-DD') BETWEEN %(start_date)s AND %(end_date)s"
        return clause, {'start_date': start_date, 'end_date': end_date}
    elif start_date:
        clause = "AND to_date(split_part(date_introduced, 'T', 1), 'YYYY-MM-DD') >= %(start_date)s"
        return clause, {'start_date': start_date}
    elif end_date:
        clause = "AND to_date(split_part(date_introduced, 'T', 1), 'YYYY-MM-DD') <= %(end_date)s"
        return clause, {'end_date': end_date}
    return "", {}

def _search_tweeted_bills_like(
    phrases: List[str], tokens: List[str], status: Optional[str], page: int, page_size: int,
    start_date: Optional[str] = None, end_date: Optional[str] = None, sort_by_impact: bool = False
) -> List[Dict[str, Any]]:
    """
    Fallback search using LIKE queries.
    """
    logger.warning("Performing fallback LIKE search for query.")
    offset = (page - 1) * page_size
    like_terms = phrases + tokens
    if not like_terms:
        return []

    try:
        with db_connect() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                status_clause, params = build_status_filter(status)
                
                # Date filter
                date_clause, date_params = build_date_filter(start_date, end_date)
                params.update(date_params)
                
                like_clauses = []
                for i, term in enumerate(like_terms):
                    param_name = f'term{i}'
                    params[param_name] = f'%{term}%'
                    like_clauses.append(f"""
                        (LOWER(COALESCE(title, '')) LIKE %({param_name})s OR
                         LOWER(COALESCE(summary_long, '')) LIKE %({param_name})s OR
                         LOWER(COALESCE(sponsor_name, '')) LIKE %({param_name})s OR
                         LOWER(COALESCE(subject_tags, '')) LIKE %({param_name})s)
                    """)
                
                full_like_clause = " AND ".join(like_clauses)
                params.update({'limit': page_size, 'offset': offset})

                # Check if status is 'introduced' to adjust the published condition
                published_condition = f"published = TRUE AND {NOT_HIDDEN}" if status != 'introduced' else NOT_HIDDEN

                # Build ORDER BY clause using helper for consistency
                order_clause = build_order_clause(sort_by_impact)

                query = f"""
                    SELECT {ARCHIVE_COLUMNS} FROM bills
                    WHERE {published_condition}
                    AND ({full_like_clause})
                    {status_clause}
                    {date_clause}
                    {order_clause}
                    LIMIT %(limit)s OFFSET %(offset)s
                """
                cursor.execute(query, params)
                return [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        logger.error(f"Error in LIKE search fallback: {e}")
        return []

def search_tweeted_bills(q: str, status: Optional[str], page: int, page_size: int, sort_by_impact: bool = False) -> List[Dict[str, Any]]:
    """
    Search tweeted bills using PostgreSQL FTS with a LIKE fallback.
    Supports date filters embedded in the free-form query:
      - "October 08, 2025" (exact day)
      - "October 2025" (month)
      - "2025" (year)
    Dates filter by date_introduced. Date expressions are stripped from the
    text query before FTS/token parsing.

    When sort_by_impact is True, results are ordered by:
      1) teen_impact_score DESC (NULL/0 last)
      2) date_processed DESC (tiebreaker)
      
    IMPORTANT: Sorting is applied in the database query BEFORE pagination
    to ensure correct ordering across all pages.
    """
    norm_q = q.strip()[:200]
    offset = (page - 1) * page_size

    # If q is empty, fetch all bills (respecting status filter and pagination)
    if not norm_q:
        try:
            with db_connect() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                    status_clause, params = build_status_filter(status)
                    params.update({'limit': page_size, 'offset': offset})
                    # Check if status is 'introduced' to adjust the published condition
                    published_condition = f"published = TRUE AND {NOT_HIDDEN}" if status != 'introduced' else NOT_HIDDEN

                    # Build ORDER BY clause using helper for consistency
                    order_clause = build_order_clause(sort_by_impact)

                    query = f"""
                        SELECT {ARCHIVE_COLUMNS} FROM bills
                        WHERE {published_condition}
                        {status_clause}
                        {order_clause}
                        LIMIT %(limit)s OFFSET %(offset)s
                    """
                    cursor.execute(query, params)
                    return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error fetching all tweeted bills: {e}")
            return []

    # Extract and strip date expressions from query
    cleaned_q, start_date, end_date = parse_date_range_from_query(norm_q)

    # Exact bill ID match fast path (after stripping date expressions)
    if BILL_ID_REGEX.match(cleaned_q):
        try:
            with db_connect() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                    status_clause, params = build_status_filter(status)
                    date_clause, date_params = build_date_filter(start_date, end_date)
                    params.update({'exact_id': cleaned_q.lower(), 'limit': page_size, 'offset': offset})
                    params.update(date_params)
                    # Check if status is 'introduced' to adjust the published condition
                    published_condition = f"published = TRUE AND {NOT_HIDDEN}" if status != 'introduced' else NOT_HIDDEN

                    # Build ORDER BY clause using helper for consistency
                    order_clause = build_order_clause(sort_by_impact)

                    cursor.execute(f"""
                        SELECT {ARCHIVE_COLUMNS} FROM bills
                        WHERE {published_condition}
                        AND LOWER(bill_id) = %(exact_id)s
                        {status_clause}
                        {date_clause}
                        {order_clause}
                        LIMIT %(limit)s OFFSET %(offset)s
                    """, params)
                    return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error in exact bill ID search: {e}")
            return []

    phrases, tokens = parse_search_query(cleaned_q)
    
    # If we have date filters but no text search, return all bills matching the date
    if not phrases and not tokens and start_date:
        try:
            with db_connect() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                    status_clause, params = build_status_filter(status)
                    date_clause, date_params = build_date_filter(start_date, end_date)
                    params.update({'limit': page_size, 'offset': offset})
                    params.update(date_params)
                    # Check if status is 'introduced' to adjust the published condition
                    published_condition = f"published = TRUE AND {NOT_HIDDEN}" if status != 'introduced' else NOT_HIDDEN

                    # Build ORDER BY clause using helper for consistency
                    order_clause = build_order_clause(sort_by_impact)

                    cursor.execute(f"""
                        SELECT {ARCHIVE_COLUMNS} FROM bills
                        WHERE {published_condition}
                        {status_clause}
                        {date_clause}
                        {order_clause}
                        LIMIT %(limit)s OFFSET %(offset)s
                    """, params)
                    return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error in date-only search: {e}")
            return []
    
    if not phrases and not tokens:
        return []

    fts_query_str = build_fts_query(phrases, tokens)

    try:
        with db_connect() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                status_clause, params = build_status_filter(status)
                date_clause, date_params = build_date_filter(start_date, end_date)
                params.update({'fts_query': fts_query_str, 'limit': page_size, 'offset': offset})
                params.update(date_params)
                
                # The tsvector column 'fts_vector' should be created via migration script
                # Check if status is 'introduced' to adjust the published condition
                published_condition = f"published = TRUE AND {NOT_HIDDEN}" if status != 'introduced' else NOT_HIDDEN

                # Build ORDER BY: if sorting by impact, override FTS rank with impact
                # When sorting by impact score, NULL/0 values are placed last
                if sort_by_impact:
                    order_clause = build_order_clause(True)
                else:
                    order_clause = "ORDER BY rank DESC, date_processed DESC"

                query = f"""
                    SELECT {ARCHIVE_COLUMNS}, ts_rank_cd(fts_vector, websearch_to_tsquery('english', %(fts_query)s)) as rank
                    FROM bills
                    WHERE {published_condition}
                    AND fts_vector @@ websearch_to_tsquery('english', %(fts_query)s)
                    {status_clause}
                    {date_clause}
                    {order_clause}
                    LIMIT %(limit)s OFFSET %(offset)s
                """
                cursor.execute(query, params)
                return [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        logger.error(f"FTS search failed: {e}. Falling back to LIKE search.")
        return _search_tweeted_bills_like(phrases, tokens, status, page, page_size, start_date, end_date, sort_by_impact)

def _count_search_tweeted_bills_like(phrases: List[str], tokens: List[str], status: Optional[str],
                                     start_date: Optional[str] = None, end_date: Optional[str] = None) -> int:
    """
    Fallback count using LIKE queries.
    
    Note: This function counts matching records without applying sorting,
    as sorting is only needed when retrieving the actual data for display.
    """
    like_terms = phrases + tokens
    if not like_terms:
        return 0
    try:
        with db_connect() as conn:
            with conn.cursor() as cursor:
                status_clause, params = build_status_filter(status)
                date_clause, date_params = build_date_filter(start_date, end_date)
                params.update(date_params)
                like_clauses = []
                for i, term in enumerate(like_terms):
                    param_name = f'term{i}'
                    params[param_name] = f'%{term}%'
                    like_clauses.append(f"""
                        (LOWER(COALESCE(title, '')) LIKE %({param_name})s OR
                         LOWER(COALESCE(summary_long, '')) LIKE %({param_name})s OR
                         LOWER(COALESCE(sponsor_name, '')) LIKE %({param_name})s OR
                         LOWER(COALESCE(subject_tags, '')) LIKE %({param_name})s)
                    """)
                full_like_clause = " AND ".join(like_clauses)
                # Check if status is 'introduced' to adjust the published condition
                published_condition = f"published = TRUE AND {NOT_HIDDEN}" if status != 'introduced' else NOT_HIDDEN
                query = f"""
                    SELECT COUNT(*) FROM bills
                    WHERE {published_condition} AND ({full_like_clause}) {status_clause} {date_clause}
                """
                cursor.execute(query, params)
                return (cursor.fetchone() or [0])[0]
    except Exception as e:
        logger.error(f"Error in LIKE count fallback: {e}")
        return 0

def count_search_tweeted_bills(q: str, status: Optional[str]) -> int:
    """
    Count total results for a search query.
    Supports date filters embedded in the free-form query (see search_tweeted_bills).
    
    Note: This function counts matching records without applying sorting,
    as sorting is only needed when retrieving the actual data for display.
    """
    norm_q = q.strip()[:200]

    # If q is empty, count all bills (respecting status filter)
    if not norm_q:
        try:
            with db_connect() as conn:
                with conn.cursor() as cursor:
                    status_clause, params = build_status_filter(status)
                    # Check if status is 'introduced' to adjust the published condition
                    published_condition = f"published = TRUE AND {NOT_HIDDEN}" if status != 'introduced' else NOT_HIDDEN
                    query = f"""
                        SELECT COUNT(*) FROM bills
                        WHERE {published_condition}
                        {status_clause}
                    """
                    cursor.execute(query, params)
                    return (cursor.fetchone() or [0])[0]
        except Exception as e:
            logger.error(f"Error counting all tweeted bills: {e}")
            return 0

    cleaned_q, start_date, end_date = parse_date_range_from_query(norm_q)

    # Exact bill ID count fast path (after stripping date expressions)
    if BILL_ID_REGEX.match(cleaned_q):
        try:
            with db_connect() as conn:
                with conn.cursor() as cursor:
                    status_clause, params = build_status_filter(status)
                    date_clause, date_params = build_date_filter(start_date, end_date)
                    params.update({'exact_id': cleaned_q.lower()})
                    params.update(date_params)
                    # Check if status is 'introduced' to adjust the published condition
                    published_condition = f"published = TRUE AND {NOT_HIDDEN}" if status != 'introduced' else NOT_HIDDEN
                    cursor.execute(f"""
                        SELECT COUNT(*) FROM bills
                        WHERE {published_condition}
                        AND LOWER(bill_id) = %(exact_id)s
                        {status_clause}
                        {date_clause}
                    """, params)
                    return (cursor.fetchone() or [0])[0]
        except Exception as e:
            logger.error(f"Error counting exact bill ID matches: {e}")
            return 0

    phrases, tokens = parse_search_query(cleaned_q)
    
    # If we have date filters but no text search, count all bills matching the date
    if not phrases and not tokens and start_date:
        try:
            with db_connect() as conn:
                with conn.cursor() as cursor:
                    status_clause, params = build_status_filter(status)
                    date_clause, date_params = build_date_filter(start_date, end_date)
                    params.update(date_params)
                    # Check if status is 'introduced' to adjust the published condition
                    published_condition = f"published = TRUE AND {NOT_HIDDEN}" if status != 'introduced' else NOT_HIDDEN
                    cursor.execute(f"""
                        SELECT COUNT(*) FROM bills
                        WHERE {published_condition}
                        {status_clause}
                        {date_clause}
                    """, params)
                    return (cursor.fetchone() or [0])[0]
        except Exception as e:
            logger.error(f"Error in date-only count: {e}")
            return 0

    if not phrases and not tokens:
        return 0
    
    fts_query_str = build_fts_query(phrases, tokens)

    try:
        with db_connect() as conn:
            with conn.cursor() as cursor:
                status_clause, params = build_status_filter(status)
                date_clause, date_params = build_date_filter(start_date, end_date)
                params.update({'fts_query': fts_query_str})
                params.update(date_params)
                # Check if status is 'introduced' to adjust the published condition
                published_condition = f"published = TRUE AND {NOT_HIDDEN}" if status != 'introduced' else NOT_HIDDEN
                query = f"""
                    SELECT COUNT(*) FROM bills
                    WHERE {published_condition}
                    AND fts_vector @@ websearch_to_tsquery('english', %(fts_query)s)
                    {status_clause}
                    {date_clause}
                """
                cursor.execute(query, params)
                return (cursor.fetchone() or [0])[0]
    except Exception as e:
        logger.error(f"FTS count failed: {e}. Falling back to LIKE count.")
        return _count_search_tweeted_bills_like(phrases, tokens, status, start_date, end_date)


def search_and_count_bills(
    q: str, status: Optional[str], page: int, page_size: int, sort_by_impact: bool = False
) -> Tuple[List[Dict[str, Any]], int]:
    """
    Combined search + count in a single database connection.
    Eliminates the overhead of acquiring a second connection for the count query.

    Returns:
        (bills_list, total_count) tuple
    """
    norm_q = q.strip()[:200]
    offset = (page - 1) * page_size

    # Build shared filter components once
    status_clause, base_params = build_status_filter(status)
    published_condition = f"published = TRUE AND {NOT_HIDDEN}" if status != 'introduced' else NOT_HIDDEN
    order_clause = build_order_clause(sort_by_impact)

    # Extract date range from query
    cleaned_q, start_date, end_date = parse_date_range_from_query(norm_q) if norm_q else (norm_q, None, None)
    date_clause, date_params = build_date_filter(start_date, end_date) if norm_q else ("", {})

    try:
        with db_connect() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                # --- Determine query strategy ---

                if not norm_q:
                    # Empty query: browse all bills
                    search_params = dict(base_params, limit=page_size, offset=offset)
                    count_params = dict(base_params)

                    search_sql = f"""
                        SELECT {ARCHIVE_COLUMNS} FROM bills
                        WHERE {published_condition} {status_clause}
                        {order_clause}
                        LIMIT %(limit)s OFFSET %(offset)s
                    """
                    count_sql = f"""
                        SELECT COUNT(*) FROM bills
                        WHERE {published_condition} {status_clause}
                    """

                elif BILL_ID_REGEX.match(cleaned_q):
                    # Exact bill ID match
                    search_params = dict(base_params, **date_params,
                                         exact_id=cleaned_q.lower(), limit=page_size, offset=offset)
                    count_params = dict(base_params, **date_params, exact_id=cleaned_q.lower())

                    search_sql = f"""
                        SELECT {ARCHIVE_COLUMNS} FROM bills
                        WHERE {published_condition}
                        AND LOWER(bill_id) = %(exact_id)s
                        {status_clause} {date_clause}
                        {order_clause}
                        LIMIT %(limit)s OFFSET %(offset)s
                    """
                    count_sql = f"""
                        SELECT COUNT(*) FROM bills
                        WHERE {published_condition}
                        AND LOWER(bill_id) = %(exact_id)s
                        {status_clause} {date_clause}
                    """

                else:
                    phrases, tokens = parse_search_query(cleaned_q)

                    if not phrases and not tokens and start_date:
                        # Date-only filter
                        search_params = dict(base_params, **date_params,
                                             limit=page_size, offset=offset)
                        count_params = dict(base_params, **date_params)

                        search_sql = f"""
                            SELECT {ARCHIVE_COLUMNS} FROM bills
                            WHERE {published_condition}
                            {status_clause} {date_clause}
                            {order_clause}
                            LIMIT %(limit)s OFFSET %(offset)s
                        """
                        count_sql = f"""
                            SELECT COUNT(*) FROM bills
                            WHERE {published_condition}
                            {status_clause} {date_clause}
                        """

                    elif not phrases and not tokens:
                        return [], 0

                    else:
                        # FTS search
                        fts_query_str = build_fts_query(phrases, tokens)
                        fts_order = order_clause if sort_by_impact else "ORDER BY rank DESC, date_processed DESC"

                        search_params = dict(base_params, **date_params,
                                             fts_query=fts_query_str, limit=page_size, offset=offset)
                        count_params = dict(base_params, **date_params, fts_query=fts_query_str)

                        search_sql = f"""
                            SELECT {ARCHIVE_COLUMNS},
                                   ts_rank_cd(fts_vector, websearch_to_tsquery('english', %(fts_query)s)) as rank
                            FROM bills
                            WHERE {published_condition}
                            AND fts_vector @@ websearch_to_tsquery('english', %(fts_query)s)
                            {status_clause} {date_clause}
                            {fts_order}
                            LIMIT %(limit)s OFFSET %(offset)s
                        """
                        count_sql = f"""
                            SELECT COUNT(*) FROM bills
                            WHERE {published_condition}
                            AND fts_vector @@ websearch_to_tsquery('english', %(fts_query)s)
                            {status_clause} {date_clause}
                        """

                # Execute both queries on the same connection
                cursor.execute(search_sql, search_params)
                bills = [dict(row) for row in cursor.fetchall()]

                cursor.execute(count_sql, count_params)
                total = (cursor.fetchone() or [0])[0]

                return bills, total

    except Exception as e:
        logger.error(f"search_and_count_bills failed: {e}", exc_info=True)
        # Fall back to the two separate calls
        try:
            bills = search_tweeted_bills(q, status, page, page_size, sort_by_impact)
            total = count_search_tweeted_bills(q, status)
            return bills, total
        except Exception as fallback_err:
            logger.error(f"Fallback also failed: {fallback_err}")
            return [], 0


def select_and_lock_unposted_bill() -> Optional[Dict[str, Any]]:
    """
    Atomically select and lock one unposted bill to prevent race conditions.
    Uses 'SELECT FOR UPDATE SKIP LOCKED' to ensure that concurrent workers
    do not select the same bill.
    
    Returns:
        A dictionary representing the locked bill, or None if no bills are available.
    """
    try:
        with db_connect() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                # This query finds the most recently introduced bill that has not been
                # posted, is not marked as problematic, and locks it.
                # If the row is already locked, SKIP LOCKED ensures we don't wait.
                cursor.execute('''
                    SELECT * FROM bills
                    WHERE published = FALSE
                    AND (problematic IS NULL OR problematic = FALSE)
                    ORDER BY date_introduced DESC
                    LIMIT 1
                    FOR UPDATE SKIP LOCKED
                ''')
                row = cursor.fetchone()
                if row:
                    logger.info(f"Locked bill for processing: {row['bill_id']}")
                    return dict(row)
                else:
                    logger.info("No unposted bills available to lock.")
                    return None
    except Exception as e:
        logger.error(f"Error selecting and locking unposted bill: {e}")
        return None

def get_unposted_count() -> int:
    """Return the number of non-problematic, unpublished bills in the DB."""
    try:
        with db_connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute('''
                    SELECT COUNT(*) FROM bills
                    WHERE published = FALSE
                    AND (problematic IS NULL OR problematic = FALSE)
                ''')
                return cursor.fetchone()[0]
    except Exception as e:
        logger.error(f"Error counting unposted bills: {e}")
        return 0


def get_problematic_count() -> int:
    """Return the total number of bills marked problematic."""
    try:
        with db_connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) FROM bills WHERE problematic = TRUE")
                return cursor.fetchone()[0]
    except Exception as e:
        logger.error(f"Error counting problematic bills: {e}")
        return 0


def generate_website_slug(title: str, bill_id: str) -> str:
    """
    Generate a URL-friendly slug from a bill title and ID.
    
    Args:
        title: The title of the bill.
        bill_id: The unique ID of the bill (e.g., 'hr123-118').
        
    Returns:
        A URL-friendly slug string.
    """
    if not title:
        # Fallback to bill_id if title is empty
        return normalize_bill_id(bill_id)

    # Normalize, remove special characters, and truncate
    s = title.lower()
    s = re.sub(r'[^\w\s-]', '', s)
    s = re.sub(r'[\s_-]+', '-', s).strip('-')
    s = s[:80] # Truncate to 80 chars

    # Append normalized bill_id to ensure uniqueness
    normalized_id = normalize_bill_id(bill_id)
    
    # Clean up the bill_id part for the slug
    slug_id = normalized_id.replace('-', '')
    
    return f"{s}-{slug_id}"




@simulate_safe
def mark_bill_as_problematic(bill_id: str, reason: str) -> bool:
    """
    Mark a bill as problematic to prevent it from being processed again.

    Sets ``problematic_marked_at`` to the current timestamp so the 15-day
    recheck delay can be calculated later.  Does NOT reset ``recheck_attempted``
    — once a recheck has been attempted, the bill stays locked out.

    Behavior:
      - UPDATE if the bill exists.
      - If no rows updated, UPSERT a minimal placeholder row marked problematic.
    """
    normalized_id = normalize_bill_id(bill_id)
    try:
        with db_connect() as conn:
            with conn.cursor() as cursor:
                # Try to update first
                cursor.execute(
                    '''
                    UPDATE bills
                    SET problematic = TRUE,
                        problem_reason = %s,
                        problematic_marked_at = COALESCE(problematic_marked_at, CURRENT_TIMESTAMP)
                    WHERE bill_id = %s
                    ''',
                    (reason, normalized_id)
                )
                if cursor.rowcount == 1:
                    logger.info(f"Successfully marked bill {normalized_id} as problematic.")
                    return True

                # If no existing row, insert minimal placeholder and mark problematic (UPSERT)
                logger.info(f"Bill {normalized_id} not found; inserting minimal placeholder and marking problematic.")
                title = ""
                summary_tweet = ""
                summary_long = ""
                status = "problematic"
                source_url = ""
                website_slug = generate_website_slug(title, normalized_id)

                cursor.execute(
                    '''
                    INSERT INTO bills (
                        bill_id, title, summary_tweet, summary_long, status,
                        date_processed, source_url, website_slug, problematic,
                        problem_reason, problematic_marked_at, published
                    )
                    VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP, %s, %s, TRUE, %s, CURRENT_TIMESTAMP, FALSE)
                    ON CONFLICT (bill_id)
                    DO UPDATE SET
                        problematic = EXCLUDED.problematic,
                        problem_reason = EXCLUDED.problem_reason,
                        problematic_marked_at = COALESCE(bills.problematic_marked_at, CURRENT_TIMESTAMP),
                        updated_at = CURRENT_TIMESTAMP
                    ''',
                    (normalized_id, title, summary_tweet, summary_long, status, source_url, website_slug, reason)
                )
                logger.info(f"Upserted problematic bill {normalized_id}.")
                return True
    except Exception as e:
        logger.error(f"Error marking bill {normalized_id} as problematic: {e}")
        return False


# Duplicate mark_bill_as_problematic removed (merged into single implementation above)


def get_all_problematic_bills(limit: int = 50) -> List[Dict[str, Any]]:
    """
    Retrieve problematic bills that are eligible for a single recheck.

    Eligibility rules:
      - ``problematic = TRUE``
      - ``recheck_attempted`` is FALSE (or NULL) — only one recheck allowed
      - ``problematic_marked_at`` is at least 15 days ago

    Bills that have already been rechecked (``recheck_attempted = TRUE``) are
    permanently locked out until manually cleared.

    Args:
        limit: Maximum number of problematic bills to return.

    Returns:
        List of bill dictionaries ordered by problematic_marked_at ASC
        (oldest first, so the longest-waiting bills get rechecked first).
    """
    try:
        with db_connect() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                cursor.execute('''
                    SELECT * FROM bills
                    WHERE problematic = TRUE
                      AND (recheck_attempted IS NULL OR recheck_attempted = FALSE)
                      AND problematic_marked_at IS NOT NULL
                      AND problematic_marked_at <= NOW() - INTERVAL '15 days'
                    ORDER BY problematic_marked_at ASC
                    LIMIT %s
                ''', (limit,))
                return [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        logger.error(f"Error retrieving problematic bills: {e}")
        return []


@simulate_safe
def unmark_bill_as_problematic(bill_id: str) -> bool:
    """
    Clear the problematic flag on a bill so it becomes eligible for processing again.
    Also resets the recheck-tracking fields so the bill starts fresh.

    Args:
        bill_id: The bill identifier (will be normalized).

    Returns:
        True if the update succeeded, False otherwise.
    """
    normalized_id = normalize_bill_id(bill_id)
    try:
        with db_connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute('''
                    UPDATE bills
                    SET problematic = FALSE,
                        problem_reason = NULL,
                        problematic_marked_at = NULL,
                        recheck_attempted = FALSE
                    WHERE bill_id = %s
                ''', (normalized_id,))
                if cursor.rowcount == 1:
                    logger.info(f"Unmarked bill {normalized_id} as no longer problematic.")
                    return True
                else:
                    logger.warning(f"Could not find bill {normalized_id} to unmark.")
                    return False
    except Exception as e:
        logger.error(f"Error unmarking bill {normalized_id} as non-problematic: {e}")
        return False


@simulate_safe
def mark_recheck_attempted(bill_id: str) -> bool:
    """
    Record that the single allowed recheck has been performed for a
    problematic bill.  After this, the bill is permanently locked out
    from future automatic rechecks (``recheck_attempted = TRUE``).

    Args:
        bill_id: The bill identifier (will be normalized).

    Returns:
        True if the update succeeded, False otherwise.
    """
    normalized_id = normalize_bill_id(bill_id)
    try:
        with db_connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute('''
                    UPDATE bills
                    SET recheck_attempted = TRUE
                    WHERE bill_id = %s
                ''', (normalized_id,))
                if cursor.rowcount == 1:
                    logger.info(f"Marked recheck_attempted=TRUE for bill {normalized_id}.")
                    return True
                else:
                    logger.warning(f"Could not find bill {normalized_id} to mark recheck_attempted.")
                    return False
    except Exception as e:
        logger.error(f"Error marking recheck_attempted for bill {normalized_id}: {e}")
        return False


@simulate_safe
def update_bill_title(bill_id: str, title: str) -> bool:
    """
    Update the title (and recalculated short_title) for a specific bill.

    Args:
        bill_id: The bill identifier (will be normalized).
        title: The new title string.

    Returns:
        True if the update succeeded, False otherwise.
    """
    normalized_id = normalize_bill_id(bill_id)
    short_title = deterministic_shorten_title(title, 80) if title else None
    try:
        with db_connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute('''
                    UPDATE bills
                    SET title = %s,
                        short_title = %s
                    WHERE bill_id = %s
                ''', (title, short_title, normalized_id))
                if cursor.rowcount == 1:
                    logger.info(f"Updated title for bill {normalized_id}")
                    return True
                else:
                    logger.warning(f"Could not find bill {normalized_id} to update title.")
                    return False
    except Exception as e:
        logger.error(f"Error updating title for bill {normalized_id}: {e}")
        return False


@simulate_safe
def update_bill_summaries(bill_id: str, overview: str, detailed: str, tweet: str, term_dictionary: str = "", subject_tags: str = "") -> bool:
    """
    Update the summaries for a specific bill.
    Note: term_dictionary parameter is kept for API compat but is no longer stored.
    """
    normalized_id = normalize_bill_id(bill_id)
    try:
        with db_connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute('''
                UPDATE bills
                SET summary_overview = %s,
                    summary_detailed = %s,
                    summary_tweet = %s,
                    subject_tags = %s
                WHERE bill_id = %s
                ''', (overview, detailed, tweet, subject_tags, normalized_id))
                if cursor.rowcount == 1:
                    logger.info(f"Successfully updated summaries for bill {normalized_id}")
                    return True
                else:
                    logger.warning(f"Could not find bill {normalized_id} to update summaries.")
                    return False
    except Exception as e:
        logger.error(f"Error updating summaries for bill {normalized_id}: {e}")
        return False

@simulate_safe
def update_bill_full_text(bill_id: str, full_text: str, text_format: str = "") -> bool:
    """
    Update the full text for a specific bill.
    Note: text_format parameter is kept for API compat but is no longer stored.
    """
    normalized_id = normalize_bill_id(bill_id)
    try:
        with db_connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute('''
                UPDATE bills
                SET full_text = %s
                WHERE bill_id = %s
                ''', (full_text, normalized_id))
                if cursor.rowcount == 1:
                    logger.info(f"Successfully updated full text for bill {normalized_id}")
                    return True
                else:
                    logger.warning(f"Could not find bill {normalized_id} to update full text.")
                    return False
    except Exception as e:
        logger.error(f"Error updating full text for bill {normalized_id}: {e}")
        return False
@simulate_safe
def update_bill_teen_impact_score(bill_id: str, teen_impact_score: int) -> bool:
    """
    Update the teen impact score for a specific bill.
    """
    normalized_id = normalize_bill_id(bill_id)
    try:
        with db_connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE bills
                    SET teen_impact_score = %s
                    WHERE bill_id = %s
                    """,
                    (teen_impact_score, normalized_id),
                )
                return cursor.rowcount > 0
    except Exception as e:
        logger.error(f"Error updating teen impact score for bill {normalized_id}: {e}")
        return False


@simulate_safe
def update_bill_sponsor(bill_id: str, sponsor_name: str, sponsor_party: str, sponsor_state: str) -> bool:
    """
    Update the sponsor information for a specific bill.
    Used by the backfill script to populate sponsor data for existing bills.
    
    Args:
        bill_id: The bill identifier (e.g., 'hr1234-119')
        sponsor_name: Full name of the primary sponsor
        sponsor_party: Party affiliation (D, R, I, etc.)
        sponsor_state: State represented (CA, TX, NY, etc.)
    
    Returns:
        bool: True if update succeeded, False otherwise
    """
    normalized_id = normalize_bill_id(bill_id)
    try:
        with db_connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE bills
                    SET sponsor_name = %s,
                        sponsor_party = %s,
                        sponsor_state = %s
                    WHERE bill_id = %s
                    """,
                    (sponsor_name, sponsor_party, sponsor_state, normalized_id),
                )
                return cursor.rowcount > 0
    except Exception as e:
        logger.error(f"Error updating sponsor for bill {normalized_id}: {e}")
        return False


def get_bills_without_sponsor(limit: int = 100) -> List[Dict[str, Any]]:
    """
    Get bills that don't have sponsor information populated.
    Used by the backfill script to find bills that need sponsor data.
    
    Args:
        limit: Maximum number of bills to return
    
    Returns:
        List of bill dictionaries with bill_id and congress_session
    """
    try:
        with db_connect() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                cursor.execute(
                    """
                    SELECT bill_id, congress_session
                    FROM bills
                    WHERE sponsor_name IS NULL OR sponsor_name = ''
                    ORDER BY date_processed DESC
                    LIMIT %s
                    """,
                    (limit,),
                )
                return [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        logger.error(f"Error getting bills without sponsor: {e}")
        return []


def record_individual_vote(voter_id: str, bill_id: str, vote_type: str) -> bool:
    """
    Record an individual vote for a voter on a bill.
    Uses INSERT ON CONFLICT UPDATE (upsert) so that if the voter already voted
    on this bill, the vote_type and updated_at are updated.

    Args:
        voter_id: UUID string identifying the voter (from cookie)
        bill_id: The bill identifier
        vote_type: Either 'yes', 'no', or 'unsure'

    Returns:
        bool: True if the vote was recorded successfully, False otherwise
    """
    try:
        with db_connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute('''
                INSERT INTO votes (voter_id, bill_id, vote_type)
                VALUES (%s, %s, %s)
                ON CONFLICT (voter_id, bill_id)
                DO UPDATE SET
                    vote_type = EXCLUDED.vote_type,
                    updated_at = CURRENT_TIMESTAMP
                ''', (voter_id, bill_id, vote_type))
                logger.info(f"Recorded vote for voter {voter_id[:8]}... on bill {bill_id}: {vote_type}")
                return True
    except Exception as e:
        logger.error(f"Error recording individual vote for voter {voter_id[:8]}... on bill {bill_id}: {e}")
        return False


def record_vote_and_update_poll(
    bill_id: str, vote_type: str, voter_id: str, previous_vote: Optional[str] = None
) -> bool:
    """
    Combined operation: update poll aggregates AND record individual vote
    in a single database connection. Eliminates the overhead of acquiring
    two separate connections.

    Args:
        bill_id: The bill identifier
        vote_type: 'yes', 'no', or 'unsure'
        voter_id: UUID string identifying the voter
        previous_vote: The user's previous vote if changing ('yes' or 'no')

    Returns:
        bool: True if the poll update succeeded, False otherwise
    """
    normalized_id = normalize_bill_id(bill_id)
    try:
        with db_connect() as conn:
            with conn.cursor() as cursor:
                # 1) Decrement previous vote if changing
                if previous_vote:
                    prev = previous_vote.lower()
                    if prev == 'yes':
                        cursor.execute(
                            'UPDATE bills SET poll_results_yes = GREATEST(0, COALESCE(poll_results_yes, 0) - 1) WHERE bill_id = %s',
                            (normalized_id,),
                        )
                    elif prev == 'no':
                        cursor.execute(
                            'UPDATE bills SET poll_results_no = GREATEST(0, COALESCE(poll_results_no, 0) - 1) WHERE bill_id = %s',
                            (normalized_id,),
                        )

                # 2) Increment new vote
                vt = vote_type.lower()
                if vt == 'yes':
                    cursor.execute(
                        'UPDATE bills SET poll_results_yes = COALESCE(poll_results_yes, 0) + 1 WHERE bill_id = %s',
                        (normalized_id,),
                    )
                elif vt == 'no':
                    cursor.execute(
                        'UPDATE bills SET poll_results_no = COALESCE(poll_results_no, 0) + 1 WHERE bill_id = %s',
                        (normalized_id,),
                    )
                elif vt != 'unsure':
                    logger.error(f"Invalid vote_type: {vote_type}")
                    return False

                if cursor.rowcount == 0:
                    logger.warning(f"No bill found with id {normalized_id} to update poll results")
                    return False

                # 3) Record individual vote (same connection, same transaction)
                cursor.execute('''
                INSERT INTO votes (voter_id, bill_id, vote_type)
                VALUES (%s, %s, %s)
                ON CONFLICT (voter_id, bill_id)
                DO UPDATE SET
                    vote_type = EXCLUDED.vote_type,
                    updated_at = CURRENT_TIMESTAMP
                ''', (voter_id, bill_id, vote_type))

                logger.info(f"Recorded vote + poll update for voter {voter_id[:8]}... on bill {normalized_id}: {vote_type}")
                return True
    except Exception as e:
        logger.error(f"Error in record_vote_and_update_poll for {normalized_id}: {e}")
        return False


def get_voter_votes(voter_id: str) -> List[Dict[str, str]]:
    """
    Retrieve all vote records for a given voter_id.

    Args:
        voter_id: UUID string identifying the voter (from cookie)

    Returns:
        List of dicts like [{"bill_id": "hr1234", "vote_type": "yes"}, ...]
    """
    try:
        with db_connect() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                cursor.execute('''
                SELECT bill_id, vote_type
                FROM votes
                WHERE voter_id = %s
                ORDER BY updated_at DESC
                ''', (voter_id,))
                return [{"bill_id": row["bill_id"], "vote_type": row["vote_type"]} for row in cursor.fetchall()]
    except Exception as e:
        logger.error(f"Error retrieving votes for voter {voter_id[:8]}...: {e}")
        return []
