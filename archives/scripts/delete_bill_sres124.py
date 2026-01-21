#!/usr/bin/env python3
"""
Script to delete the sres124-119 bill from the database.
"""

import sys
import os
import logging

# Add src to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.load_env import load_env
from src.database.connection import postgres_connect
from src.database.db import get_db_connection


def delete_bill(bill_id: str) -> bool:
    """
    Delete a bill from the database.
    
    Args:
        bill_id: The bill ID to delete
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Get database connection
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Delete the bill
                cur.execute("DELETE FROM bills WHERE bill_id = %s", (bill_id,))
                
                # Check if any rows were affected
                if cur.rowcount > 0:
                    logging.info(f"Successfully deleted bill {bill_id}")
                    return True
                else:
                    logging.warning(f"No bill found with ID {bill_id}")
                    return False
    except Exception as e:
        logging.error(f"Error deleting bill {bill_id}: {e}")
        return False


def main():
    """Main function."""
    # Set up logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    
    # Bill ID to delete
    bill_id = "sres124-119"
    
    # Delete the bill
    success = delete_bill(bill_id)
    
    if success:
        print(f"Successfully deleted bill {bill_id}")
        return 0
    else:
        print(f"Failed to delete bill {bill_id}")
        return 1


if __name__ == "__main__":
    sys.exit(main())