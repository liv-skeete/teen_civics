#!/usr/bin/env python3
"""
Database module for storing congressional bill summaries.
Provides functions for database operations using PostgreSQL.
"""

import os
import logging
import re
from datetime import datetime
from typing import Dict, Any, Optional, List, Iterator
from contextlib import contextmanager

# Import the database connection manager
from .connection import postgres_connect, init_postgres_tables

# Import psycopg2 for PostgreSQL support
import psycopg2
import psycopg2.extras

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

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
    init_postgres_tables()
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
    Return True if the bill exists AND has already been posted to Twitter/X.
    Automatically normalizes the bill_id before querying.

    Args:
        bill_id: The unique bill identifier from Congress.gov

    Returns:
        bool: True if a row exists with tweet_posted = TRUE, False otherwise
    """
    normalized_id = normalize_bill_id(bill_id)
    try:
        with db_connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute('SELECT 1 FROM bills WHERE bill_id = %s AND tweet_posted = TRUE', (normalized_id,))
                return cursor.fetchone() is not None
    except Exception as e:
        logger.error(f"Error checking if bill already posted: {e}")
        return False

def has_posted_today() -> bool:
    """
    Check if any bill has been posted to Twitter/X in the last 24 hours.
    This is used to prevent duplicate posts when running multiple daily scans.
    
    Returns:
        bool: True if a tweet was posted in the last 24 hours, False otherwise
    """
    try:
        with db_connect() as conn:
            with conn.cursor() as cursor:
                # Check for any bills posted in the last 24 hours
                # Using updated_at which is set when tweet_posted is updated to TRUE
                cursor.execute('''
                SELECT 1 FROM bills
                WHERE tweet_posted = TRUE
                AND updated_at >= NOW() - INTERVAL '24 hours'
                LIMIT 1
                ''')
                result = cursor.fetchone() is not None
                if result:
                    logger.info("✅ Found tweet posted in last 24 hours - skipping duplicate post")
                else:
                    logger.info("📭 No tweets posted in last 24 hours - proceeding with scan")
                return result
    except Exception as e:
        logger.error(f"Error checking if posted today: {e}")
        # On error, return False to allow posting (fail open)
        return False

def insert_bill(bill_data: Dict[str, Any]) -> bool:
    """
    Insert a new bill record into the database.
    """
    try:
        with db_connect() as conn:
            with conn.cursor() as cursor:
                current_time = datetime.now().isoformat()
                tweet_posted = bool(bill_data.get('tweet_posted', False))
                website_slug = bill_data.get('website_slug')
                logger.info(f"Inserting bill with slug: {website_slug}")

                cursor.execute('''
                INSERT INTO bills (
                    bill_id, title, short_title, status, summary_tweet, summary_long,
                    summary_overview, summary_detailed, term_dictionary,
                    congress_session, date_introduced, date_processed, source_url,
                    website_slug, tags, tweet_url, tweet_posted,
                    text_source, text_version, text_received_date, processing_attempts, full_text
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ''', (
                    bill_data.get('bill_id'),
                    bill_data.get('title'),
                    bill_data.get('short_title'),
                    bill_data.get('status'),
                    bill_data.get('summary_tweet'),
                    bill_data.get('summary_long'),
                    bill_data.get('summary_overview'),
                    bill_data.get('summary_detailed'),
                    bill_data.get('term_dictionary'),
                    bill_data.get('congress_session'),
                    bill_data.get('date_introduced'),
                    current_time,
                    bill_data.get('source_url'),
                    bill_data.get('website_slug'),
                    bill_data.get('tags'),
                    bill_data.get('tweet_url'),
                    tweet_posted,
                    bill_data.get('text_source', 'feed'),
                    bill_data.get('text_version', 'Introduced'),
                    bill_data.get('text_received_date'),
                    bill_data.get('processing_attempts', 0),
                    bill_data.get('full_text', '')
                ))
        logger.info(f"Successfully inserted bill {bill_data.get('bill_id')}")
        return True
    except Exception as e:
        if 'unique constraint' in str(e).lower() or 'duplicate key' in str(e).lower():
            logger.warning(f"Bill {bill_data.get('bill_id')} already exists in database")
            return False
        logger.error(f"Error inserting bill: {e}")
        return False

def update_tweet_info(bill_id: str, tweet_url: str) -> bool:
    """
    Update a bill record with tweet information after successful posting.
    Also bump date_processed so the website surfaces the newly tweeted bill.
    Automatically normalizes the bill_id before updating.
    
    This operation is atomic and idempotent - will return True if the bill
    is already marked as tweeted with the same tweet_url.
    
    Uses row-level locking to prevent race conditions.
    """
    normalized_id = normalize_bill_id(bill_id)
    try:
        with db_connect() as conn:
            with conn.cursor() as cursor:
                # Use SELECT FOR UPDATE to lock the row and prevent race conditions
                logger.debug(f"Acquiring lock on bill {normalized_id} for tweet update")
                cursor.execute('''
                SELECT tweet_posted, tweet_url FROM bills
                WHERE bill_id = %s
                FOR UPDATE
                ''', (normalized_id,))
                
                result = cursor.fetchone()
                if not result:
                    logger.error(f"Bill {normalized_id} not found in database")
                    return False
                
                current_posted, current_url = result
                
                # Check if already tweeted with same URL (idempotent)
                if current_posted and current_url == tweet_url:
                    logger.info(f"Bill {normalized_id} already tweeted with matching URL (idempotent success)")
                    return True
                
                # Check if already tweeted with different URL (error condition)
                if current_posted and current_url != tweet_url:
                    logger.error(f"Bill {normalized_id} already tweeted with different URL: {current_url} vs {tweet_url}")
                    return False
                
                # Update the bill (we have the lock, so this is safe)
                logger.debug(f"Updating tweet info for bill {normalized_id}")
                cursor.execute('''
                UPDATE bills
                SET tweet_url = %s,
                    tweet_posted = TRUE,
                    date_processed = CURRENT_TIMESTAMP
                WHERE bill_id = %s
                ''', (tweet_url, normalized_id))
                
                if cursor.rowcount == 1:
                    logger.info(f"Successfully updated tweet info for bill {normalized_id}")
                    return True
                else:
                    logger.error(f"Failed to update bill {normalized_id}: no rows affected")
                    return False
                
    except Exception as e:
        logger.error(f"Error updating tweet info for {normalized_id}: {e}")
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

def get_latest_tweeted_bill() -> Optional[Dict[str, Any]]:
    """
    Retrieve the most recently processed bill that has been tweeted (for homepage).
    """
    try:
        with db_connect() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                cursor.execute('''
                SELECT * FROM bills
                WHERE tweet_posted = TRUE
                ORDER BY date_processed DESC
                LIMIT 1
                ''')
                row = cursor.fetchone()
                return dict(row) if row else None
    except Exception as e:
        logger.error(f"Error retrieving latest tweeted bill: {e}")
        return None

def get_all_tweeted_bills(limit: int = 100) -> List[Dict[str, Any]]:
    """
    Retrieve all bills that have been tweeted, sorted by most recent first (for archive).
    """
    try:
        with db_connect() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                cursor.execute('''
                SELECT * FROM bills
                WHERE tweet_posted = TRUE
                ORDER BY date_processed DESC
                LIMIT %s
                ''', (limit,))
                return [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        logger.error(f"Error retrieving tweeted bills: {e}")
        return []

def get_latest_bill() -> Optional[Dict[str, Any]]:
    """
    Retrieve the most recently processed bill (for homepage).
    """
    try:
        with db_connect() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                cursor.execute('''
                SELECT * FROM bills
                ORDER BY date_processed DESC
                LIMIT 1
                ''')
                row = cursor.fetchone()
                return dict(row) if row else None
    except Exception as e:
        logger.error(f"Error retrieving latest bill: {e}")
        return None

def get_most_recent_unposted_bill() -> Optional[Dict[str, Any]]:
    """
    Retrieve the most recently processed bill that has not yet been posted to Twitter.
    """
    try:
        with db_connect() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                cursor.execute('''
                SELECT * FROM bills
                WHERE tweet_posted = FALSE
                AND (problematic IS NULL OR problematic = FALSE)
                ORDER BY date_processed DESC
                LIMIT 1
                ''')
                row = cursor.fetchone()
                return dict(row) if row else None
    except Exception as e:
        logger.error(f"Error retrieving most recent unposted bill: {e}")
        return None
def select_and_lock_unposted_bill() -> Optional[Dict[str, Any]]:
    """
    Atomically select and lock the most recent unposted bill for processing.
    Uses SELECT FOR UPDATE SKIP LOCKED to prevent race conditions when multiple
    processes try to select the same bill.
    
    This ensures that only one process can work on a bill at a time, preventing
    duplicate tweets even if multiple workflow runs execute simultaneously.
    
    Returns:
        Dict with bill data if found, None otherwise
    """
    try:
        with db_connect() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                logger.debug("Attempting to select and lock an unposted bill")
                cursor.execute('''
                SELECT * FROM bills
                WHERE tweet_posted = FALSE
                AND (problematic IS NULL OR problematic = FALSE)
                ORDER BY date_processed DESC
                LIMIT 1
                FOR UPDATE SKIP LOCKED
                ''')
                row = cursor.fetchone()
                if row:
                    bill_data = dict(row)
                    logger.info(f"Successfully locked bill {bill_data['bill_id']} for processing")
                    return bill_data
                else:
                    logger.info("No unposted bills available for locking")
                    return None
    except Exception as e:
        logger.error(f"Error selecting and locking unposted bill: {e}")
        return None


def get_bill_by_slug(website_slug: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve a bill by its website_slug.
    """
    try:
        with db_connect() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                cursor.execute('SELECT * FROM bills WHERE website_slug = %s', (website_slug,))
                row = cursor.fetchone()
                return dict(row) if row else None
    except Exception as e:
        logger.error(f"Error retrieving bill with slug {website_slug}: {e}")
        return None

