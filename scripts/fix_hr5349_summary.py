#!/usr/bin/env python3
"""
Fix the Tax Court Improvement Act (hr5349-119) summary.
This bill currently has no summaries, making it unhelpful for teens.
"""

import os
import sys

# Ensure src is on the path for local module imports
sys.path.insert(0, 'src')

# Load environment variables (including DATABASE_URL) from .env or Supabase vars
from load_env import load_env
load_env()

from database.db import get_bill_by_id, update_bill_summaries
from processors.summarizer import summarize_bill_enhanced

def main():
    bill_id = 'hr5349-119'
    
    print(f"=== Fixing {bill_id} Summary ===\n")
    
    # Get the bill from database
    print("1. Fetching bill from database...")
    bill = get_bill_by_id(bill_id)
    
    if not bill:
        print(f"ERROR: Bill {bill_id} not found in database!")
        return 1
    
    print(f"   ✓ Found: {bill['title']}")
    print(f"   Status: {bill['status']}")
    print(f"   Full text length: {len(bill.get('full_text', ''))} chars")
    
    # Check current summaries
    print("\n2. Current summaries:")
    print(f"   Short: {bill.get('short_summary', 'N/A')[:100]}...")
    print(f"   Long: {bill.get('long_summary', 'N/A')[:100]}...")
    
    # Get full text
    full_text = bill.get('full_text', '')
    if not full_text:
        print("\nERROR: No full text available to summarize!")
        return 1
    
    print(f"\n3. Generating new teen-friendly summaries...")
    print("   (This may take a moment...)")
    
    # Generate new summaries
    try:
        summary_result = summarize_bill_enhanced(bill)
        
        if not summary_result:
            print("\nERROR: Summarizer returned None!")
            return 1
        
        # The summarizer returns 'tweet' and 'long', not 'short_summary' and 'long_summary'
        short_summary = summary_result.get('tweet', '')
        long_summary = summary_result.get('long', '')
        
        if not short_summary or not long_summary:
            print("\nERROR: Summaries are empty!")
            print(f"Tweet (short): {short_summary}")
            print(f"Long: {long_summary}")
            print(f"Available keys: {list(summary_result.keys())}")
            return 1
        
        print(f"   ✓ Generated tweet/short summary ({len(short_summary)} chars)")
        print(f"   ✓ Generated long summary ({len(long_summary)} chars)")
        
        # Update database
        print("\n4. Updating database...")
        success = update_bill_summaries(bill_id, short_summary, long_summary)
        
        if success:
            print("   ✓ Database updated successfully!")
        else:
            print("   ✗ Failed to update database")
            return 1
        
        # Show preview of new summaries
        print("\n5. New summaries preview:")
        print("\n--- SHORT SUMMARY ---")
        print(short_summary)
        print("\n--- LONG SUMMARY ---")
        print(long_summary)
        
        print(f"\n✓ SUCCESS! {bill_id} has been fixed.")
        print(f"View at: http://127.0.0.1:5001/bill/hr5349-119-court-improvement")
        
        return 0
        
    except Exception as e:
        print(f"\nERROR during summarization: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == '__main__':
    sys.exit(main())