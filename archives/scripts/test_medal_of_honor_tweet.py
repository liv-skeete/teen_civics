#!/usr/bin/env python3
"""
Test script to verify the Twitter link generation fix with the Medal of Honor bill.
"""

import os
import sys
import logging

# Add the project root to the Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

from src.database.db import get_bill_by_id
from src.publishers.twitter_publisher import format_bill_tweet
from src.load_env import load_env

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    load_env()
    logger.info("Testing Twitter link generation with Medal of Honor bill...")
    
    # Get the Medal of Honor bill
    bill_id = 'hr695-119'
    logger.info(f"Fetching bill {bill_id}...")
    
    try:
        bill = get_bill_by_id(bill_id)
        if not bill:
            logger.error(f"Bill {bill_id} not found in database")
            return
            
        logger.info(f"Bill found: {bill.get('title', 'N/A')}")
        logger.info(f"Slug: {bill.get('website_slug', 'N/A')}")
        logger.info(f"Tweeted: {bill.get('tweet_posted', 'N/A')}")
        
        # Format the tweet
        tweet_text = format_bill_tweet(bill)
        logger.info("Formatted tweet:")
        print("=" * 50)
        print(tweet_text)
        print("=" * 50)
        
        # Check if the slug link is in the tweet
        slug = bill.get('website_slug')
        if slug:
            expected_link = f"teencivics.org/bill/{slug}"
            if expected_link in tweet_text:
                logger.info("✅ SUCCESS: Tweet contains the specific bill slug link")
            else:
                logger.error("❌ FAILURE: Tweet does not contain the specific bill slug link")
                logger.error(f"Expected to find: {expected_link}")
        else:
            logger.warning("Bill has no website_slug")
            
        # Calculate and show the effective tweet length, accounting for t.co shortening
        tco_link_length = 23
        slug = bill.get('website_slug')
        if slug:
            full_link = f"teencivics.org/bill/{slug}"
            effective_length = len(tweet_text) - len(full_link) + tco_link_length
            logger.info(f"Full text length: {len(tweet_text)} characters")
            logger.info(f"Effective tweet length (with t.co shortening): {effective_length} characters")
            if effective_length > 280:
                logger.error(f"❌ FAILURE: Effective tweet length exceeds 280 characters ({effective_length})")
            else:
                logger.info("✅ SUCCESS: Effective tweet length is within the 280-character limit")
        else:
            logger.info(f"Tweet length: {len(tweet_text)} characters")
        
    except Exception as e:
        logger.error(f"Error testing Medal of Honor bill: {e}")
        import traceback
        traceback.print_exc()
        return

if __name__ == "__main__":
    main()