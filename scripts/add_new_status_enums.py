#!/usr/bin/env python3
"""
Migration script to add new status enum values to the bill_status enum.
Adds 'agreed_to_in_senate' and 'agreed_to_in_house' values.
"""

import os
import sys
import logging
from dotenv import load_dotenv

# Load environment variables first
load_dotenv()

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.database.connection import postgres_connect

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def add_new_status_enums():
    """
    Add new values to the bill_status enum.
    """
    logger.info("🚀 Starting migration to add new status enum values...")
    
    try:
        with postgres_connect() as conn:
            with conn.cursor() as cursor:
                # Add 'agreed_to_in_senate' to the bill_status enum
                logger.info("➕ Adding 'agreed_to_in_senate' to bill_status enum...")
                cursor.execute("ALTER TYPE bill_status ADD VALUE 'agreed_to_in_senate';")
                logger.info("✅ Added 'agreed_to_in_senate' to bill_status enum")
                
                # Add 'agreed_to_in_house' to the bill_status enum
                logger.info("➕ Adding 'agreed_to_in_house' to bill_status enum...")
                cursor.execute("ALTER TYPE bill_status ADD VALUE 'agreed_to_in_house';")
                logger.info("✅ Added 'agreed_to_in_house' to bill_status enum")
                
                # Commit the transaction
                conn.commit()
                logger.info("💾 Migration committed successfully")
                
        logger.info("✅ Migration completed successfully!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        return False


if __name__ == "__main__":
    success = add_new_status_enums()
    sys.exit(0 if success else 1)