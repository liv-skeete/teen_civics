#!/usr/bin/env python3
"""
Database cleanup script to remove test bills.
This script connects to the database and deletes any bill where:
- The bill_id is 'hr9999-119'
- The title contains "Test Bill"
"""

import os
import sys
import logging
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.database.db import init_db, get_all_bills
from src.database.connection import postgres_connect
import psycopg2
import psycopg2.extras

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def find_test_bills():
    """Find all test bills in the database."""
    try:
        init_db()
        bills = get_all_bills(limit=1000)  # Get all bills
        test_bills = []
        
        for bill in bills:
            bill_id = bill.get("bill_id", "")
            title = bill.get("title", "")
            
            # Check if it's a test bill
            if bill_id == 'hr9999-119' or 'test bill' in title.lower():
                test_bills.append(bill)
                
        return test_bills
    except Exception as e:
        logger.error(f"Error finding test bills: {e}")
        return []

def delete_test_bills():
    """Delete test bills from the database after user confirmation."""
    try:
        # Find test bills
        test_bills = find_test_bills()
        
        if not test_bills:
            logger.info("No test bills found in the database.")
            return True
            
        # Display found test bills
        logger.info(f"Found {len(test_bills)} test bills:")
        for bill in test_bills:
            logger.info(f"  - ID: {bill['bill_id']}, Title: {bill['title']}")
            
        # Ask for user confirmation
        confirmation = input("\nAre you sure you want to delete these test bills from the database? (yes/no): ")
        
        if confirmation.lower() != 'yes':
            logger.info("Operation cancelled by user.")
            return True
            
        # Delete the test bills
        deleted_count = 0
        with postgres_connect() as conn:
            with conn.cursor() as cursor:
                for bill in test_bills:
                    bill_id = bill['bill_id']
                    cursor.execute("DELETE FROM bills WHERE bill_id = %s", (bill_id,))
                    if cursor.rowcount > 0:
                        deleted_count += 1
                        logger.info(f"Deleted bill {bill_id}")
                        
        logger.info(f"Successfully deleted {deleted_count} test bills from the database.")
        return True
        
    except Exception as e:
        logger.error(f"Error deleting test bills: {e}")
        return False

if __name__ == "__main__":
    success = delete_test_bills()
    if success:
        logger.info("Database cleanup completed successfully.")
        sys.exit(0)
    else:
        logger.error("Database cleanup failed.")
        sys.exit(1)