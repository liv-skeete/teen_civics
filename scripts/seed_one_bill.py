#!/usr/bin/env python3
"""
Seed the local database with the most recent bill from Congress.gov
without tweeting. This is useful when the homepage shows "No bills available".

Requirements:
- CONGRESS_API_KEY in environment
- ANTHROPIC_API_KEY in environment
"""

import os
import sys
import logging
from dotenv import load_dotenv

# Ensure project root on path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger("seed_one_bill")

def main():
    try:
        # DB/API modules
        from src.fetchers.congress_fetcher import get_recent_bills
        from src.processors.summarizer import summarize_bill_enhanced
        from src.database.db import (
            bill_exists, insert_bill, generate_website_slug
        )

        # Fetch 1 most recent bill including full text (HTML/TXT/XML/PDF)
        log.info("Fetching 1 recent bill with full text ...")
        bills = get_recent_bills(limit=1, include_text=True, text_chars=2_000_000)
        if not bills:
            log.error("No bills returned from Congress.gov API")
            return 2

        bill = bills[0]
        bill_id = bill.get("bill_id", "unknown")
        log.info(f"Fetched bill {bill_id}")

        # Skip if exists
        if bill_exists(bill_id):
            log.info(f"Bill {bill_id} already exists in DB; nothing to seed.")
            return 0

        # Summarize using enhanced format (overview, detailed, term_dictionary, tweet, long)
        log.info("Summarizing bill with enhanced pipeline...")
        summary = summarize_bill_enhanced(bill)

        tweet_text = (summary.get("tweet") or "").strip()
        long_summary = (summary.get("long") or "").strip()
        overview = (summary.get("overview") or "").strip()
        detailed = (summary.get("detailed") or "").strip()
        term_dictionary = (summary.get("term_dictionary") or "").strip()

        if not long_summary:
            log.error("Enhanced summary missing 'long' content; aborting seed.")
            return 3

        website_slug = generate_website_slug(bill.get("title", "") or bill_id, bill_id)

        # Prepare DB row
        bill_data = {
            "bill_id": bill_id,
            "title": bill.get("title", ""),
            "short_title": bill.get("short_title", ""),
            "status": bill.get("latest_action", {}).get("text", "") or bill.get("status", ""),
            "summary_tweet": tweet_text,
            "summary_long": long_summary,
            "summary_overview": overview,
            "summary_detailed": detailed,
            "term_dictionary": term_dictionary,
            "congress_session": bill.get("congress", ""),
            "date_introduced": bill.get("introduced_date", ""),
            "source_url": bill.get("congressdotgov_url", "") or bill.get("text_url", "") or "",
            "website_slug": website_slug,
            "tags": "",
            "tweet_posted": False,
            "tweet_url": None,
        }

        ok = insert_bill(bill_data)
        if not ok:
            log.error("Failed to insert bill into DB")
            return 4

        log.info(f"Seed complete. Inserted bill {bill_id} with slug '{website_slug}'")
        print(website_slug)
        return 0

    except Exception as e:
        log.exception(f"Seed failed: {e}")
        return 1

if __name__ == "__main__":
    raise SystemExit(main())