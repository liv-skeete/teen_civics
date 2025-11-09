#!/usr/bin/env python3
"""
Orchestrator script that combines bill fetching, summarization, and Twitter posting.
Designed for daily automation via GitHub Actions.
"""

import os
import sys
import logging
import json
from typing import Dict, Any, Optional
from datetime import datetime, time
import pytz

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.fetchers.feed_parser import fetch_and_enrich_bills, normalize_status
from src.processors.summarizer import summarize_bill_enhanced
from src.publishers.twitter_publisher import post_tweet, format_bill_tweet
from src.database.db import (
    bill_already_posted, get_bill_by_id, insert_bill, update_tweet_info,
    generate_website_slug, init_db, normalize_bill_id,
    select_and_lock_unposted_bill, has_posted_today, mark_bill_as_problematic
)

def snake_case(text: str) -> str:
    """Converts text to snake_case."""
    import re
    result = re.sub(r'[^a-zA-Z0-9]+', '_', text.lower())
    return result.strip('_')

def extract_teen_impact_score(summary_detailed: str) -> Optional[int]:
    """
    Extract Teen Impact Score from the detailed summary text.
    """
    if not summary_detailed:
        return None
    import re
    match = re.search(r"Teen impact score:\s*(\d+)/10", summary_detailed, re.IGNORECASE)
    if match:
        try:
            return int(match.group(1))
        except (ValueError, IndexError):
            return None
    return None

def derive_status_from_tracker(tracker: Any) -> (str, str):
    """
    Derive human-readable status and normalized_status from tracker data.
    The tracker may be a list[dict{name, selected}] or {'steps': [...]}.
    """
    steps = []
    try:
        if isinstance(tracker, list):
            steps = tracker
        elif isinstance(tracker, dict):
            steps = tracker.get("steps") or []
    except Exception:
        steps = []

    latest_name = ""
    # Prefer the last selected step (current status)
    try:
        for step in reversed(steps):
            if isinstance(step, dict) and step.get("selected"):
                latest_name = str(step.get("name", "")).strip()
                break
    except Exception:
        pass

    # Fallback: use the last step name if none marked selected
    if not latest_name and steps:
        try:
            last_step = steps[-1]
            latest_name = str(last_step.get("name") if isinstance(last_step, dict) else last_step).strip()
        except Exception:
            latest_name = ""

    status_text = latest_name or "Introduced"
    s = status_text.lower()

    # Map common tracker phrases to normalized_status values used by the site/CSS
    mapping = {
        "introduced": "introduced",
        "committee consideration": "committee_consideration",
        "reported by committee": "reported_by_committee",
        "passed house": "passed_house",
        "passed senate": "passed_senate",
        "agreed to in house": "agreed_to_in_house",
        "agreed to in senate": "agreed_to_in_senate",
        "to president": "to_president",
        "sent to president": "to_president",
        "presented to president": "to_president",
        "became law": "became_law",
        "enacted": "became_law",
        "vetoed": "vetoed",
        "failed house": "failed_house",
        "failed senate": "failed_senate",
    }

    normalized = None
    for key, val in mapping.items():
        if key in s:
            normalized = val
            break
    if not normalized:
        # Generic normalization as a safety net
        normalized = s.replace(" ", "_") if s else "introduced"
        if normalized not in mapping.values():
            normalized = "introduced"

    return status_text, normalized

