#!/usr/bin/env python3
"""
Test script for Bluesky posting integration.

Usage:
    # Dry run (preview only, no actual posting)
    python scripts/test_bluesky_posting.py
    
    # Actually post to Bluesky
    python scripts/test_bluesky_posting.py --post
    
    # Test with a specific bill from the database
    python scripts/test_bluesky_posting.py --bill-id hr-1234-119
"""

import os
import sys
import argparse
import logging

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_sample_bill():
    """Return a sample bill for testing."""
    return {
        "bill_id": "HR-TEST-119",
        "title": "Computer Science Education Expansion Act",
        "summary_tweet": (
            "A new bipartisan bill would expand computer science education in "
            "public schools nationwide, providing funding for teacher training "
            "and curriculum development to prepare students for tech careers."
        ),
        "website_slug": "hr-test-119",
        "normalized_status": "introduced",
        "teen_impact_score": 8
    }


def get_bill_from_db(bill_id: str):
    """Fetch a real bill from the database."""
    try:
        from src.database.db import get_bill_by_id
        bill = get_bill_by_id(bill_id)
        if bill:
            logger.info(f"Found bill: {bill.get('title', bill_id)}")
            return bill
        else:
            logger.error(f"Bill not found: {bill_id}")
            return None
    except Exception as e:
        logger.error(f"Database error: {e}")
        return None


def test_bluesky_config():
    """Test if Bluesky is properly configured."""
    print("\n" + "="*60)
    print("🔧 CONFIGURATION CHECK")
    print("="*60)
    
    handle = os.getenv('BLUESKY_HANDLE')
    password = os.getenv('BLUESKY_APP_PASSWORD')
    
    if handle:
        print(f"✅ BLUESKY_HANDLE: {handle}")
    else:
        print("❌ BLUESKY_HANDLE: Not set")
    
    if password:
        masked = password[:4] + "..." + password[-4:] if len(password) > 8 else "***"
        print(f"✅ BLUESKY_APP_PASSWORD: {masked}")
    else:
        print("❌ BLUESKY_APP_PASSWORD: Not set")
    
    return bool(handle and password)


def test_bluesky_auth():
    """Test Bluesky authentication."""
    print("\n" + "="*60)
    print("🔐 AUTHENTICATION TEST")
    print("="*60)
    
    try:
        from src.publishers.bluesky_publisher import BlueskyPublisher
        
        publisher = BlueskyPublisher()
        
        if not publisher.is_configured():
            print("❌ Publisher reports not configured")
            return False
        
        # Try to get an authenticated client
        client = publisher._get_client()
        
        if client:
            print(f"✅ Successfully authenticated as {publisher._handle}")
            return True
        else:
            print("❌ Failed to create client")
            return False
            
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("   Run: pip install atproto")
        return False
    except Exception as e:
        print(f"❌ Authentication failed: {e}")
        return False


def test_formatting(bill: dict):
    """Test post formatting for a bill."""
    print("\n" + "="*60)
    print("📝 FORMATTING TEST")
    print("="*60)
    
    try:
        from src.publishers.bluesky_publisher import BlueskyPublisher
        
        publisher = BlueskyPublisher()
        formatted = publisher.format_post(bill)
        
        print(f"\nFormatted post ({len(formatted)} / {publisher.max_length} chars):\n")
        print("-" * 40)
        print(formatted)
        print("-" * 40)
        
        # Validate
        is_valid, reason = publisher.validate_post(formatted)
        
        if is_valid:
            print(f"\n✅ Validation passed: {reason}")
        else:
            print(f"\n❌ Validation failed: {reason}")
        
        return formatted, is_valid
        
    except Exception as e:
        print(f"❌ Formatting error: {e}")
        return None, False


def test_facets(text: str):
    """Test link facet extraction."""
    print("\n" + "="*60)
    print("🔗 FACETS TEST (Link Detection)")
    print("="*60)
    
    try:
        from src.publishers.bluesky_publisher import BlueskyPublisher
        
        publisher = BlueskyPublisher()
        facets = publisher._build_facets(text)
        
        if facets:
            print(f"✅ Found {len(facets)} link(s):")
            for i, facet in enumerate(facets):
                uri = facet['features'][0]['uri']
                start = facet['index']['byteStart']
                end = facet['index']['byteEnd']
                print(f"   {i+1}. {uri} (bytes {start}-{end})")
        else:
            print("⚠️ No links detected in text")
        
        return facets
        
    except Exception as e:
        print(f"❌ Facet extraction error: {e}")
        return None


def post_to_bluesky(text: str):
    """Actually post to Bluesky."""
    print("\n" + "="*60)
    print("🚀 POSTING TO BLUESKY")
    print("="*60)
    
    try:
        from src.publishers.bluesky_publisher import BlueskyPublisher
        
        publisher = BlueskyPublisher()
        success, url = publisher.post(text)
        
        if success:
            print(f"✅ Posted successfully!")
            print(f"   URL: {url}")
            return True, url
        else:
            print(f"❌ Failed to post")
            if url == "DUPLICATE_CONTENT":
                print("   Reason: Duplicate content (already posted)")
            return False, url
            
    except Exception as e:
        print(f"❌ Posting error: {e}")
        return False, None


def main():
    parser = argparse.ArgumentParser(description="Test Bluesky posting integration")
    parser.add_argument("--post", action="store_true", help="Actually post to Bluesky")
    parser.add_argument("--bill-id", type=str, help="Use a specific bill from database")
    args = parser.parse_args()
    
    print("\n" + "="*60)
    print("🦋 BLUESKY PUBLISHER TEST")
    print("="*60)
    
    # Step 1: Check configuration
    if not test_bluesky_config():
        print("\n⚠️ Bluesky is not configured. Set environment variables first.")
        print("   BLUESKY_HANDLE=your_handle.bsky.social")
        print("   BLUESKY_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx")
        return 1
    
    # Step 2: Test authentication
    if not test_bluesky_auth():
        print("\n❌ Authentication failed. Check your credentials.")
        return 1
    
    # Step 3: Get bill for testing
    if args.bill_id:
        bill = get_bill_from_db(args.bill_id)
        if not bill:
            print(f"\n❌ Could not find bill: {args.bill_id}")
            return 1
    else:
        bill = get_sample_bill()
        print("\nℹ️ Using sample test bill (use --bill-id for real bills)")
    
    # Step 4: Test formatting
    formatted, is_valid = test_formatting(bill)
    
    if not formatted or not is_valid:
        print("\n❌ Formatting test failed")
        return 1
    
    # Step 5: Test facets
    test_facets(formatted)
    
    # Step 6: Post if requested
    if args.post:
        confirm = input("\n⚠️ This will post to Bluesky. Continue? (y/n): ")
        if confirm.lower() == 'y':
            success, url = post_to_bluesky(formatted)
            if not success:
                return 1
        else:
            print("Posting cancelled.")
    else:
        print("\n" + "="*60)
        print("ℹ️ DRY RUN COMPLETE")
        print("="*60)
        print("To actually post, run with --post flag:")
        print("  python scripts/test_bluesky_posting.py --post")
    
    print("\n✅ All tests passed!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
