#!/usr/bin/env python3
"""
One-time cleanup for "limbo" bills: unpublished, not problematic, but NOT
actually ready to post (missing summaries, sponsor, teen_impact_score, etc.).

These bills inflate get_unposted_count() without being postable, creating a
phantom reservoir that prevents new bills from being scraped.

Behaviour:
  - DRY-RUN (default): queries all limbo bills, runs is_bill_ready_for_posting()
    on each, and prints a summary report.  Zero DB writes.
  - APPLY mode (--apply): marks each failing bill as problematic so the daily
    pipeline skips them and the periodic recheck can try to heal them later.

Safety:
  - Aborts if DATABASE_URL matches PROD_DATABASE_URL (production guard).
  - Always prints a detailed report before writing anything.
  - Use --limit to cap the number of bills processed.

Usage:
    PYTHONPATH=. python3 scripts/cleanup_limbo_bills.py               # dry-run
    PYTHONPATH=. python3 scripts/cleanup_limbo_bills.py --apply        # write
    PYTHONPATH=. python3 scripts/cleanup_limbo_bills.py --limit 50     # cap
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from typing import Any, Dict, List

# ---------------------------------------------------------------------------
# Bootstrap — project imports
# ---------------------------------------------------------------------------

from src.load_env import load_env

load_env()

import psycopg2
import psycopg2.extras

from src.database.connection import get_connection_string
from src.utils.validation import is_bill_ready_for_posting

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("cleanup_limbo_bills")

# ---------------------------------------------------------------------------
# Safety guard
# ---------------------------------------------------------------------------

PROD_DATABASE_URL = os.environ.get("PROD_DATABASE_URL", "")


def abort_if_production(db_url: str) -> None:
    """Hard-abort when the active DATABASE_URL matches the production URL."""
    raw = os.environ.get("DATABASE_URL", "")
    if PROD_DATABASE_URL and (db_url == PROD_DATABASE_URL or raw == PROD_DATABASE_URL):
        logger.critical(
            "🛑 DATABASE_URL matches PROD_DATABASE_URL — refusing to run against production."
        )
        sys.exit(1)


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------


def fetch_limbo_bills(conn, limit: int = 500) -> List[Dict[str, Any]]:
    """Fetch all unpublished, non-problematic bills from the DB.

    Args:
        limit: Max rows to return.  0 or negative means no limit.
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        query = """
            SELECT *
            FROM bills
            WHERE published = FALSE
              AND (problematic IS NULL OR problematic = FALSE)
            ORDER BY date_introduced DESC NULLS LAST
        """
        if limit > 0:
            query += " LIMIT %s"
            cur.execute(query, (limit,))
        else:
            cur.execute(query)
        return [dict(row) for row in cur.fetchall()]


def classify_bills(bills: List[Dict[str, Any]]) -> tuple:
    """Split bills into (ready, not_ready) using is_bill_ready_for_posting().

    Returns:
        (ready_list, not_ready_list) where not_ready_list items are
        (bill_dict, reason_string) tuples.
    """
    ready: List[Dict[str, Any]] = []
    not_ready: List[tuple] = []

    for bill in bills:
        ok, reason = is_bill_ready_for_posting(bill)
        if ok:
            ready.append(bill)
        else:
            not_ready.append((bill, reason))

    return ready, not_ready


