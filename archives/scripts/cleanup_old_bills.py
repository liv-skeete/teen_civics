#!/usr/bin/env python3
"""
Script to remove all old bills from the database except for specific ones.
This is used to avoid incurring costs by reprocessing all old bill summaries.
"""

import os
import sys
import logging
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.database.connection import postgres_connect, is_postgres_available

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Bills to keep - these will not be deleted
BILLS_TO_KEEP = ['hr998-119', 'hres825-119']

def get_all_bill_ids():
    """Get all bill IDs from the database."""
    if not is_postgres_available():
        logger.error("PostgreSQL database is not available.")
        return []
    
    try:
        with postgres_connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT bill_id FROM bills ORDER BY date_processed")
                return [row[0] for row in cursor.fetchall()]
    except Exception as e:
        logger.error(f"Error fetching bill IDs: {e}")
        return []

def delete_bills_except(keep_bill_ids):
    """Delete all bills except those in the keep_bill_ids list."""
    
    # Check if PostgreSQL is available
    if not is_postgres_available():
        logger.error("PostgreSQL database is not available. Cannot proceed.")
        return False
    
    try:
        # Get all bill IDs
        all_bill_ids = get_all_bill_ids()
        if not all_bill_ids:
            logger.info("No bills found in database.")
            return True
            
        logger.info(f"Found {len(all_bill_ids)} bills in database")
        
        # Determine which bills to delete
        bills_to_delete = [bill_id for bill_id in all_bill_ids if bill_id not in keep_bill_ids]
        
        if not bills_to_delete:
            logger.info("No bills to delete. All existing bills are in the keep list.")
            return True
            
        logger.info(f"Will delete {len(bills_to_delete)} bills")
        logger.info(f"Will keep {len(keep_bill_ids)} bills: {keep_bill_ids}")
        
        # Ask for user confirmation
        print("\n" + "="*60)
        print("DANGER: BILL DELETION SCRIPT")
        print("="*60)
        print(f"This will DELETE {len(bills_to_delete)} bills from the database!")
        print(f"These bills will be KEPT: {keep_bill_ids}")
        print("This action cannot be undone.")
        print("="*60)
        
        confirmation = input("\nAre you sure you want to proceed? Type 'DELETE' to confirm: ")
        
        if confirmation != 'DELETE':
            logger.info("Deletion cancelled by user.")
            return False
            
        # Delete the bills
        deleted_count = 0
        with postgres_connect() as conn:
            with conn.cursor() as cursor:
                for bill_id in bills_to_delete:
                    try:
                        logger.info(f"Deleting bill {bill_id}...")
                        cursor.execute("DELETE FROM bills WHERE bill_id = %s", (bill_id,))
                        if cursor.rowcount > 0:
                            deleted_count += 1
                            logger.info(f"✓ Deleted bill {bill_id}")
                        else:
                            logger.warning(f"⚠ No rows deleted for bill {bill_id}")
                    except Exception as e:
                        logger.error(f"Error deleting bill {bill_id}: {e}")
                        continue
        
        logger.info(f"Successfully deleted {deleted_count} bills from the database.")
        
        # Verify the bills we wanted to keep are still there
        with postgres_connect() as conn:
            with conn.cursor() as cursor:
                for bill_id in keep_bill_ids:
                    cursor.execute("SELECT COUNT(*) FROM bills WHERE bill_id = %s", (bill_id,))
                    count = cursor.fetchone()[0]
                    if count > 0:
                        logger.info(f"✓ Verified bill {bill_id} is still in database")
                    else:
                        logger.warning(f"⚠ Bill {bill_id} that we wanted to keep is no longer in database")
        
        return True
                    
    except Exception as e:
        logger.error(f"Error deleting bills: {e}")
        return False

def main():
    logger.info("=" * 60)
    logger.info("Starting old bills cleanup script")
    logger.info("=" * 60)
    
    success = delete_bills_except(BILLS_TO_KEEP)
    
    logger.info("=" * 60)
    if success:
        logger.info("✓ Old bills cleanup completed successfully")
        sys.exit(0)
    else:
        logger.error("✗ Old bills cleanup failed")
        sys.exit(1)

if __name__ == "__main__":
    main()