def main(dry_run: bool = False) -> int:
    """
    Main orchestrator function.
    """
    try:
        logger.info("🚀 Starting orchestrator...")
        logger.info(f"📊 Dry-run mode: {dry_run}")

        et_tz = pytz.timezone('America/New_York')
        current_time_et = datetime.now(et_tz).time()
        
        scan_type = "MANUAL"
        if time(8, 30) <= current_time_et <= time(9, 30):
            scan_type = "MORNING"
        elif time(22, 0) <= current_time_et <= time(23, 0):
            scan_type = "EVENING"
        
        logger.info(f"⏰ Scan type: {scan_type}")

        logger.info("🗄️ Initializing database...")
        init_db()
        logger.info("✅ Database initialization complete")

        if not dry_run and scan_type == "EVENING" and has_posted_today():
            logger.info("🛑 DUPLICATE PREVENTION: A bill was already posted today. Skipping evening scan.")
            return 0

        logger.info("📥 Fetching and enriching recent bills from Congress.gov...")
        bills = fetch_and_enrich_bills(limit=25)
        logger.info(f"📊 Retrieved and enriched {len(bills)} bills")

        selected_bill = None
        selected_bill_data = None

        if bills:
            logger.info("🔍 Scanning for unprocessed bills...")
            for bill in bills:
                bill_id = normalize_bill_id(bill.get("bill_id", ""))
                logger.info(f"   📋 Checking bill: {bill_id}")
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
                    logger.info(f"   🆕 Bill {bill_id} is new. Selecting for full processing.")
                    selected_bill = bill
                    break
        
        if not selected_bill:
            logger.info("📭 No new bills from API. Checking DB for any unposted bills...")
            unposted = select_and_lock_unposted_bill()
            if unposted:
                logger.info(f"   🔄 Found and locked unposted bill in DB: {unposted['bill_id']}")
                selected_bill = {"bill_id": unposted["bill_id"]}
                selected_bill_data = unposted
            else:
                logger.info("📭 No unposted bills available. Nothing to do.")
                return 0

        bill_id = normalize_bill_id(selected_bill.get("bill_id", ""))
        logger.info(f"⚙️ Processing selected bill: {bill_id}")

        if selected_bill_data:
            logger.info("💾 Using existing summaries from database")
            bill_data = selected_bill_data
        else:
            # Derive status from tracker before summarization
            tracker_data = selected_bill.get("tracker") or []
            derived_status_text, derived_normalized_status = derive_status_from_tracker(tracker_data)
            selected_bill["status"] = derived_status_text
            selected_bill["normalized_status"] = derived_normalized_status
            logger.info(f"🧭 Derived status for {bill_id}: '{derived_status_text}' ({derived_normalized_status})")

            # Ensure bill has full text before summarization
            if not selected_bill.get("full_text") or len(selected_bill.get("full_text", "").strip()) < 100:
                logger.error(f"❌ No valid full text for bill {bill_id}. Skipping.")
                mark_bill_as_problematic(bill_id, "No valid full text available")
                return 1

            logger.info("🧠 Generating new summaries...")
            summary = summarize_bill_enhanced(selected_bill)
            logger.info("✅ Summaries generated successfully")

            # Validate summary content
            if not summary.get("overview") or "full bill text needed" in summary.get("detailed", "").lower():
                logger.error(f"❌ Invalid summary generated for bill {bill_id}. Marking as problematic.")
                mark_bill_as_problematic(bill_id, "Invalid summary content")
                return 1
                
            # Additional validation for "full bill text" phrases in any summary field
            summary_fields = [summary.get("overview", ""), summary.get("detailed", ""), summary.get("tweet", "")]
            if any("full bill text" in field.lower() for field in summary_fields):
                logger.error(f"❌ Summary contains 'full bill text' phrase for bill {bill_id}. Regenerating.")
                # Try one more time with a retry mechanism
                time.sleep(2)  # Small delay before retry
                summary = summarize_bill_enhanced(selected_bill)
                summary_fields = [summary.get("overview", ""), summary.get("detailed", ""), summary.get("tweet", "")]
                if any("full bill text" in field.lower() for field in summary_fields):
                    logger.error(f"❌ Summary still contains 'full bill text' phrase after retry for bill {bill_id}. Marking as problematic.")
                    mark_bill_as_problematic(bill_id, "Summary contains 'full bill text' phrase after retry")
                    return 1
            
            term_dict_json = json.dumps(summary.get("term_dictionary", []), ensure_ascii=False, separators=(',', ':'))

            teen_impact_score = extract_teen_impact_score(summary.get("detailed", ""))
            logger.info(f"⭐️ Extracted Teen Impact Score: {teen_impact_score}")
            
            tracker_raw_serialized = None
            if tracker_data:
                try:
                    tracker_raw_serialized = json.dumps(tracker_data)
                except (TypeError, ValueError) as e:
                    logger.warning(f"Failed to serialize tracker_data for bill {bill_id}: {e}")

            bill_data = {
                "bill_id": bill_id,
                "title": selected_bill.get("title", ""),
                "status": derived_status_text,
                "summary_tweet": summary.get("tweet", ""),
                "summary_long": summary.get("long", ""),
                "summary_overview": summary.get("overview", ""),
                "summary_detailed": summary.get("detailed", ""),
                "term_dictionary": term_dict_json,
                # Ensure these are always populated for UI (avoid N/A)
                "congress_session": str(selected_bill.get("congress", "") or "").strip(),
                "date_introduced": selected_bill.get("date_introduced") or selected_bill.get("introduced_date") or "",
                "source_url": selected_bill.get("source_url", ""),
                "raw_latest_action": selected_bill.get("latest_action") or "",
                "website_slug": generate_website_slug(selected_bill.get("title", ""), bill_id),
                "tweet_posted": False,
                "tracker_raw": tracker_raw_serialized,
                "normalized_status": derived_normalized_status,
                "teen_impact_score": teen_impact_score,
            }
            
            logger.info("💾 Inserting new bill into database...")
            if not insert_bill(bill_data):
                logger.error(f"❌ Failed to insert bill {bill_id}")
                return 1
            logger.info("✅ Bill inserted successfully")

        formatted_tweet = format_bill_tweet(bill_data)
        logger.info(f"📝 Formatted tweet length: {len(formatted_tweet)} characters")

        if dry_run:
            logger.info("🔶 DRY-RUN MODE: Skipping tweet and DB update")
            logger.info(f"🔶 Tweet content:\n{formatted_tweet}")
            return 0

        logger.info("🚀 Posting tweet...")
        success, tweet_url = post_tweet(formatted_tweet)

        if success:
            logger.info(f"✅ Tweet posted: {tweet_url}")
            logger.info("💾 Updating database with tweet information...")
            if update_tweet_info(bill_id, tweet_url):
                logger.info("✅ Database updated successfully")
                logger.info("🎉 Orchestrator completed successfully!")
                return 0
            else:
                logger.error("❌ Database update failed. Bill will be marked as problematic.")
                mark_bill_as_problematic(bill_id, "update_tweet_info() returned False")
                return 1
        else:
            logger.error("❌ Failed to post tweet. The bill will be retried in the next run.")
            return 1

    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}", exc_info=True)
        return 1

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="TeenCivics Orchestrator")
    parser.add_argument("--dry-run", action="store_true", help="Run without posting to Twitter or updating DB")
    args = parser.parse_args()
    sys.exit(main(dry_run=args.dry_run))