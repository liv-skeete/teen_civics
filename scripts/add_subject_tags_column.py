#!/usr/bin/env python3
"""
Migration: Add subject_tags TEXT column to the bills table.
Safe to run multiple times (uses IF NOT EXISTS pattern via column check).

Also updates the FTS trigger to include subject_tags in the search vector.
"""

import os
import sys
import logging

# Ensure project root is on sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.load_env import load_env
load_env()

from src.database.connection import postgres_connect

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def run_migration():
    """Add subject_tags column and update FTS trigger."""
    try:
        with postgres_connect() as conn:
            with conn.cursor() as cursor:
                # Step 1: Add subject_tags column if it doesn't exist
                logger.info("Step 1: Adding subject_tags column...")
                cursor.execute("""
                    ALTER TABLE bills ADD COLUMN IF NOT EXISTS subject_tags TEXT;
                """)
                logger.info("✅ subject_tags column added (or already exists).")

                # Step 2: Update FTS trigger to include subject_tags
                logger.info("Step 2: Updating FTS trigger to include subject_tags...")
                cursor.execute("""
                    CREATE OR REPLACE FUNCTION update_bills_fts_vector()
                    RETURNS TRIGGER AS $$
                    BEGIN
                        NEW.fts_vector :=
                            setweight(to_tsvector('english', COALESCE(NEW.title, '')), 'A') ||
                            setweight(to_tsvector('english', COALESCE(NEW.sponsor_name, '')), 'A') ||
                            setweight(to_tsvector('english', COALESCE(NEW.summary_long, '')), 'B') ||
                            setweight(to_tsvector('english', COALESCE(NEW.summary_overview, '')), 'C') ||
                            setweight(to_tsvector('english', COALESCE(NEW.summary_detailed, '')), 'C') ||
                            setweight(to_tsvector('english', COALESCE(NEW.summary_tweet, '')), 'C') ||
                            setweight(to_tsvector('english', COALESCE(NEW.tags, '')), 'D') ||
                            setweight(to_tsvector('english', COALESCE(NEW.subject_tags, '')), 'B');
                        RETURN NEW;
                    END;
                    $$ LANGUAGE plpgsql;
                """)
                logger.info("✅ FTS trigger function updated with subject_tags.")

                # Step 3: Verify column exists
                cursor.execute("""
                    SELECT column_name FROM information_schema.columns
                    WHERE table_name = 'bills' AND column_name = 'subject_tags'
                """)
                if cursor.fetchone():
                    logger.info("✅ Verified: subject_tags column exists in bills table.")
                else:
                    logger.error("❌ subject_tags column NOT found after migration!")
                    return False

        logger.info("🎉 Migration complete: subject_tags column added successfully.")
        return True

    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        return False


if __name__ == "__main__":
    success = run_migration()
    sys.exit(0 if success else 1)
