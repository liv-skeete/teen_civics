#!/usr/bin/env python3
"""Fix bills with missing congress_session or date_introduced data."""

import os
import re
os.environ['FLASK_APP'] = 'app.py'

from app import app
from src.database.db import get_all_bills
from src.database.connection import postgres_connect

def extract_congress_from_bill_id(bill_id: str) -> str:
    """Extract congress number from bill_id like 'hr6068-119'."""
    match = re.search(r'-(\d+)$', bill_id)
    if match:
        return match.group(1)
    return ""

def update_bill_congress(bill_id: str, congress: str):
    """Update a bill's congress_session in the database."""
    try:
        with postgres_connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    'UPDATE bills SET congress_session = %s WHERE bill_id = %s',
                    (congress, bill_id)
                )
                conn.commit()
                return True
    except Exception as e:
        print(f"Error updating bill {bill_id}: {e}")
        return False

with app.app_context():
    bills = get_all_bills(limit=50)
    
    print("\n=== Fixing bills with missing congress_session ===\n")
    fixed_count = 0
    
    for bill in bills:
        bill_id = bill['bill_id']
        congress = bill.get('congress_session')
        
        if not congress or congress.strip() == '':
            # Extract congress from bill_id
            extracted_congress = extract_congress_from_bill_id(bill_id)
            
            if extracted_congress:
                print(f"Fixing {bill_id}: setting congress_session to {extracted_congress}")
                if update_bill_congress(bill_id, extracted_congress):
                    fixed_count += 1
                    print(f"  ✅ Updated")
                else:
                    print(f"  ❌ Failed to update")
            else:
                print(f"⚠️  Could not extract congress from bill_id: {bill_id}")
    
    print(f"\n✅ Fixed {fixed_count} bills")
    print("\nNote: date_introduced field requires API data and cannot be backfilled from bill_id alone.")
    print("The orchestrator will populate this field correctly for all future bills.")
