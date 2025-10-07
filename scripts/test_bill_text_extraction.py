#!/usr/bin/env python3
"""
Test script to verify bill text extraction from Congress.gov
Fetches 5 most recent bills and displays 50 words from each
"""

import logging
import sys
import os

# Add the src directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from fetchers.congress_fetcher import get_recent_bills

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_bill_text_extraction():
    """Test bill text extraction by fetching 5 most recent bills"""
    print("Testing bill text extraction from Congress.gov...")
    print("=" * 60)
    
    try:
        # Fetch 5 most recent bills with text
        bills = get_recent_bills(limit=5, include_text=True)
        
        if not bills:
            print("❌ No bills found!")
            return False
        
        print(f"✅ Successfully fetched {len(bills)} bills")
        print()
        
        for i, bill in enumerate(bills, 1):
            print(f"Bill {i}: {bill['bill_id']} - {bill.get('title', 'No title')[:50]}...")
            print(f"Source: {bill.get('text_source', 'unknown')}")
            
            full_text = bill.get('full_text', '')
            if full_text and len(full_text.strip()) > 0:
                # Extract first 50 words
                words = full_text.split()[:50]
                sample_text = ' '.join(words)
                print(f"Text sample (50 words): {sample_text}")
            else:
                print("❌ No text content available")
            
            print(f"Text length: {len(full_text)} characters")
            print("-" * 50)
        
        return True
        
    except Exception as e:
        print(f"❌ Error during testing: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_bill_text_extraction()
    if success:
        print("\n✅ Test completed successfully!")
        sys.exit(0)
    else:
        print("\n❌ Test failed!")
        sys.exit(1)