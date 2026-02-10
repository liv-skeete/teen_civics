#!/usr/bin/env python3
"""
Database schema migration script to add the votes table.
This table stores individual vote records linked to anonymous voter IDs
(UUID stored in a long-lived HTTP-only cookie).

Table created:
- votes: Stores (voter_id, bill_id, vote_type) with a unique constraint
  on (voter_id, bill_id) so each voter can only have one vote per bill.

Indexes created:
- idx_votes_voter_id: For fast lookup of all votes by a voter
- idx_votes_bill_id: For fast lookup of all votes on a bill
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


def add_votes_table():
    """
    Create the votes table and its indexes.
    """
    logger.info("🚀 Starting votes table migration...")

    try:
        with postgres_connect() as conn:
            with conn.cursor() as cursor:
                # Check if table already exists
                logger.info("📋 Checking if votes table already exists...")
                cursor.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables
                        WHERE table_name = 'votes'
                    )
                """)
                table_exists = cursor.fetchone()[0]

                if table_exists:
                    logger.info("✅ Votes table already exists. Ensuring indexes are present...")
                else:
                    logger.info("➕ Creating votes table...")
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS votes (
                            id SERIAL PRIMARY KEY,
                            voter_id VARCHAR(36) NOT NULL,
                            bill_id VARCHAR(50) NOT NULL,
                            vote_type VARCHAR(10) NOT NULL,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            UNIQUE(voter_id, bill_id)
                        )
                    """)
                    logger.info("✅ Votes table created")

                # Create indexes (idempotent)
                logger.info("📇 Creating indexes...")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_votes_voter_id ON votes(voter_id);")
                logger.info("✅ Index idx_votes_voter_id created/verified")

                cursor.execute("CREATE INDEX IF NOT EXISTS idx_votes_bill_id ON votes(bill_id);")
                logger.info("✅ Index idx_votes_bill_id created/verified")

                conn.commit()
                logger.info("✅ Votes table migration completed successfully!")
                return True

    except Exception as e:
        logger.error(f"❌ Failed to create votes table: {e}")
        return False


def verify_table():
    """
    Verify that the votes table was created successfully.
    """
    logger.info("🔍 Verifying votes table...")

    try:
        with postgres_connect() as conn:
            with conn.cursor() as cursor:
                # Check table exists
                cursor.execute("""
                    SELECT column_name, data_type
                    FROM information_schema.columns
                    WHERE table_name = 'votes'
                    ORDER BY ordinal_position
                """)
                columns = cursor.fetchall()

                if columns:
                    logger.info("✅ Verification passed! Votes table columns:")
                    for col_name, col_type in columns:
                        logger.info(f"   - {col_name}: {col_type}")
                else:
                    logger.error("❌ Verification failed! Votes table not found.")
                    return False

                # Check indexes
                cursor.execute("""
                    SELECT indexname
                    FROM pg_indexes
                    WHERE tablename = 'votes'
                    ORDER BY indexname
                """)
                indexes = [row[0] for row in cursor.fetchall()]
                logger.info(f"✅ Indexes on votes table: {indexes}")

                return True

    except Exception as e:
        logger.error(f"❌ Verification error: {e}")
        return False


def main():
    """Main migration function."""
    logger.info("=" * 60)
    logger.info("Votes Table Migration")
    logger.info("=" * 60)

    success = add_votes_table()

    if success:
        verify_table()
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
