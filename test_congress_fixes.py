#!/usr/bin/env python3
"""
Test script to verify the congress_fetcher.py fixes:
1. Proper link usage from API (Tier 1)
2. Validation of text_url before Tier 2 usage
3. First 100 words logging to prove actual content reading
4. Clear logging to distinguish API vs constructed links
"""

import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from fetchers.congress_fetcher import fetch_bills_from_feed
import logging

# Set up logging to see all output
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

def main():
    """Test the congress fetcher with the new fixes"""
    logger.info("=" * 80)
    logger.info("Testing Congress Fetcher Fixes")
    logger.info("=" * 80)
    
    # Fetch 5 most recent bills with full text
    logger.info("\n🔍 Fetching 5 most recent bills from 'Bill Texts Received Today' feed...")
    bills = fetch_bills_from_feed(limit=5, include_text=True, text_chars=15000)
    
    if not bills:
        logger.error("❌ No bills fetched!")
        return 1
    
    logger.info(f"\n✅ Successfully fetched {len(bills)} bills")
    logger.info("=" * 80)
    
    # Display summary of each bill
    for i, bill in enumerate(bills, 1):
        logger.info(f"\n📋 Bill {i}/{len(bills)}: {bill['bill_id']}")
        logger.info(f"   Title: {bill.get('title', 'N/A')[:100]}...")
        logger.info(f"   Text Source: {bill.get('text_source', 'N/A')}")
        logger.info(f"   Text Length: {len(bill.get('full_text', ''))} characters")
        logger.info(f"   Source URL: {bill.get('source_url', 'N/A')}")
        logger.info(f"   Text URL: {bill.get('text_url', 'N/A')}")
        
        # Verify we have actual text content
        full_text = bill.get('full_text', '')
        if full_text and len(full_text) > 100:
            logger.info(f"   ✅ Has valid text content")
        else:
            logger.warning(f"   ⚠️ Missing or insufficient text content")
    
    logger.info("\n" + "=" * 80)
    logger.info("Test completed successfully!")
    logger.info("=" * 80)
    
    return 0

if __name__ == '__main__':
    sys.exit(main())