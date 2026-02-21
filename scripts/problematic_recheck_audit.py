#!/usr/bin/env python3
"""
Staging-only audit script: iterate problematic bills, re-enrich from Congress.gov,
validate completeness, and report which could be updated vs which remain problematic.

  ▸ NO database writes
  ▸ NO publishing
  ▸ Aborts if DATABASE_URL == PROD_DATABASE_URL

Usage:
    PYTHONPATH=. python3 scripts/problematic_recheck_audit.py --all
    PYTHONPATH=. python3 scripts/problematic_recheck_audit.py --eligible-only
    PYTHONPATH=. python3 scripts/problematic_recheck_audit.py --all --limit 10
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

from src.load_env import load_env
from src.database.connection import get_connection_string

load_env()

import psycopg2
import psycopg2.extras

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("problematic_recheck_audit")

# ---------------------------------------------------------------------------
# Safety guards
# ---------------------------------------------------------------------------

PROD_DATABASE_URL = os.environ.get("PROD_DATABASE_URL", "")


def abort_if_production(db_url: str) -> None:
    """Hard-abort when the active DATABASE_URL matches the production URL."""
    if PROD_DATABASE_URL and db_url == PROD_DATABASE_URL:
        logger.critical(
            "🛑 DATABASE_URL matches PROD_DATABASE_URL — refusing to run against production."
        )
        sys.exit(1)
    raw = os.environ.get("DATABASE_URL", "")
    if PROD_DATABASE_URL and raw == PROD_DATABASE_URL:
        logger.critical(
            "🛑 Raw DATABASE_URL matches PROD_DATABASE_URL — refusing to run against production."
        )
        sys.exit(1)


# ---------------------------------------------------------------------------
# Column introspection helpers
# ---------------------------------------------------------------------------


def _get_bills_columns(conn) -> List[str]:
    """Return all column names for the bills table."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'bills'
            ORDER BY ordinal_position
            """
        )
        return [r[0] for r in cur.fetchall()]


def _has_column(columns: List[str], name: str) -> bool:
    return name in columns


# ---------------------------------------------------------------------------
# Fetch problematic bills (read-only)
# ---------------------------------------------------------------------------

ELIGIBLE_DAYS = 15


def fetch_problematic_bills(
    conn,
    columns: List[str],
    *,
    eligible_only: bool = False,
    limit: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    Fetch problematic bills from the database.

    When *eligible_only* is True the query narrows to bills where:
      • problematic_marked_at is >= 15 days ago  (column may not exist)
      • recheck_attempted is FALSE / NULL          (column may not exist)
    Missing columns are silently ignored.
    """
    conditions = ["problematic = TRUE"]

    has_marked_at = _has_column(columns, "problematic_marked_at")
    has_recheck = _has_column(columns, "recheck_attempted")

    if eligible_only:
        cutoff = datetime.now(timezone.utc) - timedelta(days=ELIGIBLE_DAYS)
        if has_marked_at:
            conditions.append(
                f"problematic_marked_at <= '{cutoff.isoformat()}'"
            )
        else:
            logger.warning(
                "⚠️  Column 'problematic_marked_at' not found — skipping age filter"
            )
        if has_recheck:
            conditions.append(
                "(recheck_attempted IS NULL OR recheck_attempted = FALSE)"
            )
        else:
            logger.warning(
                "⚠️  Column 'recheck_attempted' not found — skipping recheck filter"
            )

    where = " AND ".join(conditions)

    order_parts: List[str] = []
    if has_marked_at:
        order_parts.append("problematic_marked_at DESC NULLS LAST")
    order_parts.append("updated_at DESC NULLS LAST")
    order_by = ", ".join(order_parts)

    sql = f"SELECT * FROM bills WHERE {where} ORDER BY {order_by}"
    if limit:
        sql += f" LIMIT {int(limit)}"

    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql)
        return [dict(row) for row in cur.fetchall()]


# ---------------------------------------------------------------------------
# Enrichment + validation (no DB writes)
# ---------------------------------------------------------------------------

def enrich_and_validate(bill: Dict[str, Any]) -> Tuple[bool, Dict[str, Any], List[str]]:
    """
    Re-enrich a single problematic bill from Congress.gov and validate.

    Returns:
        (is_now_complete, enriched_merged_dict, remaining_issues)

    The enriched dict merges fresh API data on top of the existing DB row
    so that validate_bill_data sees the best possible picture.
    """
    from src.fetchers.feed_parser import enrich_single_bill
    from src.utils.validation import validate_bill_data

    bill_id = bill.get("bill_id", "unknown")
    logger.info(f"🔍 Enriching {bill_id} …")

    enriched: Optional[Dict[str, Any]] = None
    try:
        enriched = enrich_single_bill(bill_id)
    except Exception as exc:
        logger.warning(f"❌ enrich_single_bill failed for {bill_id}: {exc}")

    # Build a merged view: start with existing DB row, overlay enriched fields
    merged = dict(bill)
    if enriched:
        for key, value in enriched.items():
            # Only overwrite if the enriched value is non-empty
            if value is None:
                continue
            if isinstance(value, str) and not value.strip():
                continue
            merged[key] = value

    is_valid, reasons = validate_bill_data(merged)
    return is_valid, merged, reasons


