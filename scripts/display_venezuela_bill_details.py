#!/usr/bin/env python3
"""
Script to display detailed information about the Venezuela bill from the database.
"""

import sys
import os
import json

# Add src to path to import modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

def main():
    """
    Main function to display Venezuela bill details.
    """
    print("Displaying Venezuela Bill Details")
    print("=" * 40)
    
    # Import required functions
    try:
        from src.database.db import get_bill_by_id
        from src.load_env import load_env
        
        # Load environment variables
        load_env()
        
        # Get the actual Venezuela bill from the database
        bill_id = "sjres90-119"
        bill = get_bill_by_id(bill_id)
        
        if not bill:
            print(f"Could not find bill with ID '{bill_id}' in the database.")
            return 1
        
        print(f"Bill ID: {bill['bill_id']}")
        print(f"Title: {bill['title']}")
        print(f"Short Title: {bill.get('short_title', 'N/A')}")
        print(f"Status: {bill.get('status', 'N/A')}")
        print(f"Congress Session: {bill.get('congress_session', 'N/A')}")
        print(f"Date Introduced: {bill.get('date_introduced', 'N/A')}")
        print(f"Source URL: {bill.get('source_url', 'N/A')}")
        print(f"Website Slug: {bill.get('website_slug', 'N/A')}")
        print(f"Tweet Posted: {bill.get('tweet_posted', 'N/A')}")
        print(f"Tweet URL: {bill.get('tweet_url', 'N/A')}")
        print()
        
        print("Summary Texts:")
        print("-" * 20)
        if bill.get('summary_tweet'):
            print(f"Tweet Summary: {bill['summary_tweet']}")
        if bill.get('summary_overview'):
            print(f"Overview Summary: {bill['summary_overview']}")
        if bill.get('summary_long'):
            print(f"Long Summary: {bill['summary_long']}")
        print()
        
        print("Tags:")
        print("-" * 5)
        tags = bill.get('tags', [])
        if tags:
            if isinstance(tags, list):
                print(", ".join(tags))
            else:
                print(tags)
        else:
            print("No tags available")
        print()
        
        return 0
        
    except Exception as e:
        print(f"Error retrieving bill details: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())