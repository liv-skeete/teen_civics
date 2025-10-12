#!/usr/bin/env python3
"""
Script to delete the test bill from the production database.
Deletes bill with bill_id = 'test-bill-123'
"""

import sys
import logging
from src.load_env import load_env
from src.database.connection import postgres_connect, is_postgres_available

# Load environment variables from .env file
load_env()

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def delete_test_bill():
    """Delete the test bill from the database and verify deletion."""
    
    # Check if PostgreSQL is available
    if not is_postgres_available():
        logger.error("PostgreSQL database is not available. Cannot proceed.")
        return False
    
    test_bill_id = 'test-bill-123'
    
    try:
        with postgres_connect() as conn:
            with conn.cursor() as cursor:
                # First, check if the bill exists
                logger.info(f"Checking if bill '{test_bill_id}' exists...")
                cursor.execute(
                    "SELECT bill_id, title, summary_tweet, created_at FROM bills WHERE bill_id = %s",
                    (test_bill_id,)
                )
                bill = cursor.fetchone()
                
                if not bill:
                    logger.warning(f"Bill '{test_bill_id}' not found in database. Nothing to delete.")
                    return True
                
                logger.info(f"Found bill: {bill}")
                logger.info(f"  Bill ID: {bill[0]}")
                logger.info(f"  Title: {bill[1]}")
                logger.info(f"  Summary: {bill[2]}")
                logger.info(f"  Created At: {bill[3]}")
                
                # Delete the bill
                logger.info(f"Deleting bill '{test_bill_id}'...")
                cursor.execute(
                    "DELETE FROM bills WHERE bill_id = %s",
                    (test_bill_id,)
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
                    (test_bill_id,)
                )
                count = cursor.fetchone()[0]
                
                if count == 0:
                    logger.info(f"✓ Verification successful: Bill '{test_bill_id}' is no longer in the database")
                    return True
                else:
                    logger.error(f"✗ Verification failed: Bill '{test_bill_id}' still exists in database")
                    return False
                    
    except Exception as e:
        logger.error(f"Error deleting test bill: {e}")
        return False

if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("Starting test bill deletion script")
    logger.info("=" * 60)
    
    success = delete_test_bill()
    
    logger.info("=" * 60)
    if success:
        logger.info("✓ Test bill deletion completed successfully")
        sys.exit(0)
    else:
        logger.error("✗ Test bill deletion failed")
        sys.exit(1)