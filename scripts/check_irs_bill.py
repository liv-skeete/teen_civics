#!/usr/bin/env python3
"""
Script to check if the IRS bill exists in the database and show latest bills.
"""
import sys
import os
from datetime import datetime

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Load environment variables
from src.load_env import load_env
load_env()

from src.database.connection import postgres_connect

def check_database():
    """Check for IRS bill and show latest bills in database."""
    with postgres_connect() as conn:
        cursor = conn.cursor()
        
        print("=" * 80)
        print("CHECKING FOR IRS BILL")
        print("=" * 80)
        
        # Check for IRS bill
        cursor.execute("""
            SELECT bill_id, title, created_at
            FROM bills
            WHERE title LIKE '%IRS%' OR title LIKE '%Fair and Accountable%'
            ORDER BY created_at DESC
        """)
        irs_bills = cursor.fetchall()
        
        if irs_bills:
            print(f"\nFound {len(irs_bills)} bill(s) matching IRS/Fair and Accountable:")
            for bill in irs_bills:
                print(f"  - {bill[0]}: {bill[1]}")
                print(f"    Created: {bill[2]}")
        else:
            print("\n❌ No bills found matching 'IRS' or 'Fair and Accountable'")
        
        print("\n" + "=" * 80)
        print("LATEST BILLS IN DATABASE")
        print("=" * 80)
        
        # Get latest bills
        cursor.execute("""
            SELECT bill_id, title, created_at
            FROM bills
            ORDER BY created_at DESC
            LIMIT 10
        """)
        latest_bills = cursor.fetchall()
        
        if latest_bills:
            print(f"\nFound {len(latest_bills)} most recent bills:")
            for i, bill in enumerate(latest_bills, 1):
                print(f"\n{i}. {bill[0]}: {bill[1]}")
                print(f"   Created: {bill[2]}")
        else:
            print("\n❌ No bills found in database")
        
        # Get total count
        cursor.execute("SELECT COUNT(*) FROM bills")
        total = cursor.fetchone()[0]
        print(f"\n{'=' * 80}")
        print(f"TOTAL BILLS IN DATABASE: {total}")
        print("=" * 80)
        
        return len(irs_bills) > 0
    

if __name__ == "__main__":
    has_irs_bill = check_database()
    sys.exit(0 if has_irs_bill else 1)