#!/usr/bin/env python3
"""
SQLite database module for storing congressional bill summaries.
Provides functions for database initialization, bill insertion, and duplicate checking.
Enhanced with slug uniqueness, date range queries, and safe connection handling.
"""

import os
import sqlite3
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List, Iterator
from contextlib import contextmanager

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Database file path
DB_PATH = os.path.join(os.path.dirname(__file__), '../../data/bills.db')
DATA_DIR = os.path.join(os.path.dirname(__file__), '../../data')

@contextmanager
def db_connect() -> Iterator[sqlite3.Connection]:
    """
    Context manager that yields a SQLite connection and guarantees it is closed.
    Commits on success and rolls back on failure.
    """
    conn = sqlite3.connect(DB_PATH)
    try:
        yield conn
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        try:
            conn.close()
        except Exception:
            pass

def init_db() -> None:
    """
    Initialize the SQLite database with the bills table.
    Creates the data directory if it doesn't exist.
    """
    try:
        # Create data directory if it doesn't exist
        os.makedirs(DATA_DIR, exist_ok=True)

        with db_connect() as conn:
            cursor = conn.cursor()

            # Enable WAL for better concurrent reads
            cursor.execute("PRAGMA journal_mode=WAL;")
            cursor.execute("PRAGMA synchronous=NORMAL;")

            # Create bills table
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS bills (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bill_id TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL,
                short_title TEXT,
                status TEXT,
                summary_tweet TEXT NOT NULL,
                summary_long TEXT NOT NULL,
                congress_session TEXT,
                date_introduced TEXT,
                date_processed TEXT NOT NULL,
                tweet_posted INTEGER DEFAULT 0,
                tweet_url TEXT,
                source_url TEXT NOT NULL,
                website_slug TEXT,
                tags TEXT,
                poll_results_yes INTEGER DEFAULT 0,
                poll_results_no INTEGER DEFAULT 0
            )
            ''')

            # Indexes for faster lookups
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_bill_id ON bills (bill_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_date_processed ON bills (date_processed)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_website_slug ON bills (website_slug)')

        logger.info(f"Database initialized successfully at {DB_PATH}")

    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise

def bill_exists(bill_id: str) -> bool:
    """
    Check if a bill with the given bill_id already exists in the database.

    Args:
        bill_id: The unique bill identifier from Congress.gov

    Returns:
        bool: True if bill exists, False otherwise
    """
    try:
        with db_connect() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT 1 FROM bills WHERE bill_id = ?', (bill_id,))
            return cursor.fetchone() is not None
    except Exception as e:
        logger.error(f"Error checking if bill exists: {e}")
        return False

def insert_bill(bill_data: Dict[str, Any]) -> bool:
    """
    Insert a new bill record into the database.

    Example:
        >>> bill = {
        ...   "bill_id": "hr5342-119",
        ...   "title": "Commerce, Justice, Science, and Related Agencies Appropriations Act, 2026",
        ...   "short_title": "CJS Appropriations Act 2026",
        ...   "status": "Placed on Union Calendar",
        ...   "summary_tweet": "House bill proposes 2026 funding for Commerce, Justice, Science agencies...",
        ...   "summary_long": "Overview: This bill appropriates funds... Major provisions: ...",
        ...   "congress_session": "119",
        ...   "date_introduced": "2025-07-12",
        ...   "source_url": "https://www.congress.gov/bill/119th-congress/house-bill/5342",
        ...   "website_slug": "hr5342-119-commerce-justice-2026",
        ...   "tags": "appropriations,justice,science",
        ...   "tweet_url": "https://x.com/TeenCivics/status/1234567890",
        ...   "tweet_posted": True
        ... }
        >>> insert_bill(bill)
        True

    Args:
        bill_data: Dictionary containing bill information with the following keys:
        - bill_id: Unique bill identifier (required)
        - title: Full official bill name (required)
        - short_title: Shortened bill name
        - status: Stage in legislative process
        - summary_tweet: AI-generated short summary (required)
        - summary_long: AI-generated long summary (required)
        - congress_session: Congress session info
        - date_introduced: Date bill was introduced
        - source_url: Permalink to Congress.gov (required)
        - website_slug: URL path for website
        - tags: Comma-separated issue categories
        - tweet_url: URL of posted tweet
        - tweet_posted: Boolean indicating if tweeted

    Returns:
        bool: True if insertion successful, False otherwise
    """
    try:
        with db_connect() as conn:
            cursor = conn.cursor()

            # Prepare data for insertion
            current_time = datetime.now().isoformat()

            cursor.execute('''
            INSERT INTO bills (
                bill_id, title, short_title, status, summary_tweet, summary_long,
                congress_session, date_introduced, date_processed, source_url,
                website_slug, tags, tweet_url, tweet_posted
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                bill_data.get('bill_id'),
                bill_data.get('title'),
                bill_data.get('short_title'),
                bill_data.get('status'),
                bill_data.get('summary_tweet'),
                bill_data.get('summary_long'),
                bill_data.get('congress_session'),
                bill_data.get('date_introduced'),
                current_time,
                bill_data.get('source_url'),
                bill_data.get('website_slug'),
                bill_data.get('tags'),
                bill_data.get('tweet_url'),
                1 if bill_data.get('tweet_posted', False) else 0
            ))

        logger.info(f"Successfully inserted bill {bill_data.get('bill_id')}")
        return True

    except sqlite3.IntegrityError:
        logger.warning(f"Bill {bill_data.get('bill_id')} already exists in database")
        return False
    except Exception as e:
        logger.error(f"Error inserting bill: {e}")
        return False

