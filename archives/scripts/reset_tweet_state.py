#!/usr/bin/env python3
"""
Script to reset the tweet state for a given bill.
This is useful when a tweet has been manually deleted from Twitter
but the database still shows it as posted.
"""

import sys
import os
import argparse
import logging

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from src.database.db import get_db_connection, normalize_bill_id


def reset_tweet_state(bill_id: str) -> bool:
    """
    Reset the tweet state for a bill.
    
    Args:
        bill_id: The bill ID to reset
        
    Returns:
        True if successful, False otherwise
    """
    # Normalize the bill ID
    normalized_bill_id = normalize_bill_id(bill_id)
    
    try:
        # Get database connection
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Update the bill to reset tweet state
                cur.execute("""
                    UPDATE bills 
                    SET tweet_posted = FALSE, tweet_url = NULL 
                    WHERE bill_id = %s
                """, (normalized_bill_id,))
                
                # Check if any rows were affected
                if cur.rowcount > 0:
                    logging.info(f"Successfully reset tweet state for bill {normalized_bill_id}")
                    return True
                else:
                    logging.warning(f"No bill found with ID {normalized_bill_id}")
                    return False
    except Exception as e:
        logging.error(f"Error resetting tweet state for bill {normalized_bill_id}: {e}")
        return False


def main():
    """Main function."""
    # Set up logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Reset tweet state for a bill")
    parser.add_argument("bill_id", help="The bill ID to reset (e.g., hr1234-119)")
    args = parser.parse_args()
    
    # Reset the tweet state
    success = reset_tweet_state(args.bill_id)
    
    if success:
        print(f"Successfully reset tweet state for bill {args.bill_id}")
        return 0
    else:
        print(f"Failed to reset tweet state for bill {args.bill_id}")
        return 1


if __name__ == "__main__":
    sys.exit(main())