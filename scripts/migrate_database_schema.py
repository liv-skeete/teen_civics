#!/usr/bin/env python3
"""
Database schema migration script for new workflow fields.
Adds fields needed for feed-based bill text processing.
"""

import os
import sys
import logging
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables first
load_dotenv()

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.database.connection import get_connection_manager

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def migrate_schema():
    """
    Add new columns to the bills table for feed-based processing.
    
    New fields:
    - text_source: Source of the bill text (e.g., 'feed', 'api')
    - text_version: Version of the bill text (e.g., 'Introduced', 'Engrossed')
    - text_received_date: Date when full text was received
    - processing_attempts: Number of times processing was attempted
    """
    logger.info("🚀 Starting database schema migration...")
    
    pg_connect = get_connection_manager()
    
    try:
        with pg_connect() as conn:
            with conn.cursor() as cursor:
                # Check if migration is needed
                logger.info("📋 Checking current schema...")
                cursor.execute("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = 'bills' 
                    AND column_name IN ('text_source', 'text_version', 'text_received_date', 'processing_attempts')
                """)
                existing_columns = {row[0] for row in cursor.fetchall()}
                
                if len(existing_columns) == 4:
                    logger.info("✅ All new columns already exist. No migration needed.")
                    return True
                
                logger.info(f"📊 Found {len(existing_columns)} of 4 new columns. Proceeding with migration...")
                
                # Add text_source column
                if 'text_source' not in existing_columns:
                    logger.info("➕ Adding text_source column...")
                    cursor.execute("""
                        ALTER TABLE bills 
                        ADD COLUMN IF NOT EXISTS text_source TEXT DEFAULT 'api'
                    """)
                    logger.info("✅ text_source column added")
                
                # Add text_version column
                if 'text_version' not in existing_columns:
                    logger.info("➕ Adding text_version column...")
                    cursor.execute("""
                        ALTER TABLE bills 
                        ADD COLUMN IF NOT EXISTS text_version TEXT DEFAULT 'Introduced'
                    """)
                    logger.info("✅ text_version column added")
                
                # Add text_received_date column
                if 'text_received_date' not in existing_columns:
                    logger.info("➕ Adding text_received_date column...")
                    cursor.execute("""
                        ALTER TABLE bills 
                        ADD COLUMN IF NOT EXISTS text_received_date TIMESTAMP WITH TIME ZONE
                    """)
                    logger.info("✅ text_received_date column added")
                
                # Add processing_attempts column
                if 'processing_attempts' not in existing_columns:
                    logger.info("➕ Adding processing_attempts column...")
                    cursor.execute("""
                        ALTER TABLE bills 
                        ADD COLUMN IF NOT EXISTS processing_attempts INTEGER DEFAULT 0
                    """)
                    logger.info("✅ processing_attempts column added")
                
                # Create indexes for performance
                logger.info("📇 Creating indexes...")
                
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_bills_text_received 
                    ON bills (text_received_date)
                """)
                logger.info("✅ Index on text_received_date created")
                
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_bills_processing_attempts 
                    ON bills (processing_attempts)
                """)
                logger.info("✅ Index on processing_attempts created")
                
                # Update existing bills with default values
                logger.info("🔄 Updating existing bills with default values...")
                cursor.execute("""
                    UPDATE bills 
                    SET text_source = 'api',
                        text_version = 'Introduced',
                        text_received_date = date_introduced::timestamp with time zone,
                        processing_attempts = 0
                    WHERE text_source IS NULL
                """)
                updated_count = cursor.rowcount
                logger.info(f"✅ Updated {updated_count} existing bills with default values")
                
                # Commit the transaction
                conn.commit()
                logger.info("💾 Migration committed successfully")
                
                # Verify migration
                logger.info("🔍 Verifying migration...")
                cursor.execute("""
                    SELECT column_name, data_type, column_default
                    FROM information_schema.columns 
                    WHERE table_name = 'bills' 
                    AND column_name IN ('text_source', 'text_version', 'text_received_date', 'processing_attempts')
                    ORDER BY column_name
                """)
                
                columns = cursor.fetchall()
                logger.info("📊 New columns verified:")
                for col_name, data_type, default in columns:
                    logger.info(f"  - {col_name}: {data_type} (default: {default})")
                
                if len(columns) == 4:
                    logger.info("✅ Migration completed successfully!")
                    return True
                else:
                    logger.error(f"❌ Migration verification failed. Expected 4 columns, found {len(columns)}")
                    return False
                    
    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        return False


def rollback_migration():
    """
    Rollback the schema migration by removing added columns.
    USE WITH CAUTION - This will delete data!
    """
    logger.warning("⚠️ Starting schema rollback - THIS WILL DELETE DATA!")
    
    response = input("Are you sure you want to rollback? Type 'YES' to confirm: ")
    if response != 'YES':
        logger.info("Rollback cancelled")
        return False
    
    pg_connect = get_connection_manager()
    
    try:
        with pg_connect() as conn:
            with conn.cursor() as cursor:
                logger.info("🗑️ Dropping new columns...")
                
                cursor.execute("ALTER TABLE bills DROP COLUMN IF EXISTS text_source")
                cursor.execute("ALTER TABLE bills DROP COLUMN IF EXISTS text_version")
                cursor.execute("ALTER TABLE bills DROP COLUMN IF EXISTS text_received_date")
                cursor.execute("ALTER TABLE bills DROP COLUMN IF EXISTS processing_attempts")
                
                logger.info("🗑️ Dropping indexes...")
                cursor.execute("DROP INDEX IF EXISTS idx_bills_text_received")
                cursor.execute("DROP INDEX IF EXISTS idx_bills_processing_attempts")
                
                conn.commit()
                logger.info("✅ Rollback completed successfully")
                return True
                
    except Exception as e:
        logger.error(f"❌ Rollback failed: {e}")
        return False


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Database schema migration for new workflow")
    parser.add_argument("--rollback", action="store_true", help="Rollback the migration (DANGEROUS)")
    
    args = parser.parse_args()
    
    if args.rollback:
        success = rollback_migration()
    else:
        success = migrate_schema()
    
    sys.exit(0 if success else 1)