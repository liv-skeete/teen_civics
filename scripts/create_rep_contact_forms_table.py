#!/usr/bin/env python3
"""
Database schema migration script to add the rep_contact_forms table.
Stores contact form URLs for House representatives.
"""

import os
import sys
import logging

from dotenv import load_dotenv

# Load environment variables first
load_dotenv()

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database.connection import postgres_connect

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS rep_contact_forms (
    bioguide_id TEXT PRIMARY KEY,
    name TEXT,
    state TEXT,
    district INTEGER,
    official_website TEXT,
    contact_form_url TEXT,
    contact_url_source TEXT,
    contact_url_verified_at TIMESTAMP,
    last_synced_at TIMESTAMP DEFAULT NOW()
);
"""

CREATE_INDEX_SQL = (
    "CREATE INDEX IF NOT EXISTS idx_rep_contact_state_district "
    "ON rep_contact_forms(state, district);"
)


def create_rep_contact_forms_table() -> bool:
    """
    Create the rep_contact_forms table and its index.
    """
    logger.info("🚀 Starting rep_contact_forms table migration...")

    try:
        with postgres_connect() as conn:
            with conn.cursor() as cursor:
                # Check if table already exists
                logger.info("📋 Checking if rep_contact_forms table already exists...")
                cursor.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables
                        WHERE table_name = 'rep_contact_forms'
                    )
                """)
                table_exists = cursor.fetchone()[0]

                if table_exists:
                    logger.info("✅ rep_contact_forms table already exists. Ensuring indexes are present...")
                else:
                    logger.info("➕ Creating rep_contact_forms table...")
                    cursor.execute(CREATE_TABLE_SQL)
                    logger.info("✅ rep_contact_forms table created")

                # Create index (idempotent)
                logger.info("📇 Creating index idx_rep_contact_state_district...")
                cursor.execute(CREATE_INDEX_SQL)
                logger.info("✅ Index idx_rep_contact_state_district created/verified")

                conn.commit()
                logger.info("✅ rep_contact_forms migration completed successfully!")
                return True

    except Exception as e:
        logger.error(f"❌ Failed to create rep_contact_forms table: {e}")
        return False


def verify_table() -> bool:
    """
    Verify that the rep_contact_forms table was created successfully.
    """
    logger.info("🔍 Verifying rep_contact_forms table...")

    try:
        with postgres_connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_name = 'rep_contact_forms'
                """)
                table = cursor.fetchone()

                if table:
                    logger.info("✅ Verification passed! rep_contact_forms table found.")
                    return True

                logger.error("❌ Verification failed! rep_contact_forms table not found.")
                return False

    except Exception as e:
        logger.error(f"❌ Verification error: {e}")
        return False


def main() -> None:
    """Main migration function."""
    logger.info("=" * 60)
    logger.info("Rep Contact Forms Table Migration")
    logger.info("=" * 60)

    success = create_rep_contact_forms_table()

    if success:
        verify_table()
        logger.info("=" * 60)
        logger.info("✅ Migration completed successfully!")
        logger.info("=" * 60)
        sys.exit(0)

    logger.info("=" * 60)
    logger.error("❌ Migration failed!")
    logger.info("=" * 60)
    sys.exit(1)


if __name__ == "__main__":
    main()
