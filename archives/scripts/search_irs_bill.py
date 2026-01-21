#!/usr/bin/env python3
"""
Script to search for the IRS bill on Congress.gov and add it to the database if found.
"""
import sys
import os
import requests

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Load environment variables
from src.load_env import load_env
load_env()

from src.database.connection import postgres_connect

def search_congress_for_irs_bill():
    """Search Congress.gov API for bills containing 'IRS' or 'Fair and Accountable'."""
    
    api_key = os.getenv('CONGRESS_API_KEY')
    if not api_key:
        print("❌ CONGRESS_API_KEY not found in environment")
        return []
    
    print("=" * 80)
    print("SEARCHING CONGRESS.GOV FOR IRS BILLS")
    print("=" * 80)
    
    # Search for bills with IRS in the title
    search_terms = [
        "Fair and Accountable IRS",
        "IRS Reviews",
        "Internal Revenue Service"
    ]
    
    all_results = []
    
    for term in search_terms:
        print(f"\n🔍 Searching for: '{term}'")
        
        url = "https://api.congress.gov/v3/bill"
        params = {
            'api_key': api_key,
            'format': 'json',
            'limit': 20,
            'sort': 'updateDate+desc'
        }
        
        try:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            bills = data.get('bills', [])
            print(f"   Retrieved {len(bills)} recent bills")
            
            # Filter for bills matching our search term
            matching_bills = []
            for bill in bills:
                title = bill.get('title', '').lower()
                if any(word in title for word in term.lower().split()):
                    matching_bills.append(bill)
                    print(f"   ✅ Found: {bill.get('type', '')}{bill.get('number', '')} - {bill.get('title', '')[:100]}...")
            
            all_results.extend(matching_bills)
            
        except Exception as e:
            print(f"   ❌ Error searching: {e}")
    
    return all_results

def check_database_for_bills(bill_ids):
    """Check if bills exist in the database."""
    if not bill_ids:
        return
    
    print("\n" + "=" * 80)
    print("CHECKING DATABASE FOR THESE BILLS")
    print("=" * 80)
    
    with postgres_connect() as conn:
        cursor = conn.cursor()
        
        for bill_id in bill_ids:
            cursor.execute("""
                SELECT bill_id, title, created_at, tweet_posted
                FROM bills 
                WHERE bill_id = %s
            """, (bill_id,))
            
            result = cursor.fetchone()
            if result:
                print(f"\n✅ {bill_id} EXISTS in database")
                print(f"   Title: {result[1][:100]}...")
                print(f"   Created: {result[2]}")
                print(f"   Tweeted: {result[3]}")
            else:
                print(f"\n❌ {bill_id} NOT in database")

if __name__ == "__main__":
    results = search_congress_for_irs_bill()
    
    if results:
        print(f"\n{'=' * 80}")
        print(f"FOUND {len(results)} MATCHING BILLS")
        print("=" * 80)
        
        bill_ids = []
        for bill in results:
            bill_type = bill.get('type', '').lower()
            bill_number = bill.get('number', '')
            congress = bill.get('congress', '')
            bill_id = f"{bill_type}{bill_number}-{congress}"
            bill_ids.append(bill_id)
            print(f"\n{bill_id}")
            print(f"  Title: {bill.get('title', '')}")
            print(f"  Latest Action: {bill.get('latestAction', {}).get('text', 'N/A')}")
            print(f"  Date: {bill.get('latestAction', {}).get('actionDate', 'N/A')}")
        
        check_database_for_bills(bill_ids)
    else:
        print("\n❌ No bills found matching search criteria")