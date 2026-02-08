#!/usr/bin/env python3
"""
Orchestrator script that combines bill fetching, summarization, and posting.
Designed for daily automation via GitHub Actions.
"""

import os
import sys
import logging
import json
import time as time_module  # For time.sleep()
from typing import Dict, Any, Optional
from datetime import datetime, time
import pytz
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.fetchers.feed_parser import fetch_and_enrich_bills, normalize_status
from src.processors.summarizer import summarize_bill_enhanced
from src.publishers.twitter_publisher import post_tweet, format_bill_tweet, validate_tweet_content
from src.publishers.facebook_publisher import FacebookPublisher
from src.database.db import (
    bill_already_posted, get_bill_by_id, insert_bill, update_tweet_info,
    generate_website_slug, init_db, normalize_bill_id,
    select_and_lock_unposted_bill, has_posted_today, mark_bill_as_problematic
)

# NOTE: Substack posting is disabled (Cloudflare blocks datacenter IPs).
# Implementation archived in archives/orchestrator_pre_substack.py

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

def derive_status_from_tracker(tracker: Any) -> tuple[str, str]:
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
            # Build list of candidates to try
            candidates = []
            for bill in bills:
                bill_id = normalize_bill_id(bill.get("bill_id", ""))
                logger.info(f"   📋 Checking bill: {bill_id}")
                if bill_already_posted(bill_id):
                    logger.info(f"   ✅ Bill {bill_id} already tweeted. Skipping.")
                    continue
                
                existing_bill = get_bill_by_id(bill_id)
                if existing_bill:
                    # Skip problematic bills
                    if existing_bill.get("problematic"):
                        logger.info(f"   ⚠️ Bill {bill_id} exists but is marked problematic. Skipping.")
                        continue
                    logger.info(f"   🎯 Bill {bill_id} exists but not tweeted. Adding to candidates.")
                    candidates.append((bill, existing_bill))
                else:
                    ft = (bill.get("full_text") or "").strip()
                    if len(ft) < 100:
                        logger.info(f"   🚫 New bill {bill_id} missing valid full text (len={len(ft)}). Marking problematic and continuing.")
                        mark_bill_as_problematic(bill_id, "No valid full text available during selection")
                        continue
                    logger.info(f"   🆕 Bill {bill_id} is new with full text. Adding to candidates.")
                    candidates.append((bill, None))
        
            
            # If no candidates from API, check DB for unposted bills
            if not candidates:
                logger.info("📭 No new bills from API. Checking DB for any unposted bills...")
                unposted = select_and_lock_unposted_bill()
                if unposted:
                    logger.info(f"   🔄 Found and locked unposted bill in DB: {unposted['bill_id']}")
                    candidates.append(({"bill_id": unposted["bill_id"]}, unposted))
            
            if not candidates:
                logger.info("📭 No unposted bills available. Nothing to do.")
                return 0
            
            # Try each candidate until one succeeds or all fail
            for selected_bill, selected_bill_data in candidates:
                bill_id = normalize_bill_id(selected_bill.get("bill_id", ""))
                logger.info(f"⚙️ Processing candidate bill: {bill_id}")
                
                # Attempt to process this bill
                result = process_single_bill(selected_bill, selected_bill_data, dry_run)
                
                if result == 0:
                    # Success! Exit with success
                    logger.info(f"✅ Successfully processed bill {bill_id}")
                    return 0
                else:
                    # Failed, try next candidate
                    logger.info(f"⏭️  Bill {bill_id} failed processing, trying next candidate...")
                    continue
            
            # If we get here, all candidates failed
            logger.info("📭 All candidates failed processing. No tweet posted this run.")
            return 0  # Return success so workflow doesn't fail

    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}", exc_info=True)
        return 1

