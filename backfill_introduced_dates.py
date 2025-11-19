#!/usr/bin/env python3
"""Backfill missing date_introduced fields by querying Congress.gov API."""

import os
import re
import requests
import time
os.environ['FLASK_APP'] = 'app.py'

from app import app
from src.database.db import get_all_bills, db_connect

# Get API key
CONGRESS_API_KEY = os.getenv('CONGRESS_API_KEY')
if not CONGRESS_API_KEY:
    print("❌ CONGRESS_API_KEY environment variable not set")
    exit(1)

def parse_bill_id(bill_id: str):
    """Parse bill_id into components: hr6068-119 -> ('hr', '6068', '119')"""
    match = re.match(r'^([a-z]+)(\d+)-(\d+)$', bill_id, re.IGNORECASE)
    if match:
        return match.groups()
    return None, None, None

def fetch_introduced_date(bill_type: str, bill_number: str, congress: str) -> str:
    """Fetch introducedDate from Congress.gov API."""
    url = f"https://api.congress.gov/v3/bill/{congress}/{bill_type}/{bill_number}"
    params = {
        'api_key': CONGRESS_API_KEY,
        'format': 'json'
    }
    
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        bill_data = data.get('bill', {})
        introduced_date = bill_data.get('introducedDate')
        
        if introduced_date:
            print(f"  ✅ Found: {introduced_date}")
            return introduced_date
        else:
            print(f"  ⚠️ API returned no introducedDate")
            return None
            
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return None

with app.app_context():
    bills = get_all_bills(limit=100)
    
    bills_to_update = [b for b in bills if not b.get('date_introduced')]
    
    print(f"\n=== Found {len(bills_to_update)} bills with missing date_introduced ===\n")
    
    if not bills_to_update:
        print("✅ All bills already have date_introduced!")
        exit(0)
    
    updated_count = 0
    failed_count = 0
    
    with db_connect() as conn:
        with conn.cursor() as cur:
            for bill in bills_to_update:
                bill_id = bill['bill_id']
                bill_type, bill_number, congress = parse_bill_id(bill_id)
                
                if not all([bill_type, bill_number, congress]):
                    print(f"⚠️ Skipping {bill_id} - invalid format")
                    failed_count += 1
                    continue
                
                print(f"Fetching date for {bill_id}...", end=" ")
                introduced_date = fetch_introduced_date(bill_type, bill_number, congress)
                
                if introduced_date:
                    cur.execute(
                        'UPDATE bills SET date_introduced = %s WHERE bill_id = %s',
                        (introduced_date, bill_id)
                    )
                    updated_count += 1
                else:
                    failed_count += 1
                
                # Rate limit to be nice to the API
                time.sleep(0.5)
        
        conn.commit()
    
    print(f"\n=== Backfill Complete ===")
    print(f"✅ Updated: {updated_count}")
    print(f"❌ Failed: {failed_count}")
