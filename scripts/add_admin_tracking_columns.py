#!/usr/bin/env python3
"""
Database schema migration script to add admin tracking columns.
These columns will store information about admin edits to bills.

Columns added:
- last_edited_at: ISO 8601 timestamp of the last admin edit
- last_edited_by: Name of who made the edit (e.g. "Liv")
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


def add_admin_tracking_columns():
    """
    Add admin tracking columns to the bills table.
    """
    logger.info("🚀 Starting admin tracking columns migration...")

    try:
        with postgres_connect() as conn:
            with conn.cursor() as cursor:
                # Check if columns already exist
                logger.info("📋 Checking if admin tracking columns already exist...")
                cursor.execute("""
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_name = 'bills'
                    AND column_name IN ('last_edited_at', 'last_edited_by')
                """)
                existing_columns = [row[0] for row in cursor.fetchall()]

                if len(existing_columns) == 2:
                    logger.info("✅ All admin tracking columns already exist. No migration needed.")
                    return True

                logger.info(f"📊 Existing admin tracking columns: {existing_columns}")

                # Add admin tracking columns
                logger.info("➕ Adding admin tracking columns...")
                cursor.execute("""
                    ALTER TABLE bills
                    ADD COLUMN IF NOT EXISTS last_edited_at TEXT,
                    ADD COLUMN IF NOT EXISTS last_edited_by TEXT
                """)
                logger.info("✅ Admin tracking columns added")

                conn.commit()
                logger.info("✅ Database migration completed successfully!")
                return True

    except Exception as e:
        logger.error(f"❌ Failed to add admin tracking columns: {e}")
        return False


def verify_columns():
    """
    Verify that the admin tracking columns were added successfully.
    """
    logger.info("🔍 Verifying admin tracking columns...")

    try:
        with postgres_connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT column_name, data_type
                    FROM information_schema.columns
                    WHERE table_name = 'bills'
                    AND column_name IN ('last_edited_at', 'last_edited_by')
                    ORDER BY column_name
                """)
                columns = cursor.fetchall()

                if len(columns) == 2:
                    logger.info("✅ All admin tracking columns verified:")
                    for col_name, col_type in columns:
                        logger.info(f"   - {col_name}: {col_type}")
                    return True
                else:
                    logger.error(f"❌ Expected 2 columns, found {len(columns)}")
                    return False

    except Exception as e:
        logger.error(f"❌ Failed to verify admin tracking columns: {e}")
        return False


if __name__ == "__main__":
    success = add_admin_tracking_columns()
    if success:
        verify_columns()
    else:
        sys.exit(1)