def mark_as_problematic(conn, bill_id: str, reason: str) -> bool:
    """Mark a single bill as problematic with the given reason."""
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE bills
                SET problematic = TRUE,
                    problematic_reason = %s,
                    updated_at = NOW()
                WHERE bill_id = %s
                """,
                (reason, bill_id),
            )
        return True
    except Exception as e:
        logger.error(f"Failed to mark {bill_id} as problematic: {e}")
        return False


def print_report(
    total: int,
    ready: List[Dict[str, Any]],
    not_ready: List[tuple],
    apply_mode: bool,
) -> None:
    """Print a detailed summary of the analysis."""
    print()
    print("=" * 72)
    print(f"  LIMBO BILLS CLEANUP {'(APPLY MODE)' if apply_mode else '(DRY-RUN)'}")
    print("=" * 72)
    print(f"  Total unpublished, non-problematic bills scanned: {total}")
    print(f"  ✅ Actually post-ready:                           {len(ready)}")
    print(f"  ❌ NOT post-ready (limbo):                        {len(not_ready)}")
    print("=" * 72)
    print()

    if ready:
        print("── Post-Ready Bills (no action needed) ──")
        for b in ready[:10]:
            print(f"  ✅ {b.get('bill_id', '???'):20s} {(b.get('title') or '')[:60]}")
        if len(ready) > 10:
            print(f"  ... and {len(ready) - 10} more")
        print()

    if not_ready:
        # Group by failure reason for a cleaner report
        reason_counts: Dict[str, int] = {}
        for _, reason in not_ready:
            reason_counts[reason] = reason_counts.get(reason, 0) + 1

        print("── Failure Reason Breakdown ──")
        for reason, count in sorted(reason_counts.items(), key=lambda x: -x[1]):
            print(f"  {count:4d}  {reason}")
        print()

        print("── Limbo Bills Detail (first 30) ──")
        for bill, reason in not_ready[:30]:
            bid = bill.get("bill_id", "???")
            title = (bill.get("title") or "")[:50]
            print(f"  ❌ {bid:20s} | {title:50s} | {reason}")
        if len(not_ready) > 30:
            print(f"  ... and {len(not_ready) - 30} more")
        print()

    if not apply_mode:
        print("  ℹ️  DRY-RUN: No changes written to database.")
        print("  ℹ️  Re-run with --apply to mark limbo bills as problematic.")
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Identify and clean up limbo bills that are not post-ready."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        default=False,
        help="Actually mark limbo bills as problematic (default: dry-run only).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=500,
        help="Max bills to scan (default: 500).",
    )
    args = parser.parse_args()

    db_url = get_connection_string()
    if not db_url:
        logger.error("DATABASE_URL is not set. Aborting.")
        sys.exit(1)

    abort_if_production(db_url)

    logger.info("Connecting to database...")
    # Railway requires sslmode=require; append if not already in the URL
    connect_url = db_url
    if "sslmode" not in connect_url:
        sep = "&" if "?" in connect_url else "?"
        connect_url += f"{sep}sslmode=require"
    conn = psycopg2.connect(connect_url)
    conn.autocommit = False  # explicit transaction control

    try:
        # If dry-run, use autocommit + read-only for safety
        if not args.apply:
            conn.autocommit = True
            conn.set_session(readonly=True)
            logger.info("Session set to READ-ONLY (dry-run mode).")

        logger.info(f"Fetching up to {args.limit} unpublished, non-problematic bills...")
        bills = fetch_limbo_bills(conn, limit=args.limit)
        logger.info(f"Found {len(bills)} bills to evaluate.")

        if not bills:
            print("\n  No unpublished, non-problematic bills found. Nothing to do.\n")
            return

        ready, not_ready = classify_bills(bills)
        print_report(len(bills), ready, not_ready, args.apply)

        if args.apply and not_ready:
            marked = 0
            failed = 0
            for bill, reason in not_ready:
                bid = bill.get("bill_id", "???")
                cleanup_reason = f"Limbo cleanup: {reason}"
                if mark_as_problematic(conn, bid, cleanup_reason):
                    marked += 1
                    logger.info(f"  ✓ Marked {bid} as problematic")
                else:
                    failed += 1
                    logger.warning(f"  ✗ Failed to mark {bid}")

            conn.commit()
            print(f"\n  📝 APPLY complete: {marked} bills marked problematic, {failed} failures.\n")
        elif args.apply and not not_ready:
            print("\n  All bills are post-ready. Nothing to mark.\n")

    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        conn.rollback()
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
