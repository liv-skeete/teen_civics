#!/usr/bin/env python3
"""
Diagnostic test script for congress_fetcher.py
Tests the bill text download functionality to identify why texts are not being downloaded.
"""

import sys
import logging
from src.fetchers.congress_fetcher import get_recent_bills, fetch_bills_from_feed

# Configure detailed logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def main():
    """Run diagnostic tests on the congress fetcher"""
    
    print("=" * 80)
    print("CONGRESS FETCHER DIAGNOSTIC TEST")
    print("=" * 80)
    print()
    
    # Test 1: Fetch bills with text enabled
    print("TEST 1: Fetching bills with include_text=True")
    print("-" * 80)
    
    try:
        bills = get_recent_bills(limit=3, include_text=True, text_chars=15000)
        
        print(f"\n✓ Successfully fetched {len(bills)} bills")
        print()
        
        if not bills:
            print("⚠️  WARNING: No bills were returned from the feed!")
            print()
        
        # Analyze each bill
        for i, bill in enumerate(bills, 1):
            print(f"\nBILL {i}: {bill.get('bill_id', 'UNKNOWN')}")
            print("-" * 40)
            print(f"  Title: {bill.get('title', 'N/A')[:80]}...")
            print(f"  Text URL: {bill.get('text_url', 'N/A')}")
            print(f"  Text Version: {bill.get('text_version', 'N/A')}")
            print(f"  Text Source: {bill.get('text_source', 'N/A')}")
            
            # Check if full_text exists and its length
            full_text = bill.get('full_text', '')
            if full_text:
                print(f"  ✓ Full Text: {len(full_text)} characters")
                print(f"  First 200 chars: {full_text[:200]}...")
            else:
                print(f"  ✗ Full Text: EMPTY or MISSING")
            
            print()
        
        # Summary
        print("\n" + "=" * 80)
        print("SUMMARY")
        print("=" * 80)
        
        bills_with_text = sum(1 for b in bills if b.get('full_text') and len(b.get('full_text', '').strip()) > 100)
        bills_without_text = len(bills) - bills_with_text
        
        print(f"Total bills fetched: {len(bills)}")
        print(f"Bills WITH text (>100 chars): {bills_with_text}")
        print(f"Bills WITHOUT text: {bills_without_text}")
        
        if bills_without_text > 0:
            print("\n⚠️  ISSUE DETECTED: Some bills are missing text content!")
            print("\nBills without text:")
            for bill in bills:
                if not bill.get('full_text') or len(bill.get('full_text', '').strip()) <= 100:
                    print(f"  - {bill.get('bill_id', 'UNKNOWN')}")
                    print(f"    Text URL: {bill.get('text_url', 'N/A')}")
        else:
            print("\n✓ All bills have text content!")
        
    except Exception as e:
        print(f"\n✗ ERROR: Test failed with exception:")
        print(f"  {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    print("\n" + "=" * 80)
    print("TEST COMPLETE")
    print("=" * 80)
    
    return 0

if __name__ == "__main__":
    sys.exit(main())