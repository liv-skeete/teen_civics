#!/usr/bin/env python3
"""
Backfill argument_support / argument_oppose for existing bills that have
summaries but no pre-generated arguments.

Uses the same fallback chain as the orchestrator insert path:
  1. Opus 4.6 via Venice AI
  2. Sonnet 4.6 via Venice AI
  3. Extract key provisions from summary_detailed
  4. Generic template (absolute last resort)

Usage:
    PYTHONPATH=. python3 scripts/backfill_arguments.py                # all missing
    PYTHONPATH=. python3 scripts/backfill_arguments.py --limit 10     # cap at 10
    PYTHONPATH=. python3 scripts/backfill_arguments.py --dry-run      # preview only
"""

import os
import sys
import time
import logging
import argparse

# Ensure project root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from src.database.connection import postgres_connect
from src.database.db import update_bill_arguments
from src.processors.argument_generator import generate_bill_arguments

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

RATE_LIMIT_SECONDS = float(os.getenv("BACKFILL_RATE_LIMIT", "1.5"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Fetch bills needing arguments
# ---------------------------------------------------------------------------

def fetch_bills_without_arguments(limit: int = 0):
    """
    Return a list of dicts for bills that have a summary_overview but are
    missing argument_support or argument_oppose.
    """
    query = """
        SELECT bill_id, title, summary_overview, summary_detailed
        FROM bills
        WHERE (argument_support IS NULL OR argument_support = ''
               OR argument_oppose IS NULL OR argument_oppose = '')
          AND summary_overview IS NOT NULL
          AND summary_overview != ''
        ORDER BY date_processed DESC
    """
    if limit and limit > 0:
        query += f" LIMIT {int(limit)}"

    rows = []
    with postgres_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            cols = [d[0] for d in cur.description]
            for row in cur.fetchall():
                rows.append(dict(zip(cols, row)))
    return rows


# ---------------------------------------------------------------------------
# Main backfill loop
# ---------------------------------------------------------------------------

def backfill(limit: int = 0, dry_run: bool = False):
    bills = fetch_bills_without_arguments(limit)
    total = len(bills)
    logger.info(f"📋 Found {total} bills needing argument backfill"
                + (f" (capped at {limit})" if limit else ""))

    if total == 0:
        logger.info("✅ Nothing to backfill — all bills have arguments.")
        return

    success = 0
    failed = 0

    for i, bill in enumerate(bills, 1):
        bid = bill["bill_id"]
        title = bill.get("title") or ""
        overview = bill.get("summary_overview") or ""
        detailed = bill.get("summary_detailed") or ""

        logger.info(f"[{i}/{total}] Processing {bid}: {title[:60]}...")

        try:
            args = generate_bill_arguments(
                bill_title=title,
                summary_overview=overview,
                summary_detailed=detailed,
            )
            support = args.get("support", "")
            oppose = args.get("oppose", "")

            if not support or not oppose:
                logger.warning(f"  ⚠️  Empty argument returned for {bid}, skipping.")
                failed += 1
                continue

            logger.info(f"  ✅ support={len(support)} chars, oppose={len(oppose)} chars")

            if dry_run:
                logger.info(f"  🔶 DRY-RUN: would update {bid}")
                logger.info(f"     support: {support[:80]}...")
                logger.info(f"     oppose:  {oppose[:80]}...")
            else:
                ok = update_bill_arguments(bid, support, oppose)
                if ok:
                    logger.info(f"  💾 Updated {bid} in database.")
                else:
                    logger.warning(f"  ❌ DB update failed for {bid}.")
                    failed += 1
                    continue

            success += 1
        except Exception as e:
            logger.error(f"  ❌ Exception processing {bid}: {e}")
            failed += 1

        # Rate limit between API calls
        if i < total:
            time.sleep(RATE_LIMIT_SECONDS)

    logger.info("=" * 60)
    logger.info(f"🏁 Backfill complete: {success} succeeded, {failed} failed, {total} total")
    logger.info("=" * 60)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill argument_support/oppose for existing bills")
    parser.add_argument("--limit", type=int, default=0, help="Max bills to process (0 = all)")
    parser.add_argument("--dry-run", action="store_true", help="Preview only, no DB writes")
    args = parser.parse_args()
    backfill(limit=args.limit, dry_run=args.dry_run)
