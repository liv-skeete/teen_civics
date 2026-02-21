#!/usr/bin/env python3
"""
Periodic problematic-bill recheck: enrich → re-validate → report/update.

Pulls ALL problematic bills from the database, attempts enrichment via the
Congress.gov API for each one, then re-evaluates completeness.  Outputs a
structured summary of still-problematic vs recovered bills.

Safety:
  • Aborts immediately if DATABASE_URL == PROD_DATABASE_URL.
  • Default mode is DRY-RUN (read-only).  The session is set to readonly
    unless --allow-writes is explicitly passed.
  • The --allow-writes flag must be provided to persist any changes.

Usage (dry-run — no DB writes):
    PYTHONPATH=. python3 scripts/problematic_recheck_periodic.py

Enable DB updates (staging only, after review):
    PYTHONPATH=. python3 scripts/problematic_recheck_periodic.py --allow-writes

Limit the number of bills processed:
    PYTHONPATH=. python3 scripts/problematic_recheck_periodic.py --limit 10

Designed to be called from GitHub Actions on a 15-day schedule.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Bootstrap — project imports
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
logger = logging.getLogger("problematic_recheck_periodic")

# ---------------------------------------------------------------------------
# Safety guards
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
# Column introspection
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
# Fetch problematic bills
# ---------------------------------------------------------------------------


def fetch_all_problematic_bills(
    conn,
    columns: List[str],
    *,
    limit: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Fetch every bill with problematic = TRUE, ordered newest first."""
    has_marked_at = _has_column(columns, "problematic_marked_at")

    order_parts: List[str] = []
    if has_marked_at:
        order_parts.append("problematic_marked_at DESC NULLS LAST")
    order_parts.append("updated_at DESC NULLS LAST")
    order_by = ", ".join(order_parts)

    sql = f"SELECT * FROM bills WHERE problematic = TRUE ORDER BY {order_by}"
    if limit:
        sql += f" LIMIT {int(limit)}"

    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql)
        return [dict(row) for row in cur.fetchall()]


# ---------------------------------------------------------------------------
# Enrichment + validation (stateless — no DB side-effects)
# ---------------------------------------------------------------------------


