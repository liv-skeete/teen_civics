#!/usr/bin/env python3
"""
Database schema migration script to add teen_impact_score column.
This column will store the pre-extracted Teen Impact Score for faster retrieval.
"""

import os
import sys
import logging

# Load environment variables first
from dotenv import load_dotenv
load_dotenv()

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.database.connection import postgres_connect

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def add_teen_impact_score_column():
    """
    Add teen_impact_score column to the bills table.
    """
    logger.info("🚀 Starting teen_impact_score column migration...")
    
    try:
        with postgres_connect() as conn:
            with conn.cursor() as cursor:
                # Check if column already exists
                logger.info("📋 Checking if teen_impact_score column already exists...")
                cursor.execute("""
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_name = 'bills'
                    AND column_name = 'teen_impact_score'
                """)
                result = cursor.fetchone()
                
                if result:
                    logger.info("✅ teen_impact_score column already exists. No migration needed.")
                    return True
                
                # Add teen_impact_score column
                logger.info("➕ Adding teen_impact_score column...")
                cursor.execute("""
                    ALTER TABLE bills 
                    ADD COLUMN IF NOT EXISTS teen_impact_score INTEGER
                """)
                logger.info("✅ teen_impact_score column added")
                
                # Create index for performance
                logger.info("📇 Creating index on teen_impact_score...")
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_bills_teen_impact_score 
                    ON bills (teen_impact_score)
                """)
                logger.info("✅ Index on teen_impact_score created")
                
                conn.commit()
                logger.info("✅ Database migration completed successfully!")
                return True
                
    except Exception as e:
        logger.error(f"❌ Failed to add teen_impact_score column: {e}")
        return False


def main():
    """Main migration function."""
    logger.info("Starting teen_impact_score column migration")
    
    success = add_teen_impact_score_column()
    
    if success:
        logger.info("✅ teen_impact_score column migration completed successfully!")
        sys.exit(0)
    else:
        logger.error("❌ teen_impact_score column migration failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()