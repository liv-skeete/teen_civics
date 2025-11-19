#!/usr/bin/env python3
"""Check for bills with missing congress_session or date_introduced fields."""

import os
os.environ['FLASK_APP'] = 'app.py'

from app import app
from src.database.db import get_all_bills

with app.app_context():
    bills = get_all_bills(limit=10)
    
    print("\n=== Checking first 10 bills for missing data ===\n")
    for bill in bills:
        congress = bill.get('congress_session')
        date_intro = bill.get('date_introduced')
        
        congress_display = congress if congress else "MISSING"
        date_display = date_intro if date_intro else "MISSING"
        
        print(f"Bill: {bill['bill_id']}")
        print(f"  Congress Session: {congress_display}")
        print(f"  Date Introduced: {date_display}")
        print(f"  Date Processed: {bill.get('date_processed')}")
        print()
