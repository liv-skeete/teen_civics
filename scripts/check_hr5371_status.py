#!/usr/bin/env python3
"""
Script to check the status of hr5371-119 in the database
"""

import sqlite3
import json
import os
import sys

# Add the project root to the Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

from src.database.db import get_bill_by_id

def check_hr5371_status():
    """Check the status of hr5371-119 in the database"""
    try:
        bill = get_bill_by_id('hr5371-119')
        if bill:
            print("=== hr5371-119 Data ===")
            print(f"Bill ID: {bill['bill_id']}")
            print(f"Title: {bill['title']}")
            print(f"Normalized Status: {bill['normalized_status']}")
            print(f"Raw Latest Action: {bill['raw_latest_action']}")
            print(f"Tracker Raw: {bill['tracker_raw']}")
            
            # Try to parse the tracker_raw as JSON
            try:
                tracker_data = json.loads(bill['tracker_raw'])
                print(f"Tracker Data Parsed: {tracker_data}")
            except json.JSONDecodeError:
                print("Tracker Raw is not valid JSON")
        else:
            print("hr5371-119 not found in database!")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_hr5371_status()