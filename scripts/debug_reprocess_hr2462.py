#!/usr/bin/env python3
"""
Debug version of reprocess script with detailed logging
"""

import sys
sys.path.insert(0, 'src')

from src.load_env import load_env
load_env()

from database.db import get_bill_by_id
from processors.summarizer import summarize_bill_enhanced
import json

def main():
    bill_id = "hr2462-119"
    
    print(f"Fetching bill data for {bill_id}...")
    bill = get_bill_by_id(bill_id)
    
    if not bill:
        print(f"ERROR: Bill {bill_id} not found in database")
        return 1
    
    print(f"\nBill found: {bill['title']}")
    print(f"Has full_text: {bool(bill.get('full_text'))}")
    if bill.get('full_text'):
        print(f"Full text length: {len(bill['full_text'])} characters")
    
    print("\n" + "="*80)
    print("CALLING summarize_bill_enhanced...")
    print("="*80 + "\n")
    
    # Regenerate the summary
    summary_result = summarize_bill_enhanced(bill)
    
    print("\n" + "="*80)
    print("RAW RESULT FROM summarize_bill_enhanced:")
    print("="*80)
    print(f"Type: {type(summary_result)}")
    print(f"Result: {summary_result}")
    print()
    
    if not summary_result:
        print("ERROR: summarize_bill_enhanced returned None or empty")
        return 1
    
    print("="*80)
    print("EXTRACTED FIELDS:")
    print("="*80)
    
    for key in ['tweet', 'long', 'overview', 'detailed', 'term_dictionary']:
        value = summary_result.get(key, '<KEY NOT FOUND>')
        print(f"\n{key}:")
        print(f"  Type: {type(value)}")
        print(f"  Length: {len(str(value)) if value else 0}")
        print(f"  Value: {value[:200] if value else '<EMPTY>'}...")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())