def get_bills_by_date_range(start_date: str, end_date: str) -> List[Dict[str, Any]]:
    """
    Retrieve bills whose date_processed is between start_date and end_date (inclusive).
    """
    try:
        sd = start_date if 'T' in start_date else f"{start_date}T00:00:00"
        ed = end_date if 'T' in end_date else f"{end_date}T23:59:59"
        
        with db_connect() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                cursor.execute('''
                SELECT * FROM bills
                WHERE date_processed BETWEEN %s AND %s
                ORDER BY date_processed DESC
                ''', (sd, ed))
                return [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        logger.error(f"Error retrieving bills between {start_date} and {end_date}: {e}")
        return []

def _slug_exists(slug: str) -> bool:
    """Return True if a website_slug already exists in the DB."""
    try:
        with db_connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute('SELECT 1 FROM bills WHERE website_slug = %s LIMIT 1', (slug,))
                return cursor.fetchone() is not None
    except Exception as e:
        logger.error(f"Error checking slug existence for {slug}: {e}")
        return False

def generate_website_slug(title: str, bill_id: str) -> str:
    """
    Generate a URL-friendly slug from the bill title and ID.
    """
    base_slug = bill_id.lower().replace('-', ' ')
    title_words = title.lower().split()
    important_words = [w for w in title_words if len(w) > 3 and w not in {'the', 'and', 'for', 'act', 'bill'}]
    if important_words:
        base_slug += ' ' + ' '.join(important_words[:3])

    slug = (
        base_slug
        .replace(' ', '-')
        .replace('/', '-')
        .replace("'", '')
        .replace('"', '')
        .replace('(', '')
        .replace(')', '')
    )
    slug = slug[:100]

    if _slug_exists(slug):
        if bill_id.lower() not in slug:
            candidate = f"{slug}-{bill_id.lower()}"
            slug = candidate[:100]
            if _slug_exists(slug):
                ts = datetime.now().strftime("%H%M%S")
                slug = f"{slug}-{ts}"[:100]
    return slug

def update_poll_results(bill_id: str, vote_type: str, previous_vote: str = None) -> bool:
    """
    Update poll results counters for a given bill, handling vote changes atomically.

    Args:
        bill_id: Unique bill identifier
        vote_type: 'yes', 'no', or 'unsure' (case-insensitive) for the new vote
        previous_vote: Optional 'yes', 'no', or 'unsure' (case-insensitive). If provided and
                       different from vote_type, decrement previous and increment new in one tx.

    Returns:
        True on success (including idempotent no-op), False otherwise
    """
    vt = (vote_type or '').strip().lower()
    if vt not in {'yes', 'no', 'unsure'}:
        logger.error(f"Invalid vote_type '{vote_type}'. Expected 'yes', 'no', or 'unsure'.")
        return False

    pv = (previous_vote or '').strip().lower() if previous_vote else None
    if pv and pv not in {'yes', 'no', 'unsure'}:
        logger.error(f"Invalid previous_vote '{previous_vote}'. Expected 'yes', 'no', or 'unsure'.")
        return False

    if pv and pv == vt:
        logger.info(f"No change for bill {bill_id}: vote remains {vt}")
        return True

    if vt == 'yes':
        new_column = 'poll_results_yes'
    elif vt == 'no':
        new_column = 'poll_results_no'
    else:
        new_column = 'poll_results_unsure'

    prev_column = None
    if pv:
        if pv == 'yes':
            prev_column = 'poll_results_yes'
        elif pv == 'no':
            prev_column = 'poll_results_no'
        else:
            prev_column = 'poll_results_unsure'

    underflow = False
    try:
        with db_connect() as conn:
            with conn.cursor() as cursor:
                if prev_column:
                    cursor.execute(f'''
                    SELECT COALESCE({prev_column}, 0) FROM bills WHERE bill_id = %s
                    ''', (bill_id,))
                    row = cursor.fetchone()
                    if row is None:
                        logger.error(f"No bill found with id {bill_id} to update poll results")
                        return False
                    prev_count = int(row[0] or 0)
                    underflow = prev_count <= 0

                    cursor.execute(f'''
                    UPDATE bills
                    SET {prev_column} = CASE WHEN COALESCE({prev_column}, 0) > 0 THEN COALESCE({prev_column}, 0) - 1 ELSE 0 END,
                        {new_column} = COALESCE({new_column}, 0) + 1
                    WHERE bill_id = %s
                    ''', (bill_id,))
                else:
                    cursor.execute(f'''
                    UPDATE bills
                    SET {new_column} = COALESCE({new_column}, 0) + 1
                    WHERE bill_id = %s
                    ''', (bill_id,))

                if cursor.rowcount == 0:
                    logger.error(f"No bill found with id {bill_id} to update poll results")
                    return False

        if prev_column and underflow:
            logger.warning(f"Vote change underflow for bill {bill_id}: {pv} count was 0; clamped to 0")
        if prev_column:
            logger.info(f"Changed vote for bill {bill_id}: {pv}->{vt}")
        else:
            logger.info(f"Recorded new vote {vt} for bill {bill_id}")
        return True
    except Exception as e:
        logger.error(f"Error updating poll results for {bill_id}: {e}")
        return False

def update_bill_summaries(bill_id: str, summary_overview: str = None,
                         summary_detailed: str = None, term_dictionary: str = None,
                         summary_long: str = None) -> bool:
    """
    Update summary fields for an existing bill.
    """
    try:
        with db_connect() as conn:
            with conn.cursor() as cursor:
                updates = []
                values = []
                
                if summary_overview is not None:
                    updates.append("summary_overview = %s")
                    values.append(summary_overview)
                    
                if summary_detailed is not None:
                    updates.append("summary_detailed = %s")
                    values.append(summary_detailed)
                    
                if term_dictionary is not None:
                    updates.append("term_dictionary = %s")
                    values.append(term_dictionary)
                    
                if summary_long is not None:
                    updates.append("summary_long = %s")
                    values.append(summary_long)
                    
                if not updates:
                    logger.warning(f"No summary fields provided to update for bill {bill_id}")
                    return False
                    
                values.append(bill_id)
                
                cursor.execute(f'''
                UPDATE bills
                SET {", ".join(updates)}
                WHERE bill_id = %s
                ''', values)
                
                if cursor.rowcount == 0:
                    logger.error(f"No bill found with id {bill_id} to update summaries")
                    return False
                    
        logger.info(f"Updated summary fields for bill {bill_id}")
        return True
        
    except Exception as e:
        logger.error(f"Error updating bill summaries for {bill_id}: {e}")
        return False


def mark_bill_as_problematic(bill_id: str, reason: str) -> bool:
    """
    Mark a bill as problematic to prevent it from being selected for processing again.
    This is used when tweet posting or database updates fail to prevent duplicate tweets.
    
    Args:
        bill_id: The bill ID to mark as problematic
        reason: Reason for marking as problematic
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        with db_connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute('''
                UPDATE bills
                SET problematic = TRUE,
                    problem_reason = %s,
                    date_processed = CURRENT_TIMESTAMP
                WHERE bill_id = %s
                ''', (reason, bill_id))
        logger.warning(f"Marked bill {bill_id} as problematic: {reason}")
        return True
    except Exception as e:
        logger.error(f"Error marking bill {bill_id} as problematic: {e}")
        return False
