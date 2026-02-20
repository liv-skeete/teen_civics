#!/usr/bin/env python3
"""
Backfill missing ``status`` for bills marked problematic with
"Missing or empty status".

These bills were inserted by an older pipeline that never populated
the ``status`` column.  This script:

  1. Queries all problematic bills whose ``problem_reason`` contains
     "Missing or empty status".
  2. For each, fetches actions from the Congress.gov API (fast, no Playwright).
  3. Derives tracker → ``derive_status_from_tracker()``.
  4. Updates ``status`` and ``normalized_status`` in the DB.
  5. Re-runs ``is_bill_ready_for_posting()`` — if all 12 criteria pass,
     unmarks the bill as problematic.

Dry-run by default.  Pass ``--apply`` to write.

Usage:
    PYTHONPATH=. python3 scripts/backfill_bill_status.py               # dry-run
    PYTHONPATH=. python3 scripts/backfill_bill_status.py --apply        # write
    PYTHONPATH=. python3 scripts/backfill_bill_status.py --limit 50     # cap
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

from src.load_env import load_env

load_env()

import psycopg2
import psycopg2.extras
import requests

from src.database.connection import get_connection_string
from src.orchestrator import derive_status_from_tracker
from src.fetchers.congress_fetcher import derive_tracker_from_actions
from src.utils.validation import is_bill_ready_for_posting

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("backfill_bill_status")

# ---------------------------------------------------------------------------
# Safety guard
# ---------------------------------------------------------------------------

PROD_DATABASE_URL = os.environ.get("PROD_DATABASE_URL", "")


def abort_if_production(db_url: str) -> None:
    raw = os.environ.get("DATABASE_URL", "")
    if PROD_DATABASE_URL and (db_url == PROD_DATABASE_URL or raw == PROD_DATABASE_URL):
        logger.critical("🛑 Refusing to run against production.")
        sys.exit(1)


# ---------------------------------------------------------------------------
# Congress.gov API helpers
# ---------------------------------------------------------------------------

CONGRESS_API_KEY = os.environ.get("CONGRESS_API_KEY", "")
CONGRESS_API_BASE = "https://api.congress.gov/v3"


def parse_bill_id(bill_id: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Parse 'hr1234-119' into (bill_type, bill_number, congress)."""
    m = re.match(r"^([a-z]+)(\d+)-(\d+)$", bill_id.lower())
    if not m:
        return None, None, None
    return m.group(1), m.group(2), m.group(3)


# Map our short bill_type codes to Congress.gov API path segments
BILL_TYPE_MAP = {
    "hr": "hr",
    "s": "s",
    "hjres": "hjres",
    "sjres": "sjres",
    "hconres": "hconres",
    "sconres": "sconres",
    "hres": "hres",
    "sres": "sres",
}


def fetch_bill_actions_from_api(bill_type: str, bill_number: str, congress: str) -> List[Dict[str, Any]]:
    """Fetch bill actions from Congress.gov API.  Returns list of action dicts."""
    api_type = BILL_TYPE_MAP.get(bill_type, bill_type)
    url = f"{CONGRESS_API_BASE}/bill/{congress}/{api_type}/{bill_number}/actions"
    params = {"api_key": CONGRESS_API_KEY, "format": "json", "limit": 250}
    try:
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        return data.get("actions", [])
    except Exception as e:
        logger.warning(f"  API error for {bill_type}{bill_number}-{congress}: {e}")
        return []


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------


def fetch_missing_status_bills(conn, limit: int = 500) -> List[Dict[str, Any]]:
    """Fetch problematic bills whose reason is 'Missing or empty status'."""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        query = """
            SELECT *
            FROM bills
            WHERE problematic = TRUE
              AND problem_reason LIKE '%%Missing or empty status%%'
            ORDER BY date_introduced DESC NULLS LAST
        """
        if limit > 0:
            query += " LIMIT %s"
            cur.execute(query, (limit,))
        else:
            cur.execute(query)
        return [dict(row) for row in cur.fetchall()]


