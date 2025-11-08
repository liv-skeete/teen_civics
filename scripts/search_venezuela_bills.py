#!/usr/bin/env python3
"""
Search script to find Venezuela-related bills in the database.
"""

import os
import sys
import logging

# Add the project root to the Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

from src.database.db import get_all_bills
from src.database.connection import get_connection_string
from src.load_env import load_env

logging.basicConfig(level=logging.INFO)

def main():
    load_env()
    logging.info("Searching for Venezuela-related bills...")
    
    # Ensure the database connection is configured
    if not get_connection_string():
        logging.error("Database connection not configured. Please set DATABASE_URL or Supabase environment variables.")
        return
    
    # Get all bills and filter for Venezuela-related ones
    try:
        all_bills = get_all_bills()
        print(f"Total bills in database: {len(all_bills)}")
        
        # Filter for Venezuela-related bills
        venezuela_bills = []
        for bill in all_bills:
            if bill is None:
                continue
                
            title = bill.get('title', '') or ''
            tags = bill.get('tags', []) or []
            slug = bill.get('website_slug', '') or ''
            
            if 'venezuela' in title.lower() or 'venezuela' in slug.lower() or any('venezuela' in (tag or '').lower() for tag in tags):
                venezuela_bills.append(bill)
        
        print(f"Found {len(venezuela_bills)} Venezuela-related bills:")
        
        for bill in venezuela_bills:
            print(f"  - Bill ID: {bill['bill_id']}")
            print(f"    Title: {bill['title']}")
            print(f"    Slug: {bill.get('website_slug', 'N/A')}")
            print(f"    Tweeted: {bill.get('tweet_posted', False)}")
            print(f"    Tags: {bill.get('tags', [])}")
            print()
            
        if len(venezuela_bills) == 0:
            print("No Venezuela-related bills found in the database.")
                
    except Exception as e:
        logging.error(f"Error searching for Venezuela bills: {e}")
        import traceback
        traceback.print_exc()
        return

if __name__ == "__main__":
    main()