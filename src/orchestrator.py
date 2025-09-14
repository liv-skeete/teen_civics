#!/usr/bin/env python3
"""
Orchestrator script that combines bill fetching, summarization, and Twitter posting.
Designed for daily automation via GitHub Actions.
"""

import os
import sys
import logging
from typing import Dict, Any

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

def main() -> int:
    """
    Main orchestrator function:
    1. Fetches the most recent bill from Congress.gov
    2. Checks if bill already exists in database (prevents duplicates)
    3. Summarizes it using Claude
    4. Stores summary in database
    5. Posts the tweet to X/Twitter
    6. Updates database with tweet information
    """
    try:
        logger.info("Starting orchestrator: fetch → check → summarize → store → tweet")
        
        # Import modules
        from src.fetchers.congress_fetcher import get_recent_bills
        from src.processors.summarizer import summarize_bill
        from src.publishers.twitter_publisher import post_tweet
        from src.database.db import bill_exists, insert_bill, update_tweet_info, generate_website_slug
        
        # Step 1: Fetch the most recent bill with full text (no truncation)
        logger.info("Fetching most recent bill from Congress.gov with full text...")
        bills = get_recent_bills(limit=1, include_text=True, text_chars=2000000)
        
        if not bills:
            logger.error("No bills found to process")
            return 1
            
        bill = bills[0]
        bill_id = bill.get("bill_id", "unknown")
        logger.info(f"Processing bill: {bill_id}")
        
        # Step 2: Check if bill already exists in database (deduplication)
        if bill_exists(bill_id):
            logger.info(f"Bill {bill_id} already exists in database. Skipping to avoid duplicate.")
            return 0
            
        # Step 3: Summarize the bill
        logger.info("Summarizing bill...")
        summary = summarize_bill(bill)
        
        tweet_text = summary.get("tweet", "").strip()
        long_summary = summary.get("long", "").strip()
        
        if not tweet_text or not long_summary:
            logger.error("No valid summary generated from bill")
            return 1
            
        logger.info(f"Generated tweet: {tweet_text}")
        logger.info(f"Tweet length: {len(tweet_text)}/280 characters")
        
        # Step 4: Prepare bill data for database storage
        bill_data = {
            "bill_id": bill_id,
            "title": bill.get("title", ""),
            "short_title": bill.get("short_title", ""),
            "status": bill.get("status", ""),
            "summary_tweet": tweet_text,
            "summary_long": long_summary,
            "congress_session": bill.get("congress", ""),
            "date_introduced": bill.get("introduced_date", ""),
            "source_url": bill.get("congressdotgov_url", ""),
            "website_slug": generate_website_slug(bill.get("title", ""), bill_id),
            "tags": "",  # Can be populated later based on bill content
            "tweet_posted": False,
            "tweet_url": None
        }
        
        # Step 5: Store bill in database (before posting tweet)
        if not insert_bill(bill_data):
            logger.error("Failed to insert bill into database")
            return 1
            
        # Step 6: Post to Twitter
        logger.info("Posting tweet to X/Twitter...")
        success, tweet_url = post_tweet(tweet_text)
        
        if success:
            logger.info("✅ Tweet posted successfully!")
            # Update database with tweet information
            if tweet_url:
                update_tweet_info(bill_id, tweet_url)
            return 0
        else:
            logger.error("❌ Failed to post tweet")
            return 1
            
    except ImportError as e:
        logger.error(f"Import error: {e}")
        return 1
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())