def update_bill_status(conn, bill_id: str, status: str, normalized_status: str) -> bool:
    """Update status and normalized_status columns."""
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE bills
                SET status = %s,
                    normalized_status = %s
                WHERE bill_id = %s
                """,
                (status, normalized_status, bill_id),
            )
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        logger.error(f"  Failed to update status for {bill_id}: {e}")
        return False


def unmark_problematic(conn, bill_id: str) -> bool:
    """Unmark a bill as problematic."""
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE bills
                SET problematic = FALSE,
                    problem_reason = NULL,
                    problematic_marked_at = NULL,
                    recheck_attempted = FALSE
                WHERE bill_id = %s
                """,
                (bill_id,),
            )
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        logger.error(f"  Failed to unmark {bill_id}: {e}")
        return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill missing status for problematic bills."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        default=False,
        help="Actually write status updates to DB (default: dry-run).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Max bills to process (0 = unlimited, default: 0).",
    )
    args = parser.parse_args()

    if not CONGRESS_API_KEY:
        logger.error("CONGRESS_API_KEY is not set. Aborting.")
        sys.exit(1)

    db_url = get_connection_string()
    if not db_url:
        logger.error("DATABASE_URL is not set. Aborting.")
        sys.exit(1)

    abort_if_production(db_url)

    connect_url = db_url
    if "sslmode" not in connect_url:
        sep = "&" if "?" in connect_url else "?"
        connect_url += f"{sep}sslmode=require"

    conn = psycopg2.connect(connect_url)
    conn.autocommit = False

    try:
        logger.info(f"Fetching problematic bills with 'Missing or empty status'...")
        bills = fetch_missing_status_bills(conn, limit=args.limit)
        logger.info(f"Found {len(bills)} bills to backfill.")

        if not bills:
            print("\n  No bills with 'Missing or empty status' found. Nothing to do.\n")
            return

        status_derived = 0
        status_failed = 0
        unmarked = 0
        still_problematic = 0

        for i, bill in enumerate(bills):
            bill_id = bill.get("bill_id", "???")
            bill_type, bill_number, congress = parse_bill_id(bill_id)

            if not bill_type or not bill_number or not congress:
                logger.warning(f"  [{i+1}/{len(bills)}] Cannot parse bill_id: {bill_id}")
                status_failed += 1
                continue

            # Fetch actions from API
            actions = fetch_bill_actions_from_api(bill_type, bill_number, congress)
            if not actions:
                logger.warning(f"  [{i+1}/{len(bills)}] {bill_id}: No actions from API")
                status_failed += 1
                continue

            # Derive tracker from actions
            tracker = derive_tracker_from_actions(actions)
            if not tracker:
                logger.warning(f"  [{i+1}/{len(bills)}] {bill_id}: Could not derive tracker")
                status_failed += 1
                continue

            # Derive status
            status_text, normalized = derive_status_from_tracker(tracker)
            if not status_text:
                logger.warning(f"  [{i+1}/{len(bills)}] {bill_id}: Empty status derived")
                status_failed += 1
                continue

            logger.info(f"  [{i+1}/{len(bills)}] {bill_id}: status='{status_text}', normalized='{normalized}'")

            if args.apply:
                if update_bill_status(conn, bill_id, status_text, normalized):
                    status_derived += 1

                    # Re-check if bill is now post-ready
                    updated_bill = dict(bill)
                    updated_bill["status"] = status_text
                    updated_bill["normalized_status"] = normalized
                    ready, reason = is_bill_ready_for_posting(updated_bill)

                    if ready:
                        if unmark_problematic(conn, bill_id):
                            unmarked += 1
                            logger.info(f"    ✅ Now post-ready — unmarked as problematic")
                        else:
                            still_problematic += 1
                    else:
                        still_problematic += 1
                        logger.info(f"    ⚠️ Status filled but still not post-ready: {reason}")
                else:
                    status_failed += 1
            else:
                status_derived += 1
                # Check if it would be post-ready
                updated_bill = dict(bill)
                updated_bill["status"] = status_text
                updated_bill["normalized_status"] = normalized
                ready, reason = is_bill_ready_for_posting(updated_bill)
                if ready:
                    unmarked += 1
                else:
                    still_problematic += 1

            # Rate limit: 1 req/sec to be polite to Congress.gov API
            if i < len(bills) - 1:
                time.sleep(0.5)

        # Summary
        mode = "APPLY" if args.apply else "DRY-RUN"
        print()
        print("=" * 72)
        print(f"  BACKFILL STATUS ({mode})")
        print("=" * 72)
        print(f"  Total bills processed:          {len(bills)}")
        print(f"  ✅ Status derived successfully:  {status_derived}")
        print(f"  ❌ Status derivation failed:     {status_failed}")
        print(f"  🟢 Would become post-ready:      {unmarked}")
        print(f"  🟡 Still problematic (other):    {still_problematic}")
        print("=" * 72)
        print()

    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        conn.rollback()
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