# ---------------------------------------------------------------------------
# JSON helper
# ---------------------------------------------------------------------------

def _json_safe(obj: Any) -> Any:
    """Make datetimes and other non-serialisable types safe for json.dumps."""
    if isinstance(obj, (datetime,)):
        return obj.isoformat()
    if isinstance(obj, bytes):
        return obj.decode("utf-8", errors="replace")
    return str(obj)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audit problematic bills: re-enrich from Congress.gov and report completeness (read-only).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  PYTHONPATH=. python3 scripts/problematic_recheck_audit.py --all
  PYTHONPATH=. python3 scripts/problematic_recheck_audit.py --eligible-only
  PYTHONPATH=. python3 scripts/problematic_recheck_audit.py --all --limit 5
        """,
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--all",
        action="store_true",
        help="Check ALL problematic bills",
    )
    group.add_argument(
        "--eligible-only",
        action="store_true",
        help=(
            f"Only check bills marked problematic >= {ELIGIBLE_DAYS} days ago "
            "and not yet recheck-attempted"
        ),
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max number of bills to process (default: no limit)",
    )

    args = parser.parse_args()

    # -- Connection ----------------------------------------------------------
    db_url = get_connection_string()
    if not db_url:
        logger.critical("DATABASE_URL is not set. Exiting.")
        sys.exit(1)

    abort_if_production(db_url)

    conn = psycopg2.connect(db_url)
    # Enforce read-only at the session level — belt-and-suspenders safety
    conn.set_session(readonly=True, autocommit=True)
    logger.info("✅ Connected to staging database (read-only)")

    # -- Introspect columns --------------------------------------------------
    columns = _get_bills_columns(conn)
    if not columns:
        logger.critical("Could not read bills table columns. Exiting.")
        conn.close()
        sys.exit(1)
    logger.info(f"📋 Bills table has {len(columns)} columns")

    # -- Fetch bills ---------------------------------------------------------
    bills = fetch_problematic_bills(
        conn,
        columns,
        eligible_only=args.eligible_only,
        limit=args.limit,
    )
    conn.close()

    if not bills:
        print("\n✅ No problematic bills matched the filter.")
        sys.exit(0)

    mode_label = "eligible-only" if args.eligible_only else "all"
    print(f"\n{'='*72}")
    print(f"  Problematic Recheck Audit  —  mode={mode_label}  bills={len(bills)}")
    print(f"{'='*72}\n")

    # -- Process each bill ---------------------------------------------------
    recovered: List[Dict[str, Any]] = []
    still_problematic: List[Dict[str, Any]] = []
    errors: List[Dict[str, str]] = []

    for idx, bill in enumerate(bills, 1):
        bill_id = bill.get("bill_id", "???")
        print(f"[{idx}/{len(bills)}] {bill_id}")

        try:
            is_complete, merged, reasons = enrich_and_validate(bill)
        except Exception as exc:
            logger.error(f"  💥 Unexpected error for {bill_id}: {exc}")
            errors.append({"bill_id": bill_id, "error": str(exc)})
            continue

        if is_complete:
            print(f"  ✅ RECOVERED — all validation passed")
            print(f"  📦 Enriched data:")
            print(json.dumps(merged, indent=2, default=_json_safe))
            recovered.append({"bill_id": bill_id, "data": merged})
        else:
            print(f"  ❌ STILL PROBLEMATIC — {len(reasons)} issue(s):")
            for r in reasons:
                print(f"     • {r}")
            still_problematic.append({
                "bill_id": bill_id,
                "missing_reasons": reasons,
            })

        # Polite delay between API calls
        if idx < len(bills):
            time.sleep(1.0)

    # -- Summary -------------------------------------------------------------
    print(f"\n{'='*72}")
    print("  AUDIT SUMMARY")
    print(f"{'='*72}")
    print(f"  Total processed : {len(bills)}")
    print(f"  ✅ Recovered     : {len(recovered)}")
    print(f"  ❌ Still problem. : {len(still_problematic)}")
    print(f"  💥 Errors        : {len(errors)}")
    print(f"{'='*72}\n")

    if recovered:
        print("RECOVERED BILLS (could be updated):")
        for item in recovered:
            print(f"  • {item['bill_id']}")

    if still_problematic:
        print("\nSTILL PROBLEMATIC BILLS:")
        for item in still_problematic:
            print(f"  • {item['bill_id']}  →  {', '.join(item['missing_reasons'])}")

    if errors:
        print("\nERROR BILLS:")
        for item in errors:
            print(f"  • {item['bill_id']}  →  {item['error']}")

    print(f"\n📝 This was a READ-ONLY audit. No database writes were performed.")


if __name__ == "__main__":
    main()
