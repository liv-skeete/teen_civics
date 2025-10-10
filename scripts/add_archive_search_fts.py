#!/usr/bin/env python3
"""
Migration script to add a tsvector column and triggers for Full-Text Search (FTS)
to the PostgreSQL database.

This script is idempotent and can be run multiple times safely.
"""

import os
import sys
import logging

# Add src directory to Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Load environment variables from .env file
from src.load_env import load_env
load_env()

from src.database.connection import postgres_connect

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def add_fts_to_bills_table():
    """
    Adds a tsvector column, an index, and triggers to the bills table for FTS.
    """
    try:
        with postgres_connect() as conn:
            with conn.cursor() as cursor:
                logger.info("Step 1: Add 'fts_vector' column to 'bills' table if it doesn't exist...")
                cursor.execute("""
                    ALTER TABLE bills ADD COLUMN IF NOT EXISTS fts_vector tsvector;
                """)
                logger.info("Column 'fts_vector' is present.")

                logger.info("Step 2: Create a GIN index on 'fts_vector' if it doesn't exist...")
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS bills_fts_vector_idx ON bills USING gin(fts_vector);
                """)
                logger.info("GIN index on 'fts_vector' is present.")

                logger.info("Step 3: Create or replace the trigger function to update 'fts_vector'...")
                cursor.execute("""
                    CREATE OR REPLACE FUNCTION update_bills_fts_vector()
                    RETURNS TRIGGER AS $$
                    BEGIN
                        NEW.fts_vector :=
                            setweight(to_tsvector('english', COALESCE(NEW.title, '')), 'A') ||
                            setweight(to_tsvector('english', COALESCE(NEW.summary_long, '')), 'B') ||
                            setweight(to_tsvector('english', COALESCE(NEW.summary_overview, '')), 'C') ||
                            setweight(to_tsvector('english', COALESCE(NEW.summary_detailed, '')), 'C') ||
                            setweight(to_tsvector('english', COALESCE(NEW.summary_tweet, '')), 'C') ||
                            setweight(to_tsvector('english', COALESCE(NEW.tags, '')), 'D');
                        RETURN NEW;
                    END;
                    $$ LANGUAGE plpgsql;
                """)
                logger.info("Trigger function 'update_bills_fts_vector' created or updated.")

                logger.info("Step 4: Create a trigger to call the function on INSERT or UPDATE...")
                cursor.execute("""
                    DROP TRIGGER IF EXISTS bills_fts_vector_update ON bills;
                    CREATE TRIGGER bills_fts_vector_update
                    BEFORE INSERT OR UPDATE ON bills
                    FOR EACH ROW
                    EXECUTE FUNCTION update_bills_fts_vector();
                """)
                logger.info("Trigger 'bills_fts_vector_update' created.")

                logger.info("Step 5: Backfill 'fts_vector' for existing rows where it is NULL...")
                cursor.execute("""
                    UPDATE bills
                    SET fts_vector = 
                        setweight(to_tsvector('english', COALESCE(title, '')), 'A') ||
                        setweight(to_tsvector('english', COALESCE(summary_long, '')), 'B') ||
                        setweight(to_tsvector('english', COALESCE(summary_overview, '')), 'C') ||
                        setweight(to_tsvector('english', COALESCE(summary_detailed, '')), 'C') ||
                        setweight(to_tsvector('english', COALESCE(summary_tweet, '')), 'C') ||
                        setweight(to_tsvector('english', COALESCE(tags, '')), 'D')
                    WHERE fts_vector IS NULL;
                """)
                logger.info(f"{cursor.rowcount} existing rows backfilled.")

        logger.info("✅ FTS migration completed successfully.")

    except Exception as e:
        logger.error(f"❌ FTS migration failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    add_fts_to_bills_table()