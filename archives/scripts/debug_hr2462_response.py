#!/usr/bin/env python3
"""
Debug script to see what the Anthropic API is actually returning for HR.2462
"""

import sys
sys.path.insert(0, 'src')

from database.db import get_bill_by_id
from processors.summarizer import _build_enhanced_prompt, _model_call_with_fallback, _try_parse_json_with_fallback
from anthropic import Anthropic
import os
from dotenv import load_dotenv
import json

load_dotenv()

def main():
    bill_id = "hr2462-119"
    
    print(f"Fetching bill data for {bill_id}...")
    bill = get_bill_by_id(bill_id)
    
    if not bill:
        print(f"ERROR: Bill {bill_id} not found")
        return 1
    
    print(f"\nBill: {bill['title']}")
    print(f"Has full_text: {bool(bill.get('full_text'))}")
    
    # Build the prompt
    system, user = _build_enhanced_prompt(bill)
    
    print("\n" + "="*80)
    print("SYSTEM PROMPT (first 500 chars):")
    print("="*80)
    print(system[:500])
    
    print("\n" + "="*80)
    print("USER PROMPT (first 1000 chars):")
    print("="*80)
    print(user[:1000])
    
    # Call the API
    print("\n" + "="*80)
    print("CALLING ANTHROPIC API...")
    print("="*80)
    
    client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    raw_response = _model_call_with_fallback(client, system, user)
    
    print("\n" + "="*80)
    print("RAW API RESPONSE:")
    print("="*80)
    print(raw_response)
    
    print("\n" + "="*80)
    print("PARSED JSON:")
    print("="*80)
    parsed = _try_parse_json_with_fallback(raw_response)
    print(json.dumps(parsed, indent=2))
    
    print("\n" + "="*80)
    print("EXTRACTED FIELDS:")
    print("="*80)
    print(f"overview: {repr(parsed.get('overview', ''))[:200]}")
    print(f"detailed: {repr(parsed.get('detailed', ''))[:200]}")
    print(f"tweet: {repr(parsed.get('tweet', ''))[:200]}")
    print(f"term_dictionary: {parsed.get('term_dictionary', [])}")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())