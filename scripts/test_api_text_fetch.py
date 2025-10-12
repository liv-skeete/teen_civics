#!/usr/bin/env python3
"""
Test script to fetch bills from Congress.gov API and retrieve their text.
This demonstrates that we can successfully read bill text from the API.
"""

import requests
import json
from src.config import get_config

def fetch_bill_text_from_api(congress, bill_type, bill_number, api_key):
    """
    Fetch bill text directly from the Congress.gov API text endpoint.
    
    Args:
        congress: Congress number (e.g., 119)
        bill_type: Bill type (e.g., 'sres', 's', 'hr')
        bill_number: Bill number (e.g., 412)
        api_key: Congress.gov API key
    
    Returns:
        Tuple of (text_content, format_type) or (None, None) if failed
    """
    # Get text versions
    text_versions_url = f'https://api.congress.gov/v3/bill/{congress}/{bill_type}/{bill_number}/text?format=json'
    if api_key:
        text_versions_url += f'&api_key={api_key}'
    
    print(f"  Fetching text versions from: {text_versions_url}")
    response = requests.get(text_versions_url, timeout=30)
    
    if response.status_code != 200:
        print(f"  ❌ Failed to fetch text versions: {response.status_code}")
        return None, None
    
    data = response.json()
    text_versions = data.get('textVersions', [])
    
    if not text_versions:
        print(f"  ❌ No text versions available")
        return None, None
    
    # Get the first (most recent) text version
    latest_version = text_versions[0]
    print(f"  Found text version: {latest_version.get('type', 'Unknown')}")
    
    # Get formats available for this version
    formats = latest_version.get('formats', [])
    
    # Try to get text in order of preference: TXT, XML, PDF, HTML
    for format_type in ['Formatted Text', 'XML', 'PDF', 'HTML']:
        for fmt in formats:
            if fmt.get('type') == format_type:
                url = fmt.get('url')
                if url:
                    print(f"  Downloading {format_type} from: {url}")
                    try:
                        text_response = requests.get(url, timeout=30)
                        if text_response.status_code == 200:
                            if format_type == 'PDF':
                                # For PDF, we'd need to extract text (skipping for now)
                                print(f"  ✅ PDF downloaded ({len(text_response.content)} bytes)")
                                return "[PDF content - extraction not implemented in test]", format_type
                            else:
                                content = text_response.text
                                print(f"  ✅ {format_type} downloaded ({len(content)} characters)")
                                return content, format_type
                    except Exception as e:
                        print(f"  ⚠️  Failed to download {format_type}: {e}")
    
    print(f"  ❌ No downloadable text format found")
    return None, None


def main():
    """Main test function."""
    print("=" * 80)
    print("Testing Bill Text Fetch from Congress.gov API")
    print("=" * 80)
    
    # Load configuration
    config = get_config()
    api_key = config.congress_api.api_key
    
    if not api_key:
        print("❌ CONGRESS_API_KEY not configured!")
        return
    
    print(f"✅ API Key configured\n")
    
    # Fetch recent bills from API
    print("Fetching recent bills from API...")
    bills_url = 'https://api.congress.gov/v3/bill?format=json&limit=5'
    if api_key:
        bills_url += f'&api_key={api_key}'
    
    response = requests.get(bills_url, timeout=30)
    if response.status_code != 200:
        print(f"❌ Failed to fetch bills: {response.status_code}")
        return
    
    data = response.json()
    bills = data.get('bills', [])
    
    print(f"✅ Fetched {len(bills)} bills\n")
    print("=" * 80)
    
    # Process each bill
    for i, bill in enumerate(bills, 1):
        congress = bill.get('congress')
        bill_type = bill.get('type', '').lower()
        bill_number = bill.get('number')
        title = bill.get('title', 'No title')
        
        print(f"\nBill {i}: {bill_type.upper()}{bill_number}-{congress}")
        print(f"Title: {title[:100]}...")
        print("-" * 80)
        
        # Fetch text for this bill
        text_content, format_type = fetch_bill_text_from_api(
            congress, bill_type, bill_number, api_key
        )
        
        if text_content:
            # Extract first 50 words
            words = text_content.split()[:50]
            preview = ' '.join(words)
            
            print(f"\n📄 First 50 words ({format_type}):")
            print("-" * 80)
            print(preview)
            print("-" * 80)
        else:
            print(f"\n❌ No text content available for this bill")
        
        print()
    
    print("=" * 80)
    print("✅ Test completed!")
    print("=" * 80)


if __name__ == '__main__':
    main()