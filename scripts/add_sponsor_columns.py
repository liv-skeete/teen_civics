#!/usr/bin/env python3
"""
Database schema migration script to add sponsor columns.
These columns will store bill sponsor information for search and reveal-after-vote display.

Columns added:
- sponsor_name: Full name of the bill's primary sponsor
- sponsor_party: Party affiliation (D, R, I, etc.)
- sponsor_state: State represented (CA, TX, NY, etc.)
"""

import os
import sys
import logging

# Load environment variables first
from dotenv import load_dotenv
load_dotenv()

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database.connection import postgres_connect

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def add_sponsor_columns():
    """
    Add sponsor columns to the bills table.
    """
    logger.info("🚀 Starting sponsor columns migration...")
    
    try:
        with postgres_connect() as conn:
            with conn.cursor() as cursor:
                # Check if columns already exist
                logger.info("📋 Checking if sponsor columns already exist...")
                cursor.execute("""
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_name = 'bills'
                    AND column_name IN ('sponsor_name', 'sponsor_party', 'sponsor_state')
                """)
                existing_columns = [row[0] for row in cursor.fetchall()]
                
                if len(existing_columns) == 3:
                    logger.info("✅ All sponsor columns already exist. No migration needed.")
                    return True
                
                logger.info(f"📊 Existing sponsor columns: {existing_columns}")
                
                # Add sponsor columns
                logger.info("➕ Adding sponsor columns...")
                cursor.execute("""
                    ALTER TABLE bills 
                    ADD COLUMN IF NOT EXISTS sponsor_name TEXT,
                    ADD COLUMN IF NOT EXISTS sponsor_party TEXT,
                    ADD COLUMN IF NOT EXISTS sponsor_state TEXT
                """)
                logger.info("✅ Sponsor columns added")
                
                # Create index for search performance on sponsor_name
                logger.info("📇 Creating index on sponsor_name...")
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_bills_sponsor_name 
                    ON bills (sponsor_name)
                """)
                logger.info("✅ Index on sponsor_name created")
                
                conn.commit()
                logger.info("✅ Database migration completed successfully!")
                return True
                
    except Exception as e:
        logger.error(f"❌ Failed to add sponsor columns: {e}")
        return False


def verify_columns():
    """
    Verify that the sponsor columns were added successfully.
    """
    logger.info("🔍 Verifying sponsor columns...")
    
    try:
        with postgres_connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT column_name, data_type
                    FROM information_schema.columns
                    WHERE table_name = 'bills'
                    AND column_name IN ('sponsor_name', 'sponsor_party', 'sponsor_state')
                    ORDER BY column_name
                """)
                columns = cursor.fetchall()
                
                if len(columns) == 3:
                    logger.info("✅ Verification passed! All sponsor columns present:")
                    for col_name, col_type in columns:
                        logger.info(f"   - {col_name}: {col_type}")
                    return True
                else:
                    logger.error(f"❌ Verification failed! Only {len(columns)} of 3 columns found.")
                    return False
                    
    except Exception as e:
        logger.error(f"❌ Verification error: {e}")
        return False


def main():
    """Main migration function."""
    logger.info("=" * 60)
    logger.info("Sponsor Columns Migration")
    logger.info("=" * 60)
    
    success = add_sponsor_columns()
    
    if success:
        verify_columns()
        logger.info("=" * 60)
        logger.info("✅ Migration completed successfully!")
        logger.info("=" * 60)
        sys.exit(0)
    else:
        logger.info("=" * 60)
        logger.error("❌ Migration failed!")
        logger.info("=" * 60)
        sys.exit(1)


if __name__ == "__main__":
    main()
