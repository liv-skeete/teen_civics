#!/usr/bin/env python3
"""
Orchestrator script that combines bill fetching, summarization, and Twitter posting.
Designed for daily automation via GitHub Actions.

TODO: Future improvements (SAVE FOR LATER):
- Add configurable timeout values for long-running operations
- Implement circuit breaker pattern for external API calls
- Add comprehensive monitoring and alerting
"""

import os
import sys
import logging
import json
from typing import Dict, Any

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

def main(dry_run: bool = False) -> int:
    """
    Main orchestrator function:
    1. Checks if a bill was already posted today (duplicate prevention)
    2. Fetches recent bills from Congress.gov
    3. Checks each bill to find the first one not already tweeted
    4. Summarizes it using Claude if needed
    5. Stores summary in database if needed
    6. Posts the tweet to X/Twitter (unless dry-run mode)
    7. Updates database with tweet information (unless dry-run mode)
    If all bills are already processed, checks DB for unposted bills.
    
    Args:
        dry_run: If True, skips actual Twitter posting and database updates
    """
    try:
        logger.info("🚀 Starting orchestrator: fetch → check → summarize → store → tweet")
        logger.info(f"📊 Dry-run mode: {dry_run}")
        
        # Determine which scan this is based on current time
        from datetime import datetime, time
        import pytz
        et_tz = pytz.timezone('America/New_York')
        current_time_et = datetime.now(et_tz)
        current_et_time = current_time_et.time()
        
        # Morning scan: 8:30 AM to 9:30 AM ET
        # Evening scan: 2:00 AM to 2:59 AM ET (corresponds to 2:30 AM UTC job with potential 30-minute lag)
        if time(8, 30) <= current_et_time <= time(9, 30):
            scan_type = "MORNING"
        elif time(2, 0) <= current_et_time <= time(2, 59):
            scan_type = "EVENING"
        else:
            scan_type = "MANUAL"
        
        logger.info(f"⏰ Scan type: {scan_type} (Current time: {current_time_et.strftime('%I:%M %p ET')})")
        
        # Production: Do not log environment variables or secrets
        logger.info("🔒 Environment ready (sensitive values are not logged)")

        # Import modules
        from src.fetchers.congress_fetcher import get_recent_bills
        from src.processors.summarizer import summarize_bill_enhanced
        from src.publishers.twitter_publisher import post_tweet
        from src.database.db import (
            bill_exists, bill_already_posted, get_bill_by_id,
            insert_bill, update_tweet_info, generate_website_slug, init_db,
            normalize_bill_id, select_and_lock_unposted_bill, has_posted_today
        )
        from src.fetchers.feed_parser import running_in_ci
        
        # Ensure database exists and schema is up to date
        logger.info("🗄️ Initializing database (ensure tables exist)...")
        init_db()
        logger.info("✅ Database initialization complete")
        
        # Log CI mode if applicable
        if running_in_ci():
            logger.info("⚙️ CI environment detected. Running in API-only mode.")
        
        # DUPLICATE PREVENTION: Check if we already posted today
        # Only apply duplicate prevention for evening scans
        if not dry_run and scan_type == "EVENING" and has_posted_today():
            logger.info("🛑 DUPLICATE PREVENTION: A bill was already posted in the last 24 hours")
            logger.info("🛑 Skipping EVENING scan to prevent duplicate posts")
            logger.info("✅ Orchestrator completed - no action needed")
            return 0

        # Step 1: Fetch recent bills from feed
        logger.info("📥 Fetching recent bills from 'Bill Texts Received Today' feed...")
        bills = get_recent_bills(limit=5, include_text=True)  # Only fetch 5 for efficiency
        logger.info(f"📊 Retrieved {len(bills)} bills from feed")

        if not bills:
            logger.info("ℹ️ No bills returned from feed (feed may be empty today)")
            logger.info("📭 Checking database for any unposted bills...")
            unposted = select_and_lock_unposted_bill()
            if unposted:
                logger.info(f"   🔄 Found and locked unposted bill in DB: {unposted['bill_id']}")
                selected_bill = {"bill_id": unposted["bill_id"]}
                selected_bill_data = unposted
                # Skip to step 3 (processing)
                bills = []
            else:
                logger.info("📭 No unposted bills available. Nothing to do today.")
                return 0
        
        # Step 1.5: Validate bills have full text
        if bills:
            logger.info("🔍 Validating bill text availability...")
            valid_bills = []
            for bill in bills:
                full_text = bill.get('full_text', '')
                if full_text and len(full_text.strip()) > 100:
                    valid_bills.append(bill)
                    logger.info(f"   ✅ {bill['bill_id']}: Text validated ({len(full_text)} chars)")
                else:
                    logger.warning(f"   ⚠️ {bill['bill_id']}: Insufficient text ({len(full_text)} chars) - skipping")
            
            bills = valid_bills
            logger.info(f"📊 {len(bills)} bills passed text validation")
            
            if not bills:
                logger.warning("⚠️ No bills with valid text found. Checking DB for unposted bills...")
                unposted = select_and_lock_unposted_bill()
                if unposted:
                    logger.info(f"   🔄 Found and locked unposted bill in DB: {unposted['bill_id']}")
                    selected_bill = {"bill_id": unposted["bill_id"]}
                    selected_bill_data = unposted
                else:
                    logger.info("📭 No unposted bills available. Nothing to do.")
                    return 0

        # Step 2: Find first unprocessed bill
        selected_bill = None
        selected_bill_data = None
        
        # Deduplicate bills to prevent processing the same bill multiple times
        unique_bills = []
        seen_bill_ids = set()
        for bill in bills:
            raw_bill_id = bill.get("bill_id", "unknown")
            bill_id = normalize_bill_id(raw_bill_id)
            if bill_id not in seen_bill_ids:
                unique_bills.append(bill)
                seen_bill_ids.add(bill_id)
        bills = unique_bills
        logger.info(f"📊 Deduplicated bills: {len(bills)} unique bills from {len(unique_bills)} total")
        
        logger.info("🔍 Scanning bills for unprocessed content...")

        for bill in bills:
            raw_bill_id = bill.get("bill_id", "unknown")
            bill_id = normalize_bill_id(raw_bill_id)
            logger.info(f"   📋 Checking bill: {bill_id} (normalized from: {raw_bill_id})")
            
            # Check if bill exists in DB
            if bill_already_posted(bill_id):
                logger.info(f"   ✅ Bill {bill_id} already tweeted. Skipping.")
                continue

            existing_bill = get_bill_by_id(bill_id)
            
            if existing_bill:
                logger.info(f"   🎯 Bill {bill_id} exists but not tweeted. Selecting for tweet.")
                selected_bill = bill
                selected_bill_data = existing_bill
                break
            else:
                # New bill - needs full processing
                logger.info(f"   🆕 Bill {bill_id} is new. Selecting for full processing.")
                selected_bill = bill
                selected_bill_data = None
                break

        # If no unprocessed bills found, check DB for any unposted bills with locking
        if not selected_bill:
            logger.info("📭 All recent bills already posted. Checking DB for unposted bills...")
            logger.info("🔒 Using SELECT FOR UPDATE SKIP LOCKED to prevent race conditions...")
            unposted = select_and_lock_unposted_bill()
            if unposted:
                logger.info(f"   🔄 Found and locked unposted bill in DB: {unposted['bill_id']}")
                selected_bill = {"bill_id": unposted["bill_id"]}
                selected_bill_data = unposted
            else:
                logger.info("📭 No unposted bills available (all locked or processed). Nothing to do.")
                return 0

        # Step 3: Process the selected bill
        raw_bill_id = selected_bill.get("bill_id", "unknown")
        bill_id = normalize_bill_id(raw_bill_id)
        logger.info(f"⚙️ Processing selected bill: {bill_id} (normalized from: {raw_bill_id})")

        if selected_bill_data:
            # Use existing data from DB
            logger.info("💾 Using existing summaries from database")
            bill_data = selected_bill_data
            tweet_text = bill_data.get("summary_tweet", "")
            logger.info(f"📝 Existing tweet summary length: {len(tweet_text)} characters")
        else:
            # Generate new summaries
            logger.info("🧠 Generating new summaries with enhanced format...")
            summary = summarize_bill_enhanced(selected_bill)
            logger.info("✅ Summaries generated successfully")
            
            # Create bill_data for insertion with new fields
            term_dict_obj = summary.get("term_dictionary", [])
            # Convert term dictionary to JSON string for database storage
            import json
            term_dict_json = json.dumps(term_dict_obj, ensure_ascii=False, separators=(',', ':'))
            
            # Extract latest action text from the latest_action dict
            latest_action_dict = selected_bill.get("latest_action", {})
            latest_action_text = latest_action_dict.get("text", "") if isinstance(latest_action_dict, dict) else str(latest_action_dict)
            
            # Extract tracker data
            tracker_data = selected_bill.get("tracker")
            
            # Derive normalized status from tracker and ensure proper serialization
            normalized_status = "unknown"
            tracker_raw_serialized = None
            
            if tracker_data:
                try:
                    # Try to serialize tracker_data to JSON string
                    tracker_raw_serialized = json.dumps(tracker_data)
                    
                    # Derive normalized status from tracker
                    if isinstance(tracker_data, list):
                        # List of steps with selected flag
                        for step in tracker_data:
                            if step.get("selected", False):
                                normalized_status = step["name"].lower().replace(" ", "_")
                                break
                    elif isinstance(tracker_data, dict):
                        # Dict with steps in 'steps' key
                        steps = tracker_data.get("steps", [])
                        for step in steps:
                            if step.get("selected", False):
                                normalized_status = step["name"].lower().replace(" ", "_")
                                break
                except (TypeError, ValueError) as e:
                    logger.warning(f"Failed to serialize tracker_data for bill {bill_id}: {e}")
                    # Set to None if serialization fails
                    tracker_raw_serialized = None
            
            bill_data = {
                "bill_id": bill_id,
                "title": selected_bill.get("title", ""),
                "short_title": selected_bill.get("short_title", ""),
                "status": selected_bill.get("status", ""),  # Old field for backward compatibility
                "raw_latest_action": latest_action_text,
                "tracker_raw": tracker_raw_serialized,
                "normalized_status": normalized_status,
                "summary_tweet": summary.get("tweet", ""),
                "summary_long": summary.get("long", ""),
                "summary_overview": summary.get("overview", ""),
                "summary_detailed": summary.get("detailed", ""),
                "term_dictionary": term_dict_json,
                "congress_session": selected_bill.get("congress", ""),
                "date_introduced": selected_bill.get("introduced_date", ""),
                "source_url": selected_bill.get("source_url", ""),
                "website_slug": generate_website_slug(selected_bill.get("title", ""), bill_id),
                "tags": "",
                "tweet_posted": False,
                "tweet_url": None,
                "text_source": selected_bill.get("text_source", "feed"),
                "text_version": selected_bill.get("text_version", "Introduced"),
                "text_received_date": selected_bill.get("text_received_date"),
                "processing_attempts": 0,
                "full_text": selected_bill.get("full_text", "")
            }
            
            logger.info(f"📊 New tweet summary length: {len(bill_data['summary_tweet'])} characters")
            
            # Insert into database
            logger.info("💾 Inserting new bill into database...")
            if not insert_bill(bill_data):
                logger.error(f"❌ Failed to insert bill {bill_id}")
                return 1
            logger.info("✅ Bill inserted into database successfully")

        # Step 4: Post tweet (or simulate in dry-run mode)
        logger.info("🐦 Preparing to post tweet...")
        from src.publishers.twitter_publisher import format_bill_tweet
        formatted_tweet = format_bill_tweet(bill_data)
        logger.info(f"📝 Formatted tweet length: {len(formatted_tweet)} characters")
        
        # DIAGNOSTIC: Log current database state before posting
        logger.info(f"🔍 DIAGNOSTIC: Pre-post database state for bill {bill_id}:")
        current_state = get_bill_by_id(bill_id)
        if current_state:
            logger.info(f"🔍 DIAGNOSTIC:   tweet_posted = {current_state.get('tweet_posted')}")
            logger.info(f"🔍 DIAGNOSTIC:   tweet_url = {current_state.get('tweet_url')}")
        else:
            logger.warning(f"🔍 DIAGNOSTIC:   Bill {bill_id} not found in database!")
        
        if dry_run:
            logger.info("🔶 DRY-RUN MODE: Simulating tweet post")
            logger.info(f"🔶 DRY-RUN: Would post tweet (length: {len(formatted_tweet)}):")
            logger.info(f"🔶 DRY-RUN: {formatted_tweet}")
            logger.info("🔶 DRY-RUN: Skipping actual Twitter post and database update")
            logger.info("✅ Dry-run completed successfully")
            return 0
        else:
            logger.info("🚀 Posting tweet to Twitter...")
            logger.info(f"📝 Tweet content: {formatted_tweet[:100]}...")
            
            # SAFETY CHECK: Skip tweeting test bills in production
            if os.getenv('TESTING') != 'true':
                test_bill_id = bill_data.get("bill_id", "")
                test_title = bill_data.get("title", "")
                test_summary = bill_data.get("summary_tweet", "")
                
                is_test_bill = (
                    test_bill_id == 'hr9999-119' or
                    'test' in test_title.lower() or
                    'this is a test bill' in test_summary.lower() or
                    'link coming soon' in test_summary.lower()
                )
                
                if is_test_bill:
                    logger.warning(f"⚠️ Skipping tweet for test bill {test_bill_id}.")
                    return 0
            
            success, tweet_url = post_tweet(formatted_tweet)
            
            # DIAGNOSTIC: Check if this was a duplicate content error
            if not success and tweet_url == "DUPLICATE_CONTENT":
                logger.error("🔍 DIAGNOSTIC: Twitter rejected tweet as DUPLICATE CONTENT")
                logger.error(f"🔍 DIAGNOSTIC: Bill {bill_id} was likely already tweeted but database wasn't updated")
                logger.error(f"🔍 DIAGNOSTIC: Marking bill as tweeted to prevent future duplicate attempts")
                
                # Mark the bill as tweeted even though we don't have the original tweet URL
                # This prevents infinite retry loops
                placeholder_url = f"https://twitter.com/search?q=from:TeenCivics+{bill_id}"
                update_success = update_tweet_info(bill_id, placeholder_url)
                
                if update_success:
                    logger.info(f"✅ Bill {bill_id} marked as tweeted (duplicate detected)")
                    logger.info("🎉 Orchestrator completed - duplicate handled gracefully")
                    return 0
                else:
                    logger.error(f"❌ Failed to mark bill {bill_id} as tweeted after duplicate detection")
                    return 1

            if success:
                logger.info(f"✅ Tweet posted successfully: {tweet_url}")
                
                # CRITICAL: Update database immediately with row-level locking
                logger.info("💾 Updating database with tweet information (with row lock)...")
                logger.debug(f"DEBUG: Calling update_tweet_info(bill_id='{bill_id}', tweet_url='{tweet_url}')")
                
                update_success = update_tweet_info(bill_id, tweet_url)
                
                if update_success:
                    logger.info("✅ Database updated successfully with row-level locking")
                    
                    # Post-update verification: re-query the bill to confirm changes
                    logger.debug("🔍 Performing post-update verification...")
                    updated_bill = get_bill_by_id(bill_id)
                    
                    if updated_bill:
                        tweet_posted = updated_bill.get('tweet_posted', False)
                        saved_tweet_url = updated_bill.get('tweet_url', '')
                        
                        logger.debug(f"DEBUG: Post-update verification - tweet_posted: {tweet_posted}, tweet_url: {saved_tweet_url}")
                        
                        if tweet_posted and saved_tweet_url == tweet_url:
                            logger.info("✅ Database update verified successfully - tweet_posted=True and tweet_url matches")
                            logger.info("🎉 Orchestrator completed successfully!")
                            return 0
                        else:
                            logger.error(f"❌ DATABASE UPDATE FAILED VERIFICATION: tweet_posted={tweet_posted}, tweet_url match={saved_tweet_url == tweet_url}")
                            logger.error("❌ This should not happen with row-level locking!")
                            logger.error("❌ Bill will be marked as problematic to prevent duplicate tweets")
                            
                            # Mark this bill as problematic to prevent future selection
                            from src.database.db import mark_bill_as_problematic
                            mark_bill_as_problematic(bill_id, f"Tweet update verification failed despite locking: posted={tweet_posted}, url_match={saved_tweet_url == tweet_url}")
                            
                            return 1
                    else:
                        logger.error("❌ DATABASE VERIFICATION FAILED: Could not retrieve updated bill")
                        logger.error("❌ Bill will be marked as problematic to prevent duplicate tweets")
                        
                        # Mark this bill as problematic to prevent future selection
                        from src.database.db import mark_bill_as_problematic
                        mark_bill_as_problematic(bill_id, "Could not retrieve bill for verification after update")
                        
                        return 1
                else:
                    logger.error("❌ Database update failed - update_tweet_info() returned False")
                    logger.error("❌ This indicates the bill may have been updated by another process")
                    logger.error("❌ Bill will be marked as problematic to prevent duplicate tweets")
                    
                    # Mark this bill as problematic to prevent future selection
                    from src.database.db import mark_bill_as_problematic
                    mark_bill_as_problematic(bill_id, "update_tweet_info() returned False - possible concurrent update")
                    
                    return 1
            else:
                logger.error("❌ Failed to post tweet to Twitter")
                logger.error("❌ The bill remains unposted and will be retried in the next run")
                return 1
            
    except ImportError as e:
        logger.error(f"Import error: {e}")
        return 1
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return 1

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="TeenCivics Orchestrator - Fetch, summarize, and post bills")
    parser.add_argument("--dry-run", action="store_true", help="Run in dry-run mode (no Twitter posting or DB updates)")
    
    args = parser.parse_args()
    sys.exit(main(dry_run=args.dry_run))