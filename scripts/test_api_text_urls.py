#!/usr/bin/env python3
"""
Test script to check what text URLs the Congress.gov API provides
"""

import logging
import sys
import os
import json

# Add the src directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from fetchers.feed_parser import _fetch_bills_from_api

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_api_text_urls():
    """Test what text URLs the API provides"""
    print("Testing Congress.gov API text URLs...")
    print("=" * 60)
    
    try:
        # Fetch 5 bills from API
        bills = _fetch_bills_from_api(limit=5)
        
        if not bills:
            print("❌ No bills found from API!")
            return False
        
        print(f"✅ Successfully fetched {len(bills)} bills from API")
        print()
        
        for i, bill in enumerate(bills, 1):
            print(f"Bill {i}: {bill['bill_id']} - {bill.get('title', 'No title')[:50]}...")
            print(f"Text URL: {bill.get('text_url', 'No text URL')}")
            print(f"Source URL: {bill.get('source_url', 'No source URL')}")
            print(f"Text version: {bill.get('text_version', 'Unknown')}")
            
            # Check if API data has text versions
            api_data = bill.get('api_data', {})
            if 'textVersions' in api_data:
                print(f"API text versions: {len(api_data['textVersions'])}")
                for j, version in enumerate(api_data['textVersions'][:2]):  # Show first 2 versions
                    print(f"  Version {j+1}: {version.get('type', 'Unknown')}")
                    if 'formats' in version:
                        for fmt in version['formats']:
                            print(f"    Format: {fmt.get('type', 'Unknown')} - {fmt.get('url', 'No URL')}")
            
            print("-" * 50)
        
        return True
        
    except Exception as e:
        print(f"❌ Error during API testing: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_api_text_urls()
    if success:
        print("\n✅ API test completed successfully!")
        sys.exit(0)
    else:
        print("\n❌ API test failed!")
        sys.exit(1)