def enrich_and_validate(bill: Dict[str, Any]) -> Tuple[bool, Dict[str, Any], List[str]]:
    """
    Re-enrich a single problematic bill from Congress.gov and validate.

    Returns:
        (is_now_complete, enriched_merged_dict, remaining_issues)
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

    # Build a merged view: existing DB row + any enriched fields on top
    merged = dict(bill)
    if enriched:
        for key, value in enriched.items():
            if value is None:
                continue
            if isinstance(value, str) and not value.strip():
                continue
            merged[key] = value

    is_valid, reasons = validate_bill_data(merged)
    return is_valid, merged, reasons


# ---------------------------------------------------------------------------
# DB update for recovered bills (only when --allow-writes)
# ---------------------------------------------------------------------------

# Fields from enrichment that we allow to be written back to the DB row.
UPDATABLE_FIELDS = [
    "title",
    "full_text",
    "source_url",
    "date_introduced",
    "sponsor_name",
    "sponsor_party",
    "sponsor_state",
    "latest_action",
    "latest_action_date",
]


def apply_recovery_update(conn, bill_id: str, merged: Dict[str, Any]) -> bool:
    """
    Write enriched data back for a recovered bill and clear its problematic flag.

    Returns True on success.
    """
    set_parts: List[str] = []
    values: List[Any] = []

    for field in UPDATABLE_FIELDS:
        val = merged.get(field)
        if val is not None:
            set_parts.append(f"{field} = %s")
            values.append(val)

    # Clear the problematic flag + mark recheck
    set_parts.append("problematic = FALSE")
    set_parts.append("recheck_attempted = TRUE")
    set_parts.append("updated_at = %s")
    values.append(datetime.now(timezone.utc))

    values.append(bill_id)  # for WHERE

    sql = f"UPDATE bills SET {', '.join(set_parts)} WHERE bill_id = %s"

    try:
        with conn.cursor() as cur:
            cur.execute(sql, values)
        conn.commit()
        logger.info(f"  💾 DB updated for {bill_id}")
        return True
    except Exception as exc:
        conn.rollback()
        logger.error(f"  💥 DB update failed for {bill_id}: {exc}")
        return False


# ---------------------------------------------------------------------------
# JSON serialization helper
# ---------------------------------------------------------------------------


def _json_safe(obj: Any) -> Any:
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, bytes):
        return obj.decode("utf-8", errors="replace")
    return str(obj)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Periodic recheck of all problematic bills: "
            "enrich from Congress.gov, re-validate, report results."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples (dry-run by default):
  PYTHONPATH=. python3 scripts/problematic_recheck_periodic.py
  PYTHONPATH=. python3 scripts/problematic_recheck_periodic.py --limit 5

With DB writes (staging only, after review):
  PYTHONPATH=. python3 scripts/problematic_recheck_periodic.py --allow-writes
        """,
    )
    parser.add_argument(
        "--allow-writes",
        action="store_true",
        default=False,
        help="Enable DB updates for recovered bills (default: dry-run, no writes)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max number of bills to process (default: all)",
    )

    args = parser.parse_args()
    dry_run = not args.allow_writes

    # -- Connection -----------------------------------------------------------
    db_url = get_connection_string()
    if not db_url:
        logger.critical("DATABASE_URL is not set. Exiting.")
        sys.exit(1)

    abort_if_production(db_url)

    conn = psycopg2.connect(db_url)

    if dry_run:
        conn.set_session(readonly=True, autocommit=True)
        logger.info("✅ Connected (DRY-RUN — read-only session)")
    else:
        logger.info("⚠️  Connected (WRITE MODE — changes will be persisted)")

    # -- Introspect columns ---------------------------------------------------
    columns = _get_bills_columns(conn)
    if not columns:
        logger.critical("Could not read bills table columns. Exiting.")
        conn.close()
        sys.exit(1)
    logger.info(f"📋 Bills table has {len(columns)} columns")

    # -- Fetch ----------------------------------------------------------------
    bills = fetch_all_problematic_bills(conn, columns, limit=args.limit)

    if not bills:
        print("\n✅ No problematic bills found. Nothing to do.")
        conn.close()
        sys.exit(0)

    mode_label = "DRY-RUN" if dry_run else "WRITE"
    print(f"\n{'=' * 72}")
    print(f"  Problematic Bill Periodic Recheck  —  mode={mode_label}  bills={len(bills)}")
    print(f"{'=' * 72}\n")

    # -- Phase 1: Enrich all bills -------------------------------------------
    enrichment_results: List[Tuple[Dict[str, Any], bool, Dict[str, Any], List[str]]] = []

    for idx, bill in enumerate(bills, 1):
        bill_id = bill.get("bill_id", "???")
        print(f"[{idx}/{len(bills)}] Enriching {bill_id} …")

        try:
            is_complete, merged, reasons = enrich_and_validate(bill)
            enrichment_results.append((bill, is_complete, merged, reasons))
        except Exception as exc:
            logger.error(f"  💥 Unexpected error for {bill_id}: {exc}")
            enrichment_results.append((bill, False, bill, [f"Exception: {exc}"]))

        # Polite delay between API calls
        if idx < len(bills):
            time.sleep(1.0)

    # -- Phase 2: Re-evaluate & optionally update ----------------------------
    recovered: List[Dict[str, Any]] = []
    still_problematic: List[Dict[str, Any]] = []
    write_successes = 0
    write_failures = 0

    print(f"\n{'=' * 72}")
    print("  RE-EVALUATION RESULTS")
    print(f"{'=' * 72}\n")

    for bill, is_complete, merged, reasons in enrichment_results:
        bill_id = bill.get("bill_id", "???")

        if is_complete:
            print(f"  ✅ RECOVERED  {bill_id}")
            recovered.append({"bill_id": bill_id, "data": merged})

            if not dry_run:
                ok = apply_recovery_update(conn, bill_id, merged)
                if ok:
                    write_successes += 1
                else:
                    write_failures += 1
        else:
            print(f"  ❌ STILL PROBLEMATIC  {bill_id}")
            for r in reasons:
                print(f"       • {r}")
            still_problematic.append({
                "bill_id": bill_id,
                "missing_reasons": reasons,
            })

    # -- Summary (human-readable) --------------------------------------------
    print(f"\n{'=' * 72}")
    print("  PERIODIC RECHECK SUMMARY")
    print(f"{'=' * 72}")
    print(f"  Total processed    : {len(bills)}")
    print(f"  ✅ Recovered        : {len(recovered)}")
    print(f"  ❌ Still problematic : {len(still_problematic)}")
    if not dry_run:
        print(f"  💾 DB writes OK     : {write_successes}")
        print(f"  💥 DB write errors  : {write_failures}")
    else:
        print(f"  📝 Mode             : DRY-RUN (no DB writes)")
    print(f"{'=' * 72}\n")

    # -- Machine-readable JSON blocks (for CI parsing) -----------------------
    summary_payload = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "mode": "dry-run" if dry_run else "write",
        "total_processed": len(bills),
        "recovered_count": len(recovered),
        "still_problematic_count": len(still_problematic),
        "recovered": [r["bill_id"] for r in recovered],
        "still_problematic": [
            {"bill_id": s["bill_id"], "reasons": s["missing_reasons"]}
            for s in still_problematic
        ],
    }

    print("RECHECK_SUMMARY_JSON_START")
    print(json.dumps(summary_payload, indent=2, default=_json_safe))
    print("RECHECK_SUMMARY_JSON_END")

    conn.close()

    # Exit code: 0 = all good, 1 only if there was a hard error
    # (still-problematic bills are expected — not an error)
    sys.exit(0)


if __name__ == "__main__":
    main()
