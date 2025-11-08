#!/usr/bin/env python3
"""
Script to find and delete the most recent bill about the Medal of Honor from the database.
"""

import os
import sys
import logging

# Add the project root to the Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

from src.database.db_utils import search_bills_by_title, get_bill_by_id
from src.load_env import load_env
from scripts.delete_bill import delete_bill

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def find_medal_of_honor_bills():
    """Find all bills with 'Medal of Honor' in the title, sorted by date."""
    logger.info("Searching for bills with 'Medal of Honor' in the title...")
    bills = search_bills_by_title("Medal of Honor", limit=10)
    
    if not bills:
        logger.info("No bills found with 'Medal of Honor' in the title.")
        return []
    
    logger.info(f"Found {len(bills)} bill(s) with 'Medal of Honor' in the title.")
    for i, bill in enumerate(bills):
        logger.info(f"{i+1}. {bill['bill_id']} - {bill['title']} (Processed: {bill['date_processed']})")
    
    return bills

def main():
    """Main function to find and delete the most recent Medal of Honor bill."""
    load_env()
    
    # Find bills
    bills = find_medal_of_honor_bills()
    
    if not bills:
        logger.info("No Medal of Honor bills found. Nothing to delete.")
        return True
    
    # Get the most recent bill (first in the list as they are sorted by date_processed DESC)
    most_recent_bill = bills[0]
    bill_id = most_recent_bill['bill_id']
    
    logger.info(f"Most recent Medal of Honor bill: {bill_id}")
    logger.info(f"Title: {most_recent_bill['title']}")
    logger.info(f"Processed date: {most_recent_bill['date_processed']}")
    
    # Ask for confirmation before deleting
    response = input(f"\nDo you want to delete bill '{bill_id}'? This action cannot be undone. (yes/no): ")
    
    if response.lower() not in ['yes', 'y']:
        logger.info("Deletion cancelled by user.")
        return True
    
    # Delete the bill
    logger.info(f"Deleting bill '{bill_id}'...")
    success = delete_bill(bill_id)
    
    if success:
        logger.info(f"Successfully deleted bill '{bill_id}'.")
        # Verify deletion
        logger.info("Verifying deletion...")
        deleted_bill = get_bill_by_id(bill_id)
        if deleted_bill is None:
            logger.info("✓ Verification successful: Bill is no longer in the database.")
            return True
        else:
            logger.error("✗ Verification failed: Bill still exists in database.")
            return False
    else:
        logger.error(f"Failed to delete bill '{bill_id}'.")
        return False

if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("Find and Delete Medal of Honor Bill Script")
    logger.info("=" * 60)
    
    try:
        success = main()
        
        logger.info("=" * 60)
        if success:
            logger.info("✓ Script completed successfully")
            sys.exit(0)
        else:
            logger.error("✗ Script failed")
            sys.exit(1)
    except KeyboardInterrupt:
        logger.info("\nScript interrupted by user.")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)