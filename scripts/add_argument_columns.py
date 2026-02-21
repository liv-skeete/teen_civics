#!/usr/bin/env python3
"""
Database schema migration script to add argument columns to the bills table.

Columns added:
- argument_support: Pre-generated persuasive text for supporting the bill (≤500 chars)
- argument_oppose:  Pre-generated persuasive text for opposing the bill (≤500 chars)

These columns are populated at bill-insert time by argument_generator.py
and consumed by the /api/generate-email endpoint so it never blocks on AI.

Usage:
    python scripts/add_argument_columns.py
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


def add_argument_columns():
    """
    Add argument_support and argument_oppose columns to the bills table.
    Safe to run multiple times (uses IF NOT EXISTS).
    """
    logger.info("🚀 Starting argument columns migration...")

    try:
        with postgres_connect() as conn:
            with conn.cursor() as cursor:
                # Check if columns already exist
                logger.info("📋 Checking if argument columns already exist...")
                cursor.execute("""
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_name = 'bills'
                    AND column_name IN ('argument_support', 'argument_oppose')
                """)
                existing_columns = [row[0] for row in cursor.fetchall()]

                if len(existing_columns) == 2:
                    logger.info("✅ Both argument columns already exist. No migration needed.")
                    return True

                logger.info(f"📊 Existing argument columns: {existing_columns}")

                # Add argument columns
                logger.info("➕ Adding argument columns...")
                cursor.execute("""
                    ALTER TABLE bills
                    ADD COLUMN IF NOT EXISTS argument_support TEXT,
                    ADD COLUMN IF NOT EXISTS argument_oppose TEXT
                """)
                logger.info("✅ Argument columns added")

                conn.commit()
                logger.info("✅ Database migration completed successfully!")
                return True

    except Exception as e:
        logger.error(f"❌ Failed to add argument columns: {e}")
        return False


def verify_columns():
    """Verify the columns were added correctly."""
    logger.info("🔍 Verifying argument columns...")

    try:
        with postgres_connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT column_name, data_type, character_maximum_length
                    FROM information_schema.columns
                    WHERE table_name = 'bills'
                    AND column_name IN ('argument_support', 'argument_oppose')
                    ORDER BY column_name
                """)
                rows = cursor.fetchall()

                if len(rows) == 2:
                    for row in rows:
                        logger.info(f"  ✅ {row[0]}: {row[1]} (max_length: {row[2]})")
                    logger.info("✅ All argument columns verified!")
                    return True
                else:
                    logger.error(f"❌ Expected 2 columns, found {len(rows)}")
                    return False

    except Exception as e:
        logger.error(f"❌ Verification failed: {e}")
        return False


if __name__ == "__main__":
    success = add_argument_columns()
    if success:
        verify_columns()
    sys.exit(0 if success else 1)
