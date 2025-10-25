#!/usr/bin/env python3
"""
Script to delete the bill s284-119 from the database.
"""

import sys
import os
import logging

# Add the src directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from load_env import load_env
from database.connection import postgres_connect, is_postgres_available

# Load environment variables from .env file
load_env()

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def delete_bill_s284_119():
    """Delete the bill s284-119 from the database and verify deletion."""
    
    # Check if PostgreSQL is available
    if not is_postgres_available():
        logger.error("PostgreSQL database is not available. Cannot proceed.")
        return False
    
    bill_id = 's284-119'
    
    try:
        with postgres_connect() as conn:
            with conn.cursor() as cursor:
                # First, check if the bill exists
                logger.info(f"Checking if bill '{bill_id}' exists...")
                cursor.execute(
                    "SELECT bill_id, title, summary_tweet, created_at FROM bills WHERE bill_id = %s",
                    (bill_id,)
                )
                bill = cursor.fetchone()
                
                if not bill:
                    logger.warning(f"Bill '{bill_id}' not found in database. Nothing to delete.")
                    return True
                
                logger.info(f"Found bill: {bill}")
                logger.info(f"  Bill ID: {bill[0]}")
                logger.info(f"  Title: {bill[1]}")
                logger.info(f"  Summary: {bill[2]}")
                logger.info(f"  Created At: {bill[3]}")
                
                # Delete the bill
                logger.info(f"Deleting bill '{bill_id}'...")
                cursor.execute(
                    "DELETE FROM bills WHERE bill_id = %s",
                    (bill_id,)
                )
                deleted_count = cursor.rowcount
                
                if deleted_count > 0:
                    logger.info(f"Successfully deleted {deleted_count} row(s)")
                else:
                    logger.warning("No rows were deleted")
                    return False
                
                # Verify deletion
                logger.info(f"Verifying deletion...")
                cursor.execute(
                    "SELECT COUNT(*) FROM bills WHERE bill_id = %s",
                    (bill_id,)
                )
                count = cursor.fetchone()[0]
                
                if count == 0:
                    logger.info(f"✓ Verification successful: Bill '{bill_id}' is no longer in the database")
                    return True
                else:
                    logger.error(f"✗ Verification failed: Bill '{bill_id}' still exists in database")
                    return False
                    
    except Exception as e:
        logger.error(f"Error deleting bill: {e}")
        return False

if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("Starting bill deletion script for s284-119")
    logger.info("=" * 60)
    
    success = delete_bill_s284_119()
    
    logger.info("=" * 60)
    if success:
        logger.info("✓ Bill deletion completed successfully")
        sys.exit(0)
    else:
        logger.error("✗ Bill deletion failed")
        sys.exit(1)