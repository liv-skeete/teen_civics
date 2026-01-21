#!/usr/bin/env python3
"""
Reprocess the most recent N archived (tweeted) bills using the upgraded summarizer pipeline.

Default behavior:
- Selects from the most recently processed bills (date_processed DESC)
- Filters to tweeted-only (archive) bills
- Regenerates overview, detailed, long, term_dictionary using summarize_bill_enhanced
- Updates only those fields in the database (does not modify summary_tweet)

Usage:
  python3 scripts/reprocess_recent_bills.py --limit 25
  python3 scripts/reprocess_recent_bills.py --limit 25 --dry-run
  python3 scripts/reprocess_recent_bills.py --limit 25 --include-untweeted
"""

import os
import sys
import json
import logging
import argparse
from typing import List, Dict, Any

# Add the project root to the Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

from src.database.db_utils import get_all_bills, update_bill_summaries
from src.processors.summarizer import summarize_bill_enhanced

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
log = logging.getLogger(__name__)


def select_recent_bills(limit: int, fetch_limit: int, tweeted_only: bool) -> List[Dict[str, Any]]:
    """
    Fetch a larger batch of most recent bills and return the first 'limit' after filtering.
    """
    all_recent = get_all_bills(limit=fetch_limit) or []
    if tweeted_only:
        all_recent = [b for b in all_recent if b.get('tweet_posted')]
    selected = all_recent[:limit]
    log.info(f"Selected {len(selected)} bills (tweeted_only={tweeted_only}; requested={limit}; fetched={len(all_recent)})")
    return selected


def main(limit: int, fetch_limit: int, tweeted_only: bool, dry_run: bool) -> int:
    log.info("=" * 60)
    log.info("Reprocessing recent bills with upgraded summarizer (Claude Sonnet 4-5)")
    log.info("=" * 60)
    log.info(f"Parameters: limit={limit}, fetch_limit={fetch_limit}, tweeted_only={tweeted_only}, dry_run={dry_run}")

    bills = select_recent_bills(limit=limit, fetch_limit=fetch_limit, tweeted_only=tweeted_only)
    if not bills:
        log.error("No bills selected for reprocessing. Aborting.")
        return 1

    successes = 0
    failures = 0

    for i, bill in enumerate(bills, 1):
        bill_id = bill.get('bill_id')
        title = bill.get('title', '') or ''
        log.info("")
        log.info("-" * 60)
        log.info(f"[{i}/{len(bills)}] Reprocessing bill_id={bill_id} title={title[:120]}...")
        log.info("-" * 60)

        try:
            # Summarize using enhanced pipeline
            summaries = summarize_bill_enhanced(bill)
            if not isinstance(summaries, dict):
                log.error(f"Summarizer returned non-dict for {bill_id}: {type(summaries)}")
                failures += 1
                continue

            overview = summaries.get('overview') or ""
            detailed = summaries.get('detailed') or ""
            long_sum = summaries.get('long') or summaries.get('detailed') or ""
            term_dict_obj = summaries.get('term_dictionary') or []
            # Store term_dictionary as compact JSON in DB text column
            term_dict_json = json.dumps(term_dict_obj, ensure_ascii=False, separators=(',', ':'))

            log.info(f"Lengths → overview={len(overview)}, detailed={len(detailed)}, long={len(long_sum)}, term_dictionary={len(term_dict_json)}")

            if dry_run:
                log.info(f"[DRY-RUN] Would update DB for {bill_id}")
                successes += 1
                continue

            # Update DB (overview, detailed, term_dictionary, long)
            updated = update_bill_summaries(
                bill_id,
                summary_overview=overview,
                summary_detailed=detailed,
                term_dictionary=term_dict_json,
                summary_long=long_sum
            )
            if updated:
                log.info(f"✓ Updated summaries for {bill_id}")
                successes += 1
            else:
                log.error(f"✗ Failed to update summaries for {bill_id}")
                failures += 1

        except Exception as e:
            log.exception(f"Unhandled error while reprocessing {bill_id}: {e}")
            failures += 1

    log.info("")
    log.info("=" * 60)
    log.info("Reprocessing results")
    log.info("=" * 60)
    log.info(f"Total processed: {len(bills)}")
    log.info(f"Successful:     {successes}")
    log.info(f"Failed:         {failures}")

    return 0 if failures == 0 else 2


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Reprocess the most recent N bills using the enhanced summarizer.")
    parser.add_argument("--limit", type=int, default=25, help="Number of recent bills to reprocess (default: 25)")
    parser.add_argument(
        "--fetch-limit", type=int, default=200,
        help="How many recent bills to fetch before filtering; helps when tweeted_only is set (default: 200)"
    )
    parser.add_argument(
        "--include-untweeted", action="store_true",
        help="Include bills that have not been tweeted yet (default: False)"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Do not write updates to DB; just run summarizer and log results"
    )
    args = parser.parse_args()

    tweeted_only = not args.include_untweeted
    exit_code = main(limit=args.limit, fetch_limit=args.fetch_limit, tweeted_only=tweeted_only, dry_run=args.dry_run)
    sys.exit(exit_code)