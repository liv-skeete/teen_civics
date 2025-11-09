#!/usr/bin/env python3
"""
Script to find all bills in the database that contain the phrase "full bill text" 
in any of their summary fields, which indicates they were not properly generated 
due to missing text.
"""

import os
import sys
import logging
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.database.connection import postgres_connect

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def find_incomplete_summaries():
    """Find all bills with incomplete summaries containing 'full bill text'."""
    
    # Check if DATABASE_URL is set
    if not os.environ.get('DATABASE_URL'):
        logger.error("DATABASE_URL environment variable not set.")
        return
    
    try:
        incomplete_bills = []
        
        with postgres_connect() as conn:
            with conn.cursor() as cursor:
                # Query for bills where any summary field contains "full bill text"
                cursor.execute("""
                    SELECT bill_id, 
                           summary_overview, 
                           summary_detailed, 
                           summary_tweet
                    FROM bills 
                    WHERE COALESCE(summary_overview, '') ILIKE %s 
                       OR COALESCE(summary_detailed, '') ILIKE %s 
                       OR COALESCE(summary_tweet, '') ILIKE %s
                """, ('%full bill text%', '%full bill text%', '%full bill text%'))
                
                rows = cursor.fetchall()
                
                for row in rows:
                    bill_id, overview, detailed, tweet = row
                    bill_info = {
                        'bill_id': bill_id,
                        'incomplete_fields': []
                    }
                    
                    # Check which fields contain the phrase
                    if overview and 'full bill text' in overview.lower():
                        bill_info['incomplete_fields'].append('summary_overview')
                    
                    if detailed and 'full bill text' in detailed.lower():
                        bill_info['incomplete_fields'].append('summary_detailed')
                    
                    if tweet and 'full bill text' in tweet.lower():
                        bill_info['incomplete_fields'].append('summary_tweet')
                    
                    incomplete_bills.append(bill_info)
        
        # Display results
        print("=" * 80)
        print("INCOMPLETE SUMMARY REPORT")
        print("=" * 80)
        print(f"Total bills with incomplete summaries: {len(incomplete_bills)}")
        print()
        
        if incomplete_bills:
            print("Bills with incomplete summaries:")
            print("-" * 50)
            for bill in incomplete_bills:
                print(f"Bill ID: {bill['bill_id']}")
                print(f"  Incomplete fields: {', '.join(bill['incomplete_fields'])}")
                print()
        else:
            print("✅ No bills with incomplete summaries found!")
        
        print("=" * 80)
        return incomplete_bills
        
    except Exception as e:
        logger.error(f"Error finding incomplete summaries: {e}")
        return []

def main():
    logger.info("Starting incomplete summaries search...")
    bills = find_incomplete_summaries()
    logger.info("Search completed.")
    
    # Exit with error code if there are incomplete summaries
    if bills:
        sys.exit(1)  # Exit with error code to indicate issues found
    else:
        sys.exit(0)  # Exit successfully if no issues found

if __name__ == "__main__":
    main()