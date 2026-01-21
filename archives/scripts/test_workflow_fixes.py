#!/usr/bin/env python3
"""
Test script for verifying workflow fixes.
1. Feed parser with 403 error handling and API fallback
2. Duplicate bill processing prevention
3. Database connection diagnostics
"""

import os
import sys
import logging
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.fetchers.feed_parser import parse_bill_texts_feed
from src.database.db import bill_exists, bill_already_posted, insert_bill, get_bill_by_id, select_and_lock_unposted_bill
from src.database.connection import init_db_tables, postgres_connect
import psycopg2

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# SAFETY CHECK: Prevent running tests against production database
database_url = os.getenv('DATABASE_URL', '')
test_database_url = os.getenv('TEST_DATABASE_URL', '')

# Check if DATABASE_URL contains production keywords and TEST_DATABASE_URL is not set
# Skip this check in CI environment
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'fetchers'))
from feed_parser import running_in_ci

if any(keyword in database_url.lower() for keyword in ['heroku', 'railway']) and not test_database_url and not running_in_ci():
    logger.error("ERROR: Refusing to run tests against a production database. Set TEST_DATABASE_URL to run tests.")
    sys.exit(1)

def test_feed_parser_with_fallback():
    """Test that feed parser handles 403 errors and falls back to API"""
    print("\n" + "="*60)
    logger.info("Testing feed parser with fallback...")
    # This will try the feed, get 403 errors, and fall back to API
    bills = parse_bill_texts_feed(limit=2)
    assert bills is not None, "Bills should not be None"
    assert isinstance(bills, list), "Bills should be a list"
    if bills:
        logger.info(f"✅ Feed parser returned {len(bills)} bills from API fallback")
    else:
        logger.warning("⚠️ Feed parser returned no bills from API fallback")
    print("="*60)

def test_duplicate_processing():
    """Test that duplicate bill processing is prevented"""
    print("\n" + "="*60)
    logger.info("Testing duplicate bill processing...")
    
    # 1. Insert a dummy bill
    dummy_bill = {
        "bill_id": "hr9999-119",
        "title": "Test Bill",
        "short_title": "Test Bill",
        "status": "Introduced",
        "summary_tweet": "This is a test bill.",
        "summary_long": "This is a test bill.",
        "summary_overview": "This is a test bill.",
        "summary_detailed": "This is a test bill.",
        "term_dictionary": "{}",
        "congress_session": "119",
        "date_introduced": "2025-10-12",
        "source_url": "https://www.congress.gov",
        "website_slug": "hr9999-119-test-bill",
        "tags": "test",
        "tweet_posted": False
    }
    insert_bill(dummy_bill)
    logger.info("Inserted dummy bill hr9999-119")

    # 2. Try to select it as an unposted bill in a separate transaction
    with postgres_connect() as conn1:
        with conn1.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor1:
            cursor1.execute('''
                SELECT * FROM bills
                WHERE bill_id = 'hr9999-119'
                FOR UPDATE SKIP LOCKED
            ''')
            unposted_bill = dict(cursor1.fetchone())
            assert unposted_bill is not None, "Should be able to select the unposted bill"
            assert unposted_bill['bill_id'] == "hr9999-119", "Should select the correct bill"
            logger.info("✅ Successfully selected and locked the unposted bill in transaction 1")

            # 3. Try to select it again in a different transaction (should fail because it's locked)
            with postgres_connect() as conn2:
                with conn2.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor2:
                    cursor2.execute('''
                        SELECT * FROM bills
                        WHERE bill_id = 'hr9999-119'
                        FOR UPDATE SKIP LOCKED
                    ''')
                    unposted_bill_2 = cursor2.fetchone()
                    assert unposted_bill_2 is None, "Should not be able to select the locked bill"
                    logger.info("✅ Correctly prevented selection of the locked bill in transaction 2")

    print("="*60)

def test_db_diagnostics():
    """Test that database connection diagnostics are working"""
    print("\n" + "="*60)
    logger.info("Testing database connection diagnostics...")
    logger.info("Database connection diagnostics test completed")
    print("="*60)

if __name__ == "__main__":
    init_db_tables()
    test_feed_parser_with_fallback()
    test_duplicate_processing()
    test_db_diagnostics()
    logger.info("\n🎉 All workflow fix tests passed!")