def update_tweet_info(bill_id: str, tweet_url: str) -> bool:
    """
    Update a bill record with tweet information after successful posting.

    Args:
        bill_id: The unique bill identifier
        tweet_url: URL of the posted tweet

    Returns:
        bool: True if update successful, False otherwise
    """
    try:
        with db_connect() as conn:
            cursor = conn.cursor()
            cursor.execute('''
            UPDATE bills
            SET tweet_url = ?, tweet_posted = 1
            WHERE bill_id = ?
            ''', (tweet_url, bill_id))
        logger.info(f"Updated tweet info for bill {bill_id}")
        return True
    except Exception as e:
        logger.error(f"Error updating tweet info: {e}")
        return False

def get_all_bills(limit: int = 100) -> List[Dict[str, Any]]:
    """
    Retrieve all bills from the database, sorted by most recent first.

    Args:
        limit: Maximum number of bills to return

    Returns:
        List of bill dictionaries
    """
    try:
        with db_connect() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('''
            SELECT * FROM bills
            ORDER BY date_processed DESC
            LIMIT ?
            ''', (limit,))
            return [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        logger.error(f"Error retrieving bills: {e}")
        return []

def get_bill_by_id(bill_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve a specific bill by its bill_id.

    Args:
        bill_id: The unique bill identifier

    Returns:
        Bill dictionary if found, None otherwise
    """
    try:
        with db_connect() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM bills WHERE bill_id = ?', (bill_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    except Exception as e:
        logger.error(f"Error retrieving bill {bill_id}: {e}")
        return None

def get_latest_bill() -> Optional[Dict[str, Any]]:
    """
    Retrieve the most recently processed bill (for homepage).

    Returns:
        The latest bill as a dict, or None if none exist.
    """
    try:
        with db_connect() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
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

def get_bill_by_slug(website_slug: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve a bill by its website_slug.

    Args:
        website_slug: The slug used in website URLs (e.g., 'commerce-justice-2026')

    Returns:
        Bill dictionary if found, None otherwise
    """
    try:
        with db_connect() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM bills WHERE website_slug = ?', (website_slug,))
            row = cursor.fetchone()
            return dict(row) if row else None
    except Exception as e:
        logger.error(f"Error retrieving bill with slug {website_slug}: {e}")
        return None

def get_bills_by_date_range(start_date: str, end_date: str) -> List[Dict[str, Any]]:
    """
    Retrieve bills whose date_processed is between start_date and end_date (inclusive).

    Args:
        start_date: ISO8601 date or datetime string (e.g., '2025-09-12' or '2025-09-12T00:00:00')
        end_date: ISO8601 date or datetime string (e.g., '2025-09-13' or '2025-09-13T23:59:59')

    Returns:
        List of bill dictionaries in descending date order.
    """
    try:
        # Normalize pure dates to full-day span
        sd = start_date if 'T' in start_date else f"{start_date}T00:00:00"
        ed = end_date if 'T' in end_date else f"{end_date}T23:59:59"
        with db_connect() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('''
            SELECT * FROM bills
            WHERE date_processed BETWEEN ? AND ?
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
            cursor = conn.cursor()
            cursor.execute('SELECT 1 FROM bills WHERE website_slug = ? LIMIT 1', (slug,))
            return cursor.fetchone() is not None
    except Exception as e:
        logger.error(f"Error checking slug existence for {slug}: {e}")
        return False

def generate_website_slug(title: str, bill_id: str) -> str:
    """
    Generate a URL-friendly slug from the bill title and ID.
    Ensures slug uniqueness by appending bill_id when needed.

    Args:
        title: Bill title
        bill_id: Bill identifier (e.g., 'hr5342-119')

    Returns:
        URL-friendly slug (<=100 chars)
    """
    # Use bill_id as base, ensure hyphens preserved
    base_slug = bill_id.lower().replace('-', ' ')

    # Add key words from title if it's descriptive
    title_words = title.lower().split()
    important_words = [w for w in title_words if len(w) > 3 and w not in {'the', 'and', 'for', 'act', 'bill'}]
    if important_words:
        base_slug += ' ' + ' '.join(important_words[:3])

    # Convert to URL-friendly format
    slug = (
        base_slug
        .replace(' ', '-')
        .replace('/', '-')
        .replace("'", '')
        .replace('"', '')
        .replace('(', '')
        .replace(')', '')
    )

    # Trim length early
    slug = slug[:100]

    # Ensure uniqueness: if slug exists for a different bill, append bill_id
    if _slug_exists(slug):
        # If slug already contains bill_id, return as-is (likely same bill)
        if bill_id.lower() not in slug:
            candidate = f"{slug}-{bill_id.lower()}"
            slug = candidate[:100]
            # If still somehow exists (rare), append short timestamp suffix
            if _slug_exists(slug):
                ts = datetime.now().strftime("%H%M%S")
                slug = f"{slug}-{ts}"[:100]

    return slug

def update_poll_results(bill_id: str, vote_type: str) -> bool:
    """
    Increment poll results counters for a given bill.

    Args:
        bill_id: Unique bill identifier
        vote_type: 'yes' or 'no' (case-insensitive)

    Returns:
        True on success, False otherwise
    """
    vt = (vote_type or '').strip().lower()
    if vt not in {'yes', 'no'}:
        logger.error(f"Invalid vote_type '{vote_type}'. Expected 'yes' or 'no'.")
        return False
    column = 'poll_results_yes' if vt == 'yes' else 'poll_results_no'
    try:
        with db_connect() as conn:
            cursor = conn.cursor()
            cursor.execute(f'''
            UPDATE bills
            SET {column} = COALESCE({column}, 0) + 1
            WHERE bill_id = ?
            ''', (bill_id,))
            if cursor.rowcount == 0:
                logger.error(f"No bill found with id {bill_id} to update poll results")
                return False
        logger.info(f"Incremented {column} for bill {bill_id}")
        return True
    except Exception as e:
        logger.error(f"Error updating poll results for {bill_id}: {e}")
        return False

# Initialize database when module is imported
init_db()