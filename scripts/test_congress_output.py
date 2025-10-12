#!/usr/bin/env python3
"""
Test script to fetch recent bills and display first 100 words of each.
This verifies that the congress_fetcher is correctly extracting and logging bill text.
"""

import sys
from src.fetchers.congress_fetcher import get_recent_bills


def main():
    """Fetch 5 recent bills and display their first 100 words."""
    print("=" * 80)
    print("FETCHING 5 MOST RECENT BILLS FROM CONGRESS.GOV")
    print("=" * 80)
    print()
    
    try:
        # Fetch 5 recent bills with text included
        bills = get_recent_bills(limit=5, include_text=True)
        
        if not bills:
            print("❌ No bills were fetched. Check the congress_fetcher logs for errors.")
            return
        
        print(f"✅ Successfully fetched {len(bills)} bill(s)\n")
        
        # Display each bill's information
        for i, bill in enumerate(bills, 1):
            print("=" * 80)
            print(f"BILL {i}: {bill.get('bill_id', 'Unknown ID')}")
            print("=" * 80)
            
            # Display metadata
            print(f"Title: {bill.get('title', 'No title available')}")
            print(f"Text Source: {bill.get('text_source', 'Unknown source')}")
            
            # Get bill text (stored as 'full_text' in congress_fetcher)
            bill_text = bill.get('full_text', '')
            
            if bill_text:
                # Calculate character count
                char_count = len(bill_text)
                print(f"Total Characters: {char_count:,}")
                
                # Extract first 100 words
                words = bill_text.split()
                first_100_words = ' '.join(words[:100])
                word_count = len(words)
                
                print(f"Total Words: {word_count:,}")
                print()
                print("First 100 Words:")
                print("-" * 80)
                print(first_100_words)
                print("-" * 80)
                
                if word_count < 100:
                    print(f"⚠️  Note: Bill only contains {word_count} words (less than 100)")
            else:
                print("❌ No text available for this bill")
            
            print()
        
        print("=" * 80)
        print("TEST COMPLETE")
        print("=" * 80)
        
    except Exception as e:
        print(f"❌ Error during test: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()