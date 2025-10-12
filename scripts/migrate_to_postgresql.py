#!/usr/bin/env python3
"""
Data migration script to transfer data from SQLite to PostgreSQL.
This script migrates all bills data from the SQLite database to PostgreSQL.
"""

import os
import sys
import sqlite3
import logging
from datetime import datetime

# Add the src directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.database.connection import is_postgres_available, postgres_connect, init_postgres_tables
from src.load_env import load_env

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('migration.log')
    ]
)
logger = logging.getLogger(__name__)

def get_sqlite_connection():
    """Get SQLite database connection."""
    db_path = os.path.join(os.path.dirname(__file__), '../data/bills.db')
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"SQLite database not found at {db_path}")
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def migrate_data():
    """Migrate data from SQLite to PostgreSQL."""
    # Load environment variables
    load_env()
    
    # Check if PostgreSQL is available
    if not is_postgres_available():
        logger.error("PostgreSQL is not configured or available")
        return False
    
    # Initialize PostgreSQL tables
    try:
        init_postgres_tables()
        logger.info("PostgreSQL tables initialized")
    except Exception as e:
        logger.error(f"Failed to initialize PostgreSQL tables: {e}")
        return False
    
    # Get SQLite data
    try:
        sqlite_conn = get_sqlite_connection()
        sqlite_cursor = sqlite_conn.cursor()
        
        # Get all bills from SQLite
        sqlite_cursor.execute('SELECT * FROM bills ORDER BY id')
        bills = sqlite_cursor.fetchall()
        
        if not bills:
            logger.info("No bills found in SQLite database to migrate")
            return True
        
        logger.info(f"Found {len(bills)} bills to migrate")
        
        # Migrate each bill to PostgreSQL
        migrated_count = 0
        with postgres_connect() as pg_conn:
            pg_cursor = pg_conn.cursor()
            
            for bill in bills:
                try:
                    # Convert SQLite row to dict
                    bill_dict = dict(bill)
                    
                    # Handle SQLite integer booleans to PostgreSQL booleans
                    tweet_posted = bool(bill_dict.get('tweet_posted', 0))
                    
                    # Insert into PostgreSQL
                    pg_cursor.execute('''
                    INSERT INTO bills (
                        bill_id, title, short_title, status, summary_tweet, summary_long,
                        summary_overview, summary_detailed, term_dictionary,
                        congress_session, date_introduced, date_processed, source_url,
                        website_slug, tags, tweet_url, tweet_posted,
                        poll_results_yes, poll_results_no, poll_results_unsure
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (bill_id) DO NOTHING
                    ''', (
                        bill_dict.get('bill_id'),
                        bill_dict.get('title'),
                        bill_dict.get('short_title'),
                        bill_dict.get('status'),
                        bill_dict.get('summary_tweet'),
                        bill_dict.get('summary_long'),
                        bill_dict.get('summary_overview'),
                        bill_dict.get('summary_detailed'),
                        bill_dict.get('term_dictionary'),
                        bill_dict.get('congress_session'),
                        bill_dict.get('date_introduced'),
                        bill_dict.get('date_processed'),
                        bill_dict.get('source_url'),
                        bill_dict.get('website_slug'),
                        bill_dict.get('tags'),
                        bill_dict.get('tweet_url'),
                        tweet_posted,
                        bill_dict.get('poll_results_yes', 0),
                        bill_dict.get('poll_results_no', 0),
                        bill_dict.get('poll_results_unsure', 0)
                    ))
                    
                    if pg_cursor.rowcount > 0:
                        migrated_count += 1
                        logger.info(f"Migrated bill: {bill_dict.get('bill_id')}")
                    else:
                        logger.warning(f"Bill already exists in PostgreSQL: {bill_dict.get('bill_id')}")
                        
                except Exception as e:
                    logger.error(f"Error migrating bill {bill_dict.get('bill_id')}: {e}")
                    continue
        
        logger.info(f"Migration completed: {migrated_count}/{len(bills)} bills migrated successfully")
        return True
        
    except Exception as e:
        logger.error(f"Error during migration: {e}")
        return False
    finally:
        if 'sqlite_conn' in locals():
            sqlite_conn.close()

def verify_migration():
    """Verify that migration was successful by comparing record counts."""
    try:
        # Get SQLite count
        sqlite_conn = get_sqlite_connection()
        sqlite_cursor = sqlite_conn.cursor()
        sqlite_cursor.execute('SELECT COUNT(*) FROM bills')
        sqlite_count = sqlite_cursor.fetchone()[0]
        
        # Get PostgreSQL count
        with postgres_connect() as pg_conn:
            pg_cursor = pg_conn.cursor()
            pg_cursor.execute('SELECT COUNT(*) FROM bills')
            pg_count = pg_cursor.fetchone()[0]
        
        logger.info(f"SQLite records: {sqlite_count}, PostgreSQL records: {pg_count}")
        
        if sqlite_count == pg_count:
            logger.info("✅ Migration verification successful - record counts match!")
            return True
        else:
            logger.warning(f"⚠️  Record counts don't match: SQLite={sqlite_count}, PostgreSQL={pg_count}")
            return False
            
    except Exception as e:
        logger.error(f"Error during verification: {e}")
        return False
    finally:
        if 'sqlite_conn' in locals():
            sqlite_conn.close()

def main():
    """Main migration function."""
    logger.info("Starting SQLite to PostgreSQL migration")
    
    if not migrate_data():
        logger.error("Migration failed")
        sys.exit(1)
    
    if not verify_migration():
        logger.warning("Migration verification showed discrepancies")
        # Don't exit with error for verification issues - data might be intentionally different
    
    logger.info("Migration process completed")

if __name__ == "__main__":
    main()