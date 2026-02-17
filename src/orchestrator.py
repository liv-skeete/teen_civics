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

from src.fetchers.feed_parser import fetch_and_enrich_bills, normalize_status, fetch_bill_ids_from_texts_received_today, enrich_single_bill
from src.processors.summarizer import summarize_bill_enhanced
from src.publishers.twitter_publisher import post_tweet, format_bill_tweet, validate_tweet_content
from src.publishers.facebook_publisher import FacebookPublisher
from src.database.db import (
    bill_already_posted, get_bill_by_id, insert_bill, update_tweet_info,
    generate_website_slug, init_db, normalize_bill_id,
    select_and_lock_unposted_bill, has_posted_today, mark_bill_as_problematic,
    get_all_problematic_bills, unmark_bill_as_problematic,
    update_bill_title, update_bill_full_text,
    mark_recheck_attempted,
)
from src.utils.validation import validate_bill_data

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
    
    Uses a lazy enrichment strategy:
    1. Phase 1 (Fast): Fetch just the bill IDs from "Texts Received Today" (~10s)
    2. Phase 2 (Fast): Filter out bills already in DB (already posted)
    3. Phase 3 (Lazy): Enrich candidate bills ONE AT A TIME until one posts successfully
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

        # ── Phase 1+2+3: Scrape → Filter → Process (with re-scrape retry) ─
        MAX_SCRAPE_ATTEMPTS = 2  # Cap re-scrapes to avoid infinite loops
        for scrape_attempt in range(1, MAX_SCRAPE_ATTEMPTS + 1):
            logger.info(f"🔄 Scrape attempt {scrape_attempt}/{MAX_SCRAPE_ATTEMPTS}")

            # ── Phase 1 (Fast): Fetch bill IDs only ──────────────────────────
            phase1_start = time_module.time()
            logger.info("📥 Phase 1: Fetching bill IDs from 'Texts Received Today'...")
            bill_ids = fetch_bill_ids_from_texts_received_today()
            phase1_elapsed = time_module.time() - phase1_start
            logger.info(f"⏱️ Phase 1: Fetched {len(bill_ids)} bill IDs in {phase1_elapsed:.1f}s")

            if not bill_ids and scrape_attempt < MAX_SCRAPE_ATTEMPTS:
                logger.info("📭 No bill IDs found on first scrape. Will re-scrape after a short delay...")
                time_module.sleep(5)
                continue  # retry the scrape

            # ── Phase 2 (Fast): Filter out already-posted / problematic bills ─
            phase2_start = time_module.time()
            logger.info("🔍 Phase 2: Filtering candidates against database...")
            candidate_ids = []
            db_hit_bills = []  # Bills in DB but not yet posted (can skip enrichment)
            problematic_from_feed = []  # Problematic bills that appeared in today's feed (re-check candidates)
            for bid in bill_ids:
                bid = normalize_bill_id(bid)
                if bill_already_posted(bid):
                    logger.info(f"   ✅ {bid} already posted. Skipping.")
                    continue
                existing = get_bill_by_id(bid)
                if existing:
                    if existing.get("problematic"):
                        # Skip bills whose single recheck has already been attempted
                        if existing.get("recheck_attempted"):
                            logger.info(f"   🔒 {bid} already rechecked once and still problematic. Permanently skipping.")
                            continue
                        logger.info(f"   🔄 {bid} marked problematic but in today's feed. Queuing for re-check.")
                        problematic_from_feed.append((bid, existing))
                        continue
                    logger.info(f"   🎯 {bid} in DB but not posted. Adding as priority candidate.")
                    db_hit_bills.append((bid, existing))
                else:
                    logger.info(f"   🆕 {bid} is new. Adding to enrichment candidates.")
                    candidate_ids.append(bid)
            phase2_elapsed = time_module.time() - phase2_start
            logger.info(f"⏱️ Phase 2: Filtered to {len(db_hit_bills)} DB hits + {len(candidate_ids)} new + {len(problematic_from_feed)} problematic-recheck in {phase2_elapsed:.1f}s")

            # If no candidates after filtering and we can re-scrape, do so
            if not db_hit_bills and not candidate_ids and not problematic_from_feed and scrape_attempt < MAX_SCRAPE_ATTEMPTS:
                logger.info("📭 All feed bills filtered out. Will re-scrape after short delay...")
                time_module.sleep(5)
                continue

            # ── Phase 3 (Lazy): Process candidates one at a time ─────────────
            phase3_start = time_module.time()
            logger.info("⚙️ Phase 3: Processing candidates (lazy enrichment)...")

            # 3a) Try DB-hit bills first (already have data, no enrichment needed)
            for bid, existing_data in db_hit_bills:
                logger.info(f"⚙️ Processing DB candidate: {bid}")
                result = process_single_bill({"bill_id": bid}, existing_data, dry_run)
                if result == 0:
                    phase3_elapsed = time_module.time() - phase3_start
                    logger.info(f"⏱️ Phase 3: Successfully processed {bid} in {phase3_elapsed:.1f}s")
                    logger.info(f"✅ Successfully processed bill {bid}")
                    return 0
                else:
                    logger.info(f"⏭️  DB candidate {bid} failed processing, trying next...")

            # 3a½) Re-check problematic bills that appeared in today's feed.
            #       Only eligible if 15+ days since marked AND not yet rechecked.
            #       Each bill gets exactly ONE recheck; after that it's locked out.
            for bid, prob_data in problematic_from_feed:
                prob_reason = prob_data.get("problem_reason", "")

                # Enforce 15-day cooling-off period per bill
                marked_at = prob_data.get("problematic_marked_at")
                if marked_at:
                    from datetime import timezone
                    now_utc = datetime.now(timezone.utc)
                    if hasattr(marked_at, 'tzinfo') and marked_at.tzinfo is None:
                        marked_at = marked_at.replace(tzinfo=timezone.utc)
                    days_since = (now_utc - marked_at).days
                    if days_since < 15:
                        logger.info(f"   ⏳ {bid} marked problematic only {days_since}d ago (need 15d). Skipping recheck.")
                        continue

                logger.info(f"🔄 Re-enriching problematic feed bill {bid} (reason: {prob_reason})")

                # Mark recheck_attempted BEFORE the attempt so even if it crashes,
                # the bill won't be retried endlessly.
                mark_recheck_attempted(bid)

                try:
                    enriched = enrich_single_bill(bid)
                except Exception as e:
                    logger.warning(f"   ❌ Re-enrichment failed for {bid}: {e}")
                    continue

                if not enriched:
                    logger.info(f"   ⏭️  Enrichment still returns None for {bid}. Locked out from future rechecks.")
                    continue

                # Re-evaluate whether the bill now passes validation
                new_title = (enriched.get("title") or "").strip()
                old_title = (prob_data.get("title") or "").strip()
                
                # Check validation using the shared utility
                # Pass 'enriched' which has the latest API data
                is_valid_now, validation_reasons = validate_bill_data(enriched)

                if not is_valid_now:
                    reason_str = "; ".join(validation_reasons)
                    logger.info(f"   ⏭️  {bid} still problematic after recheck: {reason_str}. Locked out from future rechecks.")
                    continue

                # Bill data has improved — update DB and unmark problematic
                logger.info(f"   ✅ {bid} now has valid data. Unmarking problematic and processing.")
                
                # Update individual fields if they improved
                if new_title and new_title != old_title:
                    update_bill_title(bid, new_title)
                
                # Full text update is handled implicitly by validation check + below
                new_ft = (enriched.get("full_text") or "").strip()
                if len(new_ft) >= 100:
                    update_bill_full_text(bid, new_ft)
                    
                unmark_bill_as_problematic(bid)

                # Try to process and post the recovered bill
                refreshed = get_bill_by_id(bid)
                if refreshed:
                    result = process_single_bill(
                        {**enriched, "bill_id": bid},
                        refreshed,
                        dry_run
                    )
                    if result == 0:
                        phase3_elapsed = time_module.time() - phase3_start
                        logger.info(f"⏱️ Phase 3: Successfully posted recovered feed bill {bid} in {phase3_elapsed:.1f}s")
                        return 0
                    else:
                        logger.info(f"   ⏭️  Recovered feed bill {bid} failed processing, trying next...")

            # 3b) Enrich new candidates one at a time
            for bid in candidate_ids:
                logger.info(f"🔧 Enriching new candidate: {bid}")
                enrich_start = time_module.time()
                try:
                    enriched = enrich_single_bill(bid)
                except Exception as e:
                    logger.warning(f"❌ Enrichment failed for {bid}: {e}")
                    continue
                enrich_elapsed = time_module.time() - enrich_start
                logger.info(f"⏱️ Enriched {bid} in {enrich_elapsed:.1f}s")

                if not enriched:
                    logger.warning(f"⏭️  Enrichment returned None for {bid}, skipping.")
                    continue

                # Validate full text before processing
                ft = (enriched.get("full_text") or "").strip()
                # Use shared validator for new feed candidates
                is_valid, validation_reasons = validate_bill_data(enriched)
                if not is_valid:
                    reason_str = "; ".join(validation_reasons)
                    logger.info(f"   🚫 {bid} incomplete data: {reason_str}. Marking problematic.")
                    mark_bill_as_problematic(bid, f"Validation failed: {reason_str}")
                    continue

                logger.info(f"⚙️ Processing enriched candidate: {bid}")
                result = process_single_bill(enriched, None, dry_run)
                if result == 0:
                    phase3_elapsed = time_module.time() - phase3_start
                    logger.info(f"⏱️ Phase 3: Successfully processed {bid} in {phase3_elapsed:.1f}s")
                    logger.info(f"✅ Successfully processed bill {bid}")
                    return 0
                else:
                    logger.info(f"⏭️  Enriched candidate {bid} failed processing, trying next...")

            # 3c) Fallback: check DB for any unposted bills
            logger.info("📭 No candidates from feed succeeded. Checking DB for unposted bills...")
            unposted = select_and_lock_unposted_bill()
            if unposted:
                bid = unposted['bill_id']
                logger.info(f"   🔄 Found and locked unposted bill in DB: {bid}")
                result = process_single_bill({"bill_id": bid}, unposted, dry_run)
                if result == 0:
                    phase3_elapsed = time_module.time() - phase3_start
                    logger.info(f"⏱️ Phase 3: Successfully processed {bid} in {phase3_elapsed:.1f}s")
                    return 0

            phase3_elapsed = time_module.time() - phase3_start
            logger.info(f"⏱️ Phase 3: All candidates exhausted in {phase3_elapsed:.1f}s (scrape attempt {scrape_attempt})")

            # If we still have scrape attempts left, loop back for a re-scrape
            if scrape_attempt < MAX_SCRAPE_ATTEMPTS:
                logger.info("🔁 Re-scraping feed to look for newly available bills...")
                time_module.sleep(5)
                continue

            # All scrape attempts exhausted — break out to Phase 4
            break

        # ── Phase 4: Problematic-bill recovery (single recheck, 15-day delay) ─
        # get_all_problematic_bills now only returns bills where:
        #   - problematic_marked_at is 15+ days ago
        #   - recheck_attempted is FALSE
        # Each bill gets exactly ONE recheck attempt here.
        logger.info("🔍 Phase 4: Re-checking eligible problematic bills (15-day delay, single attempt)...")
        phase4_start = time_module.time()
        problematic_bills = get_all_problematic_bills(limit=20)
        logger.info(f"   Found {len(problematic_bills)} problematic bills eligible for recheck.")

        recovered_count = 0
        for prob_bill in problematic_bills:
            pbid = prob_bill.get("bill_id", "")
            prob_reason = prob_bill.get("problem_reason", "")
            logger.info(f"   🔎 Re-checking {pbid} (reason: {prob_reason})")

            # Mark recheck_attempted BEFORE the attempt so even on crash
            # this bill won't be retried indefinitely.
            mark_recheck_attempted(pbid)

            # Re-enrich from the API to see if title/full_text are now available
            try:
                enriched = enrich_single_bill(pbid)
            except Exception as e:
                logger.warning(f"   ❌ Re-enrichment failed for {pbid}: {e}. Locked out from future rechecks.")
                continue

            if not enriched:
                logger.info(f"   ⏭️  Enrichment still returns None for {pbid}. Locked out from future rechecks.")
                continue

            # Check if the bill now passes shared validation rules
            new_title = (enriched.get("title") or "").strip()
            old_title = (prob_bill.get("title") or "").strip()
            
            is_valid_now, validation_reasons = validate_bill_data(enriched)

            if not is_valid_now:
                reason_str = "; ".join(validation_reasons)
                logger.info(f"   ⏭️  {pbid} still problematic after recheck: {reason_str}. Locked out from future rechecks.")
                continue

            # Bill has improved — update DB fields and unmark
            logger.info(f"   ✅ {pbid} now has valid data. Unmarking problematic.")
            recovered_count += 1

            if new_title and new_title != old_title:
                update_bill_title(pbid, new_title)

            new_ft = (enriched.get("full_text") or "").strip()
            if len(new_ft) >= 100:
                update_bill_full_text(pbid, new_ft)

            unmark_bill_as_problematic(pbid)

            # Attempt to process and post the recovered bill
            logger.info(f"   🚀 Attempting to process recovered bill {pbid}...")
            refreshed = get_bill_by_id(pbid)
            if refreshed:
                result = process_single_bill(
                    {**enriched, "bill_id": pbid},
                    refreshed,
                    dry_run
                )
                if result == 0:
                    phase4_elapsed = time_module.time() - phase4_start
                    logger.info(f"⏱️ Phase 4: Successfully posted recovered bill {pbid} in {phase4_elapsed:.1f}s")
                    return 0
                else:
                    logger.info(f"   ⏭️  Recovered bill {pbid} failed processing, continuing...")

        phase4_elapsed = time_module.time() - phase4_start
        logger.info(f"⏱️ Phase 4: Checked {len(problematic_bills)} problematic bills, recovered {recovered_count}, in {phase4_elapsed:.1f}s")
        logger.info("📭 No bills could be posted this run (all phases exhausted).")
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

        # Safety check: refuse to process bills with no title (placeholder rows)
        effective_title = (
            (selected_bill_data or {}).get("title") or
            selected_bill.get("title") or ""
        ).strip()
        if not effective_title:
            logger.error(f"🚫 Bill {bill_id} has no title — cannot process. Marking as problematic.")
            mark_bill_as_problematic(bill_id, "No title available from API or DB")
            return 1

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
                    if _ubs(bill_id, summary.get("overview", ""), summary.get("detailed", ""), summary.get("tweet", ""), subject_tags=summary.get("subject_tags", "")):
                        # Merge updated fields locally for tweet formatting
                        bill_data.update({
                            "summary_tweet": summary.get("tweet", ""),
                            "summary_long": summary.get("long", ""),
                            "summary_overview": summary.get("overview", ""),
                            "summary_detailed": summary.get("detailed", ""),
                            "teen_impact_score": teen_impact_score,
                            "normalized_status": selected_bill.get("normalized_status"),
                            "status": selected_bill.get("status"),
                            "subject_tags": summary.get("subject_tags", ""),
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
                # Subject tags from AI summarizer
                "subject_tags": summary.get("subject_tags", ""),
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

        # ── HARD VALIDATION GATE ──
        # Final check before ANY posting: bill MUST have complete data.
        # This catches bills that leak through from DB fallback paths or
        # incomplete enrichment regardless of which phase called us.
        is_complete, missing_reasons = validate_bill_data(bill_data)
        if not is_complete:
            reason_str = "; ".join(missing_reasons)
            logger.error(f"🚫 FINAL GATE: Bill {bill_id} has incomplete data: {reason_str}. Blocking from posting.")
            mark_bill_as_problematic(bill_id, f"Final gate: {reason_str}")
            return 1

        # Also block if status is literally "problematic"
        bill_status = (bill_data.get("status") or "").strip().lower()
        if bill_status == "problematic":
            logger.error(f"🚫 FINAL GATE: Bill {bill_id} status is 'problematic'. Blocking from posting.")
            mark_bill_as_problematic(bill_id, "Status is still 'problematic'")
            return 1

        # Block if summary_tweet is too short or looks like a placeholder
        summary_tweet = (bill_data.get("summary_tweet") or "").strip()
        if len(summary_tweet) < 20:
            logger.error(f"🚫 FINAL GATE: Bill {bill_id} has no usable summary_tweet ({len(summary_tweet)} chars). Blocking.")
            mark_bill_as_problematic(bill_id, f"summary_tweet too short ({len(summary_tweet)} chars)")
            return 1

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
