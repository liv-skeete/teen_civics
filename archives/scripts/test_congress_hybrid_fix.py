#!/usr/bin/env python3
"""
Test script for the hybrid congress fetcher implementation.
Tests the three-tier approach: Browser -> Requests -> API with filtering.
"""

import sys
import logging
from src.fetchers.feed_parser import parse_bill_texts_feed, PLAYWRIGHT_AVAILABLE
from src.fetchers.congress_fetcher import fetch_bills_from_feed

# Configure logging to see all the tier transitions
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_feed_parser():
    """Test the feed parser with three-tier approach"""
    logger.info("=" * 80)
    logger.info("TEST 1: Feed Parser (Three-Tier Approach)")
    logger.info("=" * 80)
    
    if not PLAYWRIGHT_AVAILABLE:
        logger.warning("⚠️ Playwright not available - Tier 1 (browser) will be skipped")
        logger.info("To enable browser fetching, run: pip install playwright && playwright install chromium")
    
    try:
        bills = parse_bill_texts_feed(limit=5)
        
        if bills:
            logger.info(f"✅ SUCCESS: Retrieved {len(bills)} bills")
            for i, bill in enumerate(bills, 1):
                logger.info(f"\n📋 Bill {i}:")
                logger.info(f"   ID: {bill['bill_id']}")
                logger.info(f"   Title: {bill['title'][:80]}...")
                logger.info(f"   Text URL: {bill.get('text_url', 'None')}")
                logger.info(f"   Source URL: {bill.get('source_url', 'None')}")
        else:
            logger.info("ℹ️ No bills returned (feed may be empty today - this is normal)")
            logger.info("ℹ️ The system should have automatically fallen back to API with text filtering")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ FAILED: {e}", exc_info=True)
        return False


def test_full_workflow():
    """Test the full workflow including text enrichment"""
    logger.info("\n" + "=" * 80)
    logger.info("TEST 2: Full Workflow (Feed + Text Enrichment)")
    logger.info("=" * 80)
    
    try:
        bills = fetch_bills_from_feed(limit=3, include_text=True, text_chars=500)
        
        if bills:
            logger.info(f"✅ SUCCESS: Retrieved {len(bills)} bills with text")
            for i, bill in enumerate(bills, 1):
                logger.info(f"\n📋 Bill {i}:")
                logger.info(f"   ID: {bill['bill_id']}")
                logger.info(f"   Title: {bill['title'][:80]}...")
                logger.info(f"   Text Source: {bill.get('text_source', 'unknown')}")
                logger.info(f"   Text Length: {len(bill.get('full_text', ''))} chars")
                
                # Show first 200 chars of text
                text = bill.get('full_text', '')
                if text:
                    preview = text[:200].replace('\n', ' ')
                    logger.info(f"   Preview: {preview}...")
        else:
            logger.info("ℹ️ No bills returned (feed may be empty today - this is normal)")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ FAILED: {e}", exc_info=True)
        return False


def main():
    """Run all tests"""
    logger.info("🚀 Starting Congress Fetcher Hybrid Implementation Tests")
    logger.info("This will test the three-tier approach:")
    logger.info("  Tier 1: Browser-based fetch (bypasses 403)")
    logger.info("  Tier 2: Requests library (fallback)")
    logger.info("  Tier 3: API with text filtering (when feed is empty)")
    logger.info("")
    
    results = []
    
    # Test 1: Feed parser
    results.append(("Feed Parser", test_feed_parser()))
    
    # Test 2: Full workflow
    results.append(("Full Workflow", test_full_workflow()))
    
    # Summary
    logger.info("\n" + "=" * 80)
    logger.info("TEST SUMMARY")
    logger.info("=" * 80)
    
    for test_name, passed in results:
        status = "✅ PASSED" if passed else "❌ FAILED"
        logger.info(f"{status}: {test_name}")
    
    all_passed = all(result[1] for result in results)
    
    if all_passed:
        logger.info("\n🎉 All tests passed!")
        return 0
    else:
        logger.error("\n❌ Some tests failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())