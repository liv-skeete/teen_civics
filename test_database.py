#!/usr/bin/env python3
"""
Test script to verify database functionality.
"""

import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '.'))

from src.database.db import init_db, bill_exists, insert_bill, get_all_bills, update_tweet_info

def test_database():
    print("Testing database functionality...")
    
    # Initialize database (should create tables if not exists)
    init_db()
    
    # Test data
    test_bill = {
        "bill_id": "test-bill-123",
        "title": "Test Bill Title",
        "short_title": "Test Bill",
        "status": "Introduced",
        "summary_tweet": "This is a test tweet summary.",
        "summary_long": "This is a longer summary for the test bill.",
        "congress_session": "118th Congress, 1st Session",
        "date_introduced": "2023-01-01",
        "source_url": "https://www.congress.gov/bill/118th-congress/house-bill/123",
        "website_slug": "test-bill-123",
        "tags": "test, education",
        "tweet_posted": False,
        "tweet_url": None
    }
    
    # Check if bill exists (should not)
    exists = bill_exists(test_bill["bill_id"])
    print(f"Bill exists before insertion: {exists}")
    
    # Insert bill
    success = insert_bill(test_bill)
    print(f"Insertion successful: {success}")
    
    # Check if bill exists now (should be true)
    exists = bill_exists(test_bill["bill_id"])
    print(f"Bill exists after insertion: {exists}")
    
    # Try to insert again (should fail due to unique constraint)
    success_again = insert_bill(test_bill)
    print(f"Second insertion successful: {success_again} (should be False)")
    
    # Update tweet info
    update_success = update_tweet_info(test_bill["bill_id"], "https://twitter.com/user/status/123456")
    print(f"Tweet update successful: {update_success}")
    
    # Get all bills
    bills = get_all_bills()
    print(f"Number of bills in database: {len(bills)}")
    for bill in bills:
        print(f"Bill: {bill['bill_id']} - {bill['title']}")
    
    print("Database test completed.")

if __name__ == "__main__":
    test_database()