def process_single_bill(selected_bill: Dict, selected_bill_data: Optional[Dict], dry_run: bool) -> int:
    """
    Process a single bill candidate. Returns 0 on success, 1 on failure.
    """
    try:
        bill_id = normalize_bill_id(selected_bill.get("bill_id", ""))
        if selected_bill_data:
            logger.info("💾 Using existing summaries from database")
            bill_data = selected_bill_data

            # Backfill sponsor data if missing in DB but available from fresh API
            db_sponsor = (selected_bill_data.get("sponsor_name") or "").strip()
            api_sponsor = (selected_bill.get("sponsor_name") or "").strip()
            if not db_sponsor and api_sponsor:
                logger.info(f"📝 Backfilling missing sponsor data for {bill_id}: {api_sponsor}")
                try:
                    from src.database.db import db_connect
                    with db_connect() as conn:
                        with conn.cursor() as cursor:
                            cursor.execute('''
                                UPDATE bills
                                SET sponsor_name = %s, sponsor_party = %s, sponsor_state = %s
                                WHERE bill_id = %s
                            ''', (
                                selected_bill.get("sponsor_name", ""),
                                selected_bill.get("sponsor_party", ""),
                                selected_bill.get("sponsor_state", ""),
                                bill_id
                            ))
                            conn.commit()
                            logger.info(f"✅ Sponsor data backfilled for {bill_id}")
                            # Update local bill_data as well
                            bill_data["sponsor_name"] = selected_bill.get("sponsor_name", "")
                            bill_data["sponsor_party"] = selected_bill.get("sponsor_party", "")
                            bill_data["sponsor_state"] = selected_bill.get("sponsor_state", "")
                except Exception as e:
                    logger.warning(f"⚠️ Failed to backfill sponsor data for {bill_id}: {e}")

            # Decide whether to regenerate summaries based on DB content
            summary_tweet_existing = (bill_data.get("summary_tweet") or "").strip()
            needs_summary = (len(summary_tweet_existing) < 20) or ("no summary available" in summary_tweet_existing.lower())

            # If we have fresh full text from enrichment and summaries are weak/missing, regenerate
            if needs_summary and len((selected_bill.get("full_text") or "").strip()) >= 100:
                logger.info("🧠 Existing summaries missing/weak; regenerating from fresh full text...")
                tracker_data = selected_bill.get("tracker") or []
                derived_status_text, derived_normalized_status = derive_status_from_tracker(tracker_data)
                selected_bill["status"] = derived_status_text or bill_data.get("status")
                selected_bill["normalized_status"] = derived_normalized_status or bill_data.get("normalized_status")

                # Generate new summaries
                summary = summarize_bill_enhanced(selected_bill)
                logger.info("✅ Summaries generated successfully (regen path)")

                # Validate summary content
                if not summary.get("overview") or "full bill text needed" in summary.get("detailed", "").lower():
                    logger.error(f"❌ Invalid summary generated for bill {bill_id}. Marking as problematic.")
                    mark_bill_as_problematic(bill_id, "Invalid summary content (regen)")
                    return 1

                summary_fields = [summary.get("overview", ""), summary.get("detailed", ""), summary.get("tweet", "")]
                if any("full bill text" in field.lower() for field in summary_fields):
                    logger.error(f"❌ Summary contains 'full bill text' phrase after regen for bill {bill_id}. Marking as problematic.")
                    mark_bill_as_problematic(bill_id, "Summary contains 'full bill text' phrase after regen")
                    return 1

                term_dict_json = ""
                teen_impact_score = extract_teen_impact_score(summary.get("detailed", ""))
                logger.info(f"⭐️ Extracted Teen Impact Score (regen): {teen_impact_score}")

                # Persist regenerated summaries
                try:
                    from src.database.db import update_bill_summaries as _ubs
                    if _ubs(bill_id, summary.get("overview", ""), summary.get("detailed", ""), summary.get("tweet", "")):
                        # Merge updated fields locally for tweet formatting
                        bill_data.update({
                            "summary_tweet": summary.get("tweet", ""),
                            "summary_long": summary.get("long", ""),
                            "summary_overview": summary.get("overview", ""),
                            "summary_detailed": summary.get("detailed", ""),
                            "teen_impact_score": teen_impact_score,
                            "normalized_status": selected_bill.get("normalized_status"),
                            "status": selected_bill.get("status"),
                        })
                        logger.info("💾 Database summaries updated (regen).")
                    else:
                        logger.error("❌ Failed to update summaries in DB after regeneration.")
                        mark_bill_as_problematic(bill_id, "update_bill_summaries failed (regen)")
                        return 1
                except Exception as e:
                    logger.error(f"❌ Exception updating summaries in DB: {e}")
                    mark_bill_as_problematic(bill_id, "Exception updating summaries (regen)")
                    return 1
        else:
            # Derive status from tracker before summarization
            tracker_data = selected_bill.get("tracker") or []
            derived_status_text, derived_normalized_status = derive_status_from_tracker(tracker_data)
            selected_bill["status"] = derived_status_text
            selected_bill["normalized_status"] = derived_normalized_status
            logger.info(f"🧭 Derived status for {bill_id}: '{derived_status_text}' ({derived_normalized_status})")

            # Ensure bill has full text before summarization
            _ft = selected_bill.get("full_text") or ""
            _ts = "api"
            _ft_len = len(_ft.strip())
            try:
                _ft_preview = _ft[:120].replace("\n", " ").replace("\r", " ")
            except Exception:
                _ft_preview = ""
            _preview_suffix = "..." if _ft_len > 80 else ""
            logger.info(f"🔎 Full text precheck for {bill_id}: len={_ft_len}, source={_ts}, preview='{_ft_preview[:80]}{_preview_suffix}'")
            if not _ft or _ft_len < 100:
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
                time_module.sleep(2)  # Small delay before retry
                summary = summarize_bill_enhanced(selected_bill)
                summary_fields = [summary.get("overview", ""), summary.get("detailed", ""), summary.get("tweet", "")]
                if any("full bill text" in field.lower() for field in summary_fields):
                    logger.error(f"❌ Summary still contains 'full bill text' phrase after retry for bill {bill_id}. Marking as problematic.")
                    mark_bill_as_problematic(bill_id, "Summary contains 'full bill text' phrase after retry")
                    return 1
            
            term_dict_json = ""

            teen_impact_score = extract_teen_impact_score(summary.get("detailed", ""))
            logger.info(f"⭐️ Extracted Teen Impact Score: {teen_impact_score}")
            
            # Title length validation and truncation
            raw_title = selected_bill.get("title", "")
            title_length = len(raw_title)
            
            if title_length > 300:
                logger.warning(f"⚠️ Bill title extremely long ({title_length} chars), truncating to 300 chars.")
                logger.warning(f"   Original: \"{raw_title}\"")
                truncated_title = raw_title[:300] + "..."
                logger.warning(f"   Truncated: \"{truncated_title}\"")
                final_title = truncated_title
            elif title_length > 200:
                logger.warning(f"⚠️ Bill title is long ({title_length} chars) but within acceptable range (≤300)")
                logger.info(f"   Title: \"{raw_title}\"")
                final_title = raw_title
            else:
                final_title = raw_title

            bill_data = {
                "bill_id": bill_id,
                "title": final_title,
                "status": derived_status_text,
                "summary_tweet": summary.get("tweet", ""),
                "summary_long": summary.get("long", ""),
                "summary_overview": summary.get("overview", ""),
                "summary_detailed": summary.get("detailed", ""),
                # Ensure these are always populated for UI (avoid N/A)
                "congress_session": str(selected_bill.get("congress", "") or "").strip(),
                "date_introduced": selected_bill.get("date_introduced") or selected_bill.get("introduced_date") or "",
                "source_url": selected_bill.get("source_url", ""),
                "website_slug": generate_website_slug(selected_bill.get("title", ""), bill_id),
                "published": False,
                "normalized_status": derived_normalized_status,
                "teen_impact_score": teen_impact_score,
                # Sponsor data from API
                "sponsor_name": selected_bill.get("sponsor_name", ""),
                "sponsor_party": selected_bill.get("sponsor_party", ""),
                "sponsor_state": selected_bill.get("sponsor_state", ""),
            }
            
            # Warn about missing metadata to help debug future issues
            if not bill_data.get("congress_session"):
                logger.warning(f"⚠️ Bill {bill_id} missing congress_session - will display 'N/A' on site")
            if not bill_data.get("date_introduced"):
                logger.warning(f"⚠️ Bill {bill_id} missing date_introduced - will display 'N/A' on site")
            
            logger.info("💾 Inserting new bill into database...")
            if not insert_bill(bill_data):
                logger.error(f"❌ Failed to insert bill {bill_id}")
                return 1
            logger.info("✅ Bill inserted successfully")

        # Ensure website_slug exists so the link is correct
        if not bill_data.get("website_slug"):
            slug = generate_website_slug(bill_data.get("title", ""), bill_id)
            bill_data["website_slug"] = slug
            logger.info(f"🔗 Set website_slug for {bill_id}: {slug}")

        formatted_tweet = format_bill_tweet(bill_data)
        logger.info(f"📝 Formatted tweet length: {len(formatted_tweet)} characters")

        if dry_run:
            logger.info("🔶 DRY-RUN MODE: Skipping tweet and DB update")
            logger.info(f"🔶 Tweet content:\n{formatted_tweet}")
            return 0

        # Quality gate: validate tweet content before posting
        is_valid, reason = validate_tweet_content(formatted_tweet, bill_data)
        if not is_valid:
            logger.error(f"🚫 Tweet content failed validation for {bill_id}: {reason}")
            # Attempt one-shot summary regeneration when full_text is present
            if bill_data.get("full_text") and len(bill_data.get("full_text", "")) >= 100:
                logger.info(f"🔄 Attempting one-shot summary regeneration for {bill_id}")
                try:
                    # Regenerate summaries
                    summary = summarize_bill_enhanced(bill_data)
                    
                    # Update bill_data with new summaries
                    bill_data["summary_tweet"] = summary.get("tweet", "")
                    bill_data["summary_overview"] = summary.get("overview", "")
                    bill_data["summary_detailed"] = summary.get("detailed", "")
                    bill_data["teen_impact_score"] = extract_teen_impact_score(summary.get("detailed", ""))
                    
                    # Re-format tweet with regenerated summaries
                    formatted_tweet = format_bill_tweet(bill_data)
                    logger.info(f"📝 Re-formatted tweet length: {len(formatted_tweet)} characters")
                    
                    # Re-validate tweet content
                    is_valid, reason = validate_tweet_content(formatted_tweet, bill_data)
                    if not is_valid:
                        logger.error(f"🚫 Tweet content still failed validation after regeneration for {bill_id}: {reason}")
                except Exception as e:
                    logger.error(f"❌ Exception during summary regeneration: {e}")
                    is_valid = False
                    reason = f"Exception during regeneration: {e}"
            else:
                logger.info(f"⏭️  No full text available for regeneration for {bill_id}")
            
            # If still invalid or no full_text, mark bill problematic and continue scanning
            if not is_valid:
                # Mark problematic only in live mode
                mark_bill_as_problematic(bill_id, f"Tweet content failed validation: {reason}")
                logger.info("⛔ Skipping posting due to quality gate.")
                return 1

        # Check environment safety switch
        strict_posting = os.getenv("STRICT_POSTING", "true").lower() == "true"
        if not strict_posting:
            logger.warning("🚨 STRICT_POSTING is disabled! Skipping actual posting.")
            logger.info("🟡 DRY-RUN MODE: Would post tweet:")
            logger.info(f"🔵 Tweet content:\n{formatted_tweet}")
            return 0

        logger.info("🚀 Posting tweet...")
        success, tweet_url = post_tweet(formatted_tweet)

        if success:
            logger.info(f"✅ Tweet posted: {tweet_url}")
            
            # Post to Bluesky (if configured)
            try:
                from src.publishers.bluesky_publisher import BlueskyPublisher
                bluesky = BlueskyPublisher()
                if bluesky.is_configured():
                    logger.info("🦋 Posting to Bluesky...")
                    # Use Bluesky's own format (shorter URLs for 300-char limit)
                    bsky_post = bluesky.format_post(bill_data)
                    bsky_success, bsky_url = bluesky.post(bsky_post)
                    if bsky_success:
                        logger.info(f"✅ Bluesky posted: {bsky_url}")
                    else:
                        logger.warning("⚠️ Bluesky posting failed (non-fatal)")
                else:
                    logger.info("ℹ️ Bluesky not configured, skipping")
            except ImportError:
                logger.info("ℹ️ Bluesky publisher not available, skipping")
            except Exception as e:
                logger.warning(f"⚠️ Bluesky posting error (non-fatal): {e}")
            
            # Post to Threads (if configured)
            try:
                from src.publishers.threads_publisher import ThreadsPublisher
                threads = ThreadsPublisher()
                if threads.is_configured():
                    logger.info("🧵 Posting to Threads...")
                    threads_post = threads.format_post(bill_data)
                    threads_success, threads_url = threads.post(threads_post)
                    if threads_success:
                        logger.info(f"✅ Threads posted: {threads_url}")
                    else:
                        logger.warning("⚠️ Threads posting failed (non-fatal)")
                else:
                    logger.info("ℹ️ Threads not configured, skipping")
            except ImportError:
                logger.info("ℹ️ Threads publisher not available, skipping")
            except Exception as e:
                logger.warning(f"⚠️ Threads posting error (non-fatal): {e}")

            # Post to Facebook (if configured)
            try:
                facebook = FacebookPublisher()
                if facebook.is_configured():
                    logger.info("📘 Posting to Facebook...")
                    facebook_post = facebook.format_post(bill_data)
                    facebook_success, facebook_url = facebook.post(facebook_post)
                    if facebook_success:
                        logger.info(f"✅ Facebook posted: {facebook_url}")
                    else:
                        logger.warning("⚠️ Facebook posting failed (non-fatal)")
                else:
                    logger.info("ℹ️ Facebook not configured, skipping")
            except ImportError:
                logger.info("ℹ️ Facebook publisher not available, skipping")
            except Exception as e:
                logger.warning(f"⚠️ Facebook posting error (non-fatal): {e}")
            
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
