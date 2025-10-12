#!/usr/bin/env python3
"""
Final demonstration: Fetch 5 bills from Congress.gov API and show first 50 words of text.
"""

import sys
from src.fetchers.congress_fetcher import get_recent_bills

def main():
    print("=" * 80)
    print("FINAL DEMONSTRATION: Bill Text Extraction from Congress.gov")
    print("=" * 80)
    print()
    
    # Fetch 5 recent bills with text
    print("Fetching 5 recent bills with full text...")
    print()
    
    bills = get_recent_bills(limit=5, include_text=True)
    
    if not bills:
        print("❌ No bills fetched")
        return 1
    
    print(f"✅ Successfully fetched {len(bills)} bills")
    print("=" * 80)
    print()
    
    # Display each bill with first 50 words
    for i, bill in enumerate(bills, 1):
        bill_id = bill.get('bill_id', 'unknown')
        title = bill.get('title', 'No title')
        text_source = bill.get('text_source', 'unknown')
        full_text = bill.get('full_text', '')
        
        print(f"Bill {i}: {bill_id}")
        print(f"Title: {title[:80]}...")
        print(f"Source: {text_source}")
        print("-" * 80)
        
        if full_text and len(full_text.strip()) > 0:
            # Clean up HTML tags for better readability
            import re
            clean_text = re.sub(r'<[^>]+>', ' ', full_text)
            clean_text = re.sub(r'\s+', ' ', clean_text).strip()
            
            # Get first 50 words
            words = clean_text.split()[:50]
            preview = ' '.join(words)
            
            print(f"✅ First 50 words:")
            print(preview)
            print()
            print(f"Total text length: {len(full_text)} characters")
        else:
            print("❌ No text content available")
        
        print("=" * 80)
        print()
    
    print("✅ Demonstration completed successfully!")
    return 0

if __name__ == '__main__':
    sys.exit(main())