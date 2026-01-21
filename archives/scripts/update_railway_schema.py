#!/usr/bin/env python3
"""
Script to update the Railway database schema to match Supabase schema.
"""

import sys
import os

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Load environment variables first
from src.load_env import load_env
load_env()

# Import the database initialization function
from src.database.db import init_db
from src.database.connection import postgres_connect
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def update_railway_schema():
    """Update the Railway database schema to match Supabase schema."""
    init_db()
    
    try:
        with postgres_connect() as conn:
            with conn.cursor() as cursor:
                # Add missing columns
                logger.info("Adding missing columns to Railway database...")
                
                # Add raw_latest_action column
                try:
                    cursor.execute("ALTER TABLE bills ADD COLUMN IF NOT EXISTS raw_latest_action TEXT")
                    logger.info("Added raw_latest_action column")
                except Exception as e:
                    logger.warning(f"Could not add raw_latest_action column: {e}")
                
                # Add text_source column
                try:
                    cursor.execute("ALTER TABLE bills ADD COLUMN IF NOT EXISTS text_source TEXT")
                    logger.info("Added text_source column")
                except Exception as e:
                    logger.warning(f"Could not add text_source column: {e}")
                
                # Add text_version column
                try:
                    cursor.execute("ALTER TABLE bills ADD COLUMN IF NOT EXISTS text_version TEXT")
                    logger.info("Added text_version column")
                except Exception as e:
                    logger.warning(f"Could not add text_version column: {e}")
                
                # Add text_received_date column
                try:
                    cursor.execute("ALTER TABLE bills ADD COLUMN IF NOT EXISTS text_received_date TIMESTAMP WITH TIME ZONE")
                    logger.info("Added text_received_date column")
                except Exception as e:
                    logger.warning(f"Could not add text_received_date column: {e}")
                
                # Add processing_attempts column
                try:
                    cursor.execute("ALTER TABLE bills ADD COLUMN IF NOT EXISTS processing_attempts INTEGER DEFAULT 0")
                    logger.info("Added processing_attempts column")
                except Exception as e:
                    logger.warning(f"Could not add processing_attempts column: {e}")
                
                # Add full_text column
                try:
                    cursor.execute("ALTER TABLE bills ADD COLUMN IF NOT EXISTS full_text TEXT")
                    logger.info("Added full_text column")
                except Exception as e:
                    logger.warning(f"Could not add full_text column: {e}")
                
                # Add fts_vector column (for full-text search)
                try:
                    cursor.execute("ALTER TABLE bills ADD COLUMN IF NOT EXISTS fts_vector TSVECTOR")
                    logger.info("Added fts_vector column")
                except Exception as e:
                    logger.warning(f"Could not add fts_vector column: {e}")
                
                # Add normalized_status column (as text for now)
                try:
                    cursor.execute("ALTER TABLE bills ADD COLUMN IF NOT EXISTS normalized_status TEXT")
                    logger.info("Added normalized_status column")
                except Exception as e:
                    logger.warning(f"Could not add normalized_status column: {e}")
                
                # Add tracker_raw column
                try:
                    cursor.execute("ALTER TABLE bills ADD COLUMN IF NOT EXISTS tracker_raw TEXT")
                    logger.info("Added tracker_raw column")
                except Exception as e:
                    logger.warning(f"Could not add tracker_raw column: {e}")
                
                # Add summary_technical_details column
                try:
                    cursor.execute("ALTER TABLE bills ADD COLUMN IF NOT EXISTS summary_technical_details TEXT")
                    logger.info("Added summary_technical_details column")
                except Exception as e:
                    logger.warning(f"Could not add summary_technical_details column: {e}")
                
                # Convert date_processed to TIMESTAMP WITH TIME ZONE to match Supabase
                try:
                    cursor.execute("ALTER TABLE bills ALTER COLUMN date_processed TYPE TIMESTAMP WITH TIME ZONE")
                    logger.info("Updated date_processed column to TIMESTAMP WITH TIME ZONE")
                except Exception as e:
                    logger.warning(f"Could not update date_processed column: {e}")
                
                # Convert created_at to TIMESTAMP WITH TIME ZONE to match Supabase
                try:
                    cursor.execute("ALTER TABLE bills ALTER COLUMN created_at TYPE TIMESTAMP WITH TIME ZONE")
                    logger.info("Updated created_at column to TIMESTAMP WITH TIME ZONE")
                except Exception as e:
                    logger.warning(f"Could not update created_at column: {e}")
                
                # Convert updated_at to TIMESTAMP WITH TIME ZONE to match Supabase
                try:
                    cursor.execute("ALTER TABLE bills ALTER COLUMN updated_at TYPE TIMESTAMP WITH TIME ZONE")
                    logger.info("Updated updated_at column to TIMESTAMP WITH TIME ZONE")
                except Exception as e:
                    logger.warning(f"Could not update updated_at column: {e}")
                
                # Add index for fts_vector if it exists
                try:
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_bills_fts_vector ON bills USING GIN (fts_vector)")
                    logger.info("Added index for fts_vector column")
                except Exception as e:
                    logger.warning(f"Could not add index for fts_vector column: {e}")
                
                logger.info("Railway database schema updated successfully!")
        
        logger.info("✅ Railway database schema update completed!")
        
    except Exception as e:
        logger.error(f"❌ Failed to update Railway database schema: {e}")
        raise

if __name__ == "__main__":
    update_railway_schema()