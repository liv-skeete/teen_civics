#!/usr/bin/env python3
"""
Backfill 'date_introduced' for bills by scraping the Congress.gov bill HTML
and extracting the Introduced date. This fixes records where date_introduced
came from the 'Bill Texts Received Today' feed's text-received date.

Usage:
  - Dry-run for a single bill:
      python3 scripts/backfill_introduced_dates.py --bill-id s284-119

  - Apply changes for a single bill:
      python3 scripts/backfill_introduced_dates.py --bill-id s284-119 --apply

  - Dry-run for all bills:
      python3 scripts/backfill_introduced_dates.py --all

  - Apply for all bills (caution: network intensive):
      python3 scripts/backfill_introduced_dates.py --all --apply
"""

import os
import re
import sys
import time
import argparse
from typing import Optional, Tuple

from dotenv import load_dotenv
load_dotenv()

# Add project root to path so 'src' package is importable when running as a script
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

# DB helpers
from src.database.db import db_connect, normalize_bill_id

# HTML introduced-date extractor and URL helper
from src.fetchers.feed_parser import (
    _extract_introduced_date_from_bill_page,
    construct_bill_url,
    HEADERS,
)

def parse_bill_id(bill_id: str) -> Optional[Tuple[str, str, str]]:
    """
    Parse bill_id like 's284-119' into (bill_type, number, congress).
    Returns None if not parseable.
    """
    if not bill_id:
        return None
    m = re.match(r"^([a-z]+)(\d+)-(\d+)$", bill_id.strip().lower())
    if not m:
        return None
    return m.group(1), m.group(2), m.group(3)

def choose_source_url(db_source_url: Optional[str], bill_id: str) -> Optional[str]:
    """
    Prefer a Congress.gov bill page URL if present; otherwise construct it from bill_id.
    """
    if db_source_url and "congress.gov" in db_source_url and "/bill/" in db_source_url:
        return db_source_url

    parsed = parse_bill_id(bill_id)
    if not parsed:
        return None
    bill_type, number, congress = parsed
    return construct_bill_url(congress, bill_type, number)

def normalize_iso_date(s: Optional[str]) -> Optional[str]:
    """
    Normalize stored date (possibly 'YYYY-MM-DD' or 'YYYY-MM-DDTHH:MM:SSZ') to 'YYYY-MM-DD'.
    Returns None if input is falsy.
    """
    if not s:
        return None
    return s.split("T", 1)[0].strip()

def backfill_one(bill_id: str, apply: bool = False, delay: float = 0.8) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Backfill a single bill. Returns (updated, old_date, new_date).
    """
    bill_id_norm = normalize_bill_id(bill_id)
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT bill_id, source_url, date_introduced FROM bills WHERE bill_id = %s",
                (bill_id_norm,),
            )
            row = cur.fetchone()
            if not row:
                print(f"- Not found: {bill_id_norm}")
                return (False, None, None)

            _, source_url, date_introduced = row
            url = choose_source_url(source_url, bill_id_norm)
            if not url:
                print(f"- Cannot determine source URL for {bill_id_norm}")
                return (False, None, None)

            # Be a polite scraper
            time.sleep(delay)

            html_intro = _extract_introduced_date_from_bill_page(url)
            if not html_intro:
                print(f"- HTML introduced date not found for {bill_id_norm} ({url})")
                return (False, normalize_iso_date(date_introduced), None)

            old_iso = normalize_iso_date(date_introduced)
            new_iso = normalize_iso_date(html_intro)

            if not new_iso:
                print(f"- Parsed introduced date invalid for {bill_id_norm} ({html_intro})")
                return (False, old_iso, None)

            if old_iso == new_iso:
                print(f"= Up-to-date: {bill_id_norm} -> {new_iso}")
                return (False, old_iso, new_iso)

            print(f"* Change needed: {bill_id_norm} {old_iso} -> {new_iso}")
            if apply:
                cur.execute(
                    "UPDATE bills SET date_introduced = %s WHERE bill_id = %s",
                    (new_iso, bill_id_norm),
                )
                conn.commit()
                print(f"✓ Updated: {bill_id_norm} -> {new_iso}")
                return (True, old_iso, new_iso)
            else:
                print(f"(dry-run) Would update: {bill_id_norm} -> {new_iso}")
                return (False, old_iso, new_iso)

def backfill_all(apply: bool = False, limit: Optional[int] = None, delay: float = 0.8) -> None:
    """
    Iterate all bills, compare stored date_introduced vs HTML Introduced date, and update if different.
    Optionally limit number of processed bills for safety.
    """
    processed = 0
    updates = 0
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT bill_id, source_url, date_introduced FROM bills ORDER BY bill_id")
            rows = cur.fetchall()

    for bill_id, source_url, date_introduced in rows:
        if limit is not None and processed >= limit:
            break

        url = choose_source_url(source_url, bill_id)
        old_iso = normalize_iso_date(date_introduced)

        # Be a polite scraper
        time.sleep(delay)

        html_intro = _extract_introduced_date_from_bill_page(url) if url else None
        new_iso = normalize_iso_date(html_intro)
        processed += 1

        if not new_iso:
            print(f"- Skip (no HTML date): {bill_id} (stored={old_iso})")
            continue

        if old_iso == new_iso:
            print(f"= OK: {bill_id} -> {new_iso}")
            continue

        print(f"* Change needed: {bill_id} {old_iso} -> {new_iso}")
        if apply:
            with db_connect() as conn2:
                with conn2.cursor() as cur2:
                    cur2.execute(
                        "UPDATE bills SET date_introduced = %s WHERE bill_id = %s",
                        (new_iso, bill_id),
                    )
                    conn2.commit()
            print(f"✓ Updated: {bill_id} -> {new_iso}")
            updates += 1
        else:
            print(f"(dry-run) Would update: {bill_id} -> {new_iso}")

    print(f"\nSummary: processed={processed}, updates={'applied ' if apply else 'pending '} {updates}")

def main():
    ap = argparse.ArgumentParser(description="Backfill introduced dates from Congress.gov HTML")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--bill-id", help="Specific bill_id like s284-119")
    g.add_argument("--all", action="store_true", help="Process all bills")
    ap.add_argument("--apply", action="store_true", help="Apply updates (default is dry-run)")
    ap.add_argument("--limit", type=int, default=None, help="Limit total bills when using --all")
    ap.add_argument("--delay", type=float, default=0.8, help="Delay between requests (seconds)")

    args = ap.parse_args()

    if args.bill_id:
        backfill_one(args.bill_id, apply=args.apply, delay=args.delay)
    else:
        backfill_all(apply=args.apply, limit=args.limit, delay=args.delay)

if __name__ == "__main__":
    main()