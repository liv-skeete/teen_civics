#!/usr/bin/env python3
"""
Script to check the data for a specific bill in the database.
"""

import sys
import os
import json

# Add project root to path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

from src.database.db import get_bill_by_id

def main(bill_id):
    print(f"Checking data for bill {bill_id}...")
    
    try:
        bill = get_bill_by_id(bill_id)
        if not bill:
            print(f"Bill {bill_id} not found in database")
            return
            
        print("Bill data:")
        print(f"  Bill ID: {bill.get('bill_id')}")
        print(f"  Title: {bill.get('title')}")
        print(f"  Source URL: {bill.get('source_url')}")
        print(f"  Congress Session: {bill.get('congress_session')}")
        print(f"  Date Introduced: {bill.get('date_introduced')}")
        print(f"  Raw Latest Action: {bill.get('raw_latest_action')}")
        print(f"  Normalized Status: {bill.get('normalized_status')}")
        print(f"  Status: {bill.get('status')}")
        
        # Pretty print tracker data if it exists
        tracker_raw = bill.get('tracker_raw')
        if tracker_raw and tracker_raw != 'null':
            try:
                tracker_data = json.loads(tracker_raw)
                print("  Tracker Data:")
                for i, step in enumerate(tracker_data):
                    print(f"    {i+1}. {step.get('name')} {'(selected)' if step.get('selected') else ''}")
            except json.JSONDecodeError:
                print(f"  Tracker Raw: {tracker_raw}")
        else:
            print("  Tracker Data: None")
            
    except Exception as e:
        print(f"Error checking data for {bill_id}: {e}")
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python3 check_bill_data.py <bill_id>")
        sys.exit(1)
        
    main(sys.argv[1])