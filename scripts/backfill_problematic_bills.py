#!/usr/bin/env python3
"""
Comprehensive backfill for ALL problematic bills.

Iterates every bill with ``problematic = TRUE`` (or ``normalized_status IS NULL``),
identifies what data is missing, fetches it from the Congress.gov API, and
optionally regenerates summaries/arguments via the AI pipeline.

What it fixes per bill (as needed):
  - status / normalized_status  -- derived from API actions -> tracker
  - full_text                   -- fetched from Congress.gov text endpoint
  - sponsor_name/party/state    -- from bill detail endpoint
  - congress_session            -- from bill detail endpoint
  - date_introduced             -- from bill detail endpoint + action fallbacks
  - title                       -- from bill detail endpoint
  - summary_overview/detailed/tweet + teen_impact_score -- regenerated via AI
  - argument_support/oppose     -- regenerated via AI
  - hidden flag                 -- cleared if bill passes full validation

After each bill is patched, ``is_bill_ready_for_posting()`` is re-evaluated.
If the bill passes, it is unmarked as problematic (and unhidden).

Safety:
  Dry-run by default.  Pass ``--apply`` to actually write.
  Pass ``--target prod`` to run against DATABASE_URL (production).
  Without ``--target prod``, runs against STAGING_DATABASE_URL.

Usage:
    PYTHONPATH=. python3 scripts/backfill_problematic_bills.py                        # dry-run staging
    PYTHONPATH=. python3 scripts/backfill_problematic_bills.py --target prod           # dry-run prod
    PYTHONPATH=. python3 scripts/backfill_problematic_bills.py --target prod --apply   # write to prod
    PYTHONPATH=. python3 scripts/backfill_problematic_bills.py --limit 10 --apply      # cap at 10
    PYTHONPATH=. python3 scripts/backfill_problematic_bills.py --skip-summaries        # skip AI calls
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.load_env import load_env

load_env()

import psycopg2
import psycopg2.extras
import requests

from src.orchestrator import derive_status_from_tracker, extract_teen_impact_score
from src.fetchers.congress_fetcher import (
    derive_tracker_from_actions,
    fetch_bill_text_from_api,
)
from src.utils.validation import is_bill_ready_for_posting

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("backfill_problematic")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CONGRESS_API_KEY = os.environ.get("CONGRESS_API_KEY", "")
CONGRESS_API_BASE = "https://api.congress.gov/v3"
MIN_FULL_TEXT_LENGTH = 100

BILL_TYPE_MAP = {
    "hr": "hr", "s": "s",
    "hjres": "hjres", "sjres": "sjres",
    "hconres": "hconres", "sconres": "sconres",
    "hres": "hres", "sres": "sres",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def parse_bill_id(bill_id: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    m = re.match(r"^([a-z]+)(\d+)-(\d+)$", bill_id.lower())
    if not m:
        return None, None, None
    return m.group(1), m.group(2), m.group(3)


def api_get(url: str, params: Optional[dict] = None, timeout: int = 30) -> Optional[dict]:
    """GET with error handling + rate-limit politeness."""
    try:
        params = params or {}
        params.setdefault("api_key", CONGRESS_API_KEY)
        params.setdefault("format", "json")
        resp = requests.get(url, params=params, timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.warning(f"  API error: {e}")
        return None


def fetch_bill_detail(bill_type: str, bill_number: str, congress: str) -> Optional[dict]:
    api_type = BILL_TYPE_MAP.get(bill_type, bill_type)
    url = f"{CONGRESS_API_BASE}/bill/{congress}/{api_type}/{bill_number}"
    data = api_get(url)
    return data.get("bill") if data else None


def fetch_bill_actions(bill_type: str, bill_number: str, congress: str) -> List[dict]:
    api_type = BILL_TYPE_MAP.get(bill_type, bill_type)
    url = f"{CONGRESS_API_BASE}/bill/{congress}/{api_type}/{bill_number}/actions"
    data = api_get(url, params={"limit": "250"})
    return data.get("actions", []) if data else []


def derive_introduced_date(detail: dict, actions: List[dict]) -> Optional[str]:
    """Extract introduced date with fallbacks."""
    d = detail.get("introducedDate")
    if d:
        return d
    la = detail.get("latestAction", {})
    if "introduced" in (la.get("text") or "").lower():
        d = la.get("actionDate")
        if d:
            return d
    for a in actions:
        if "introduced" in (a.get("text") or "").lower():
            d = a.get("actionDate")
            if d:
                return d
    return None


# ---------------------------------------------------------------------------
# Fetch targets
# ---------------------------------------------------------------------------


def fetch_target_bills(conn, limit: int = 0) -> List[Dict[str, Any]]:
    """
    Fetch bills that need backfilling.

    Safety: only returns bills with ``problematic = TRUE``
    **or** whose current status/normalized_status indicates they are
    broken ('problematic', 'unknown', NULL, empty).  Normal bills
    that are functioning correctly are never touched.
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        sql = """
            SELECT *
            FROM bills
            WHERE problematic = TRUE
               OR LOWER(TRIM(COALESCE(status, ''))) IN ('problematic', 'unknown', '')
               OR LOWER(TRIM(COALESCE(normalized_status, ''))) IN ('unknown', '')
               OR normalized_status IS NULL
            ORDER BY
                problematic DESC,
                date_processed DESC NULLS LAST
        """
        if limit > 0:
            sql += " LIMIT %s"
            cur.execute(sql, (limit,))
        else:
            cur.execute(sql)
        return [dict(r) for r in cur.fetchall()]


def fetch_specific_bills(conn, bill_ids: List[str]) -> List[Dict[str, Any]]:
    """
    Fetch specific bills by their IDs, regardless of their current state.
    Used with --bill-ids for targeted backfilling.
    """
    if not bill_ids:
        return []
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        placeholders = ", ".join(["%s"] * len(bill_ids))
        cur.execute(
            f"SELECT * FROM bills WHERE LOWER(bill_id) IN ({placeholders}) ORDER BY date_processed DESC NULLS LAST",
            bill_ids,
        )
        return [dict(r) for r in cur.fetchall()]


# ---------------------------------------------------------------------------
# Per-bill repair
# ---------------------------------------------------------------------------


def diagnose(bill: dict) -> List[str]:
    """Return a list of issues for this bill."""
    issues = []
    if not (bill.get("title") or "").strip():
        issues.append("missing_title")
    if not (bill.get("status") or "").strip():
        issues.append("missing_status")
    if not (bill.get("normalized_status") or "").strip():
        issues.append("missing_normalized_status")
    ft = (bill.get("full_text") or "").strip()
    if not ft or len(ft) < MIN_FULL_TEXT_LENGTH:
        issues.append("missing_full_text")
    if not (bill.get("sponsor_name") or "").strip():
        issues.append("missing_sponsor")
    if not (bill.get("congress_session") or "").strip():
        issues.append("missing_congress_session")
    if not (bill.get("date_introduced") or "").strip():
        issues.append("missing_date_introduced")
    if not (bill.get("summary_overview") or "").strip():
        issues.append("missing_summary_overview")
    if not (bill.get("summary_detailed") or "").strip():
        issues.append("missing_summary_detailed")
    st = (bill.get("summary_tweet") or "").strip()
    if not st or len(st) < 20:
        issues.append("missing_summary_tweet")
    if bill.get("teen_impact_score") is None:
        issues.append("missing_teen_impact_score")
    if not (bill.get("argument_support") or "").strip():
        issues.append("missing_argument_support")
    if not (bill.get("argument_oppose") or "").strip():
        issues.append("missing_argument_oppose")
    return issues


def repair_bill(
    bill: dict,
    skip_summaries: bool = False,
) -> Tuple[Dict[str, Any], List[str]]:
    """
    Attempt to fill in missing fields for *bill*.

    Returns (updates_dict, fixes_applied).
    ``updates_dict`` maps column -> new value to SET in the database.
    """
    bill_id = bill.get("bill_id", "")
    bill_type, bill_number, congress = parse_bill_id(bill_id)
    if not bill_type:
        return {}, []

    updates: Dict[str, Any] = {}
    fixes: List[str] = []
    issues = diagnose(bill)

    if not issues:
        return {}, []

    needs_api = any(
        i in issues
        for i in [
            "missing_title", "missing_status", "missing_normalized_status",
            "missing_sponsor", "missing_congress_session",
            "missing_date_introduced", "missing_full_text",
        ]
    )

    detail: Optional[dict] = None
    actions: List[dict] = []
    tracker: Optional[list] = None

    if needs_api:
        detail = fetch_bill_detail(bill_type, bill_number, congress)
        time.sleep(0.3)
        actions = fetch_bill_actions(bill_type, bill_number, congress)
        time.sleep(0.3)

        if actions:
            tracker = derive_tracker_from_actions(actions)

    # -- Title --
    if "missing_title" in issues and detail:
        title = (detail.get("title") or "").strip()
        if title:
            updates["title"] = title
            fixes.append("title")

    # -- Status / normalized_status --
    if "missing_status" in issues or "missing_normalized_status" in issues:
        if tracker:
            status_text, normalized = derive_status_from_tracker(tracker)
        else:
            status_text, normalized = "Introduced", "introduced"
        if "missing_status" in issues:
            updates["status"] = status_text
        if "missing_normalized_status" in issues:
            updates["normalized_status"] = normalized
        fixes.append("status")

    # -- Sponsor --
    if "missing_sponsor" in issues and detail:
        sponsors = detail.get("sponsors") or []
        if sponsors:
            primary = sponsors[0]
            updates["sponsor_name"] = primary.get("fullName", "")
            updates["sponsor_party"] = primary.get("party", "")
            updates["sponsor_state"] = primary.get("state", "")
            fixes.append("sponsor")

    # -- Congress session --
    if "missing_congress_session" in issues:
        cs = congress or ""
        if not cs and detail:
            cs = str(detail.get("congress", ""))
        if cs:
            updates["congress_session"] = cs
            fixes.append("congress_session")

    # -- Date introduced --
    if "missing_date_introduced" in issues:
        di = None
        if detail:
            di = derive_introduced_date(detail, actions)
        if di:
            updates["date_introduced"] = di
            fixes.append("date_introduced")

    # -- Full text --
    if "missing_full_text" in issues:
        try:
            ft, fmt = fetch_bill_text_from_api(congress, bill_type, bill_number, CONGRESS_API_KEY, timeout=30)
            time.sleep(0.3)
        except Exception:
            ft, fmt = "", None
        if ft and len(ft.strip()) >= MIN_FULL_TEXT_LENGTH:
            updates["full_text"] = ft
            fixes.append("full_text")

    # -- Summaries + teen_impact_score + arguments (requires full_text) --
    needs_summaries = any(
        i in issues
        for i in [
            "missing_summary_overview", "missing_summary_detailed",
            "missing_summary_tweet", "missing_teen_impact_score",
        ]
    )
    needs_arguments = any(
        i in issues
        for i in ["missing_argument_support", "missing_argument_oppose"]
    )

    # Compute effective full text (DB value or freshly fetched)
    effective_ft = updates.get("full_text") or (bill.get("full_text") or "")
    effective_title = updates.get("title") or (bill.get("title") or "")

    if needs_summaries and not skip_summaries and len(effective_ft.strip()) >= MIN_FULL_TEXT_LENGTH:
        try:
            from src.processors.summarizer import summarize_bill_enhanced

            fake_bill = dict(bill)
            fake_bill["full_text"] = effective_ft
            fake_bill["title"] = effective_title
            # Ensure status fields are set for summarizer
            if "status" in updates:
                fake_bill["status"] = updates["status"]
            if "normalized_status" in updates:
                fake_bill["normalized_status"] = updates["normalized_status"]

            summary = summarize_bill_enhanced(fake_bill)

            overview = (summary.get("overview") or "").strip()
            detailed = (summary.get("detailed") or "").strip()
            tweet = (summary.get("tweet") or "").strip()

            # Validate that summaries don't contain error phrases
            combined = (overview + detailed + tweet).lower()
            error_phrases = ["full bill text needed", "no summary available", "error generating summary"]
            has_errors = any(p in combined for p in error_phrases)

            if overview and detailed and len(tweet) >= 20 and not has_errors:
                updates["summary_overview"] = overview
                updates["summary_detailed"] = detailed
                updates["summary_tweet"] = tweet
                updates["subject_tags"] = summary.get("subject_tags", "")
                fixes.append("summaries")

                score = extract_teen_impact_score(detailed)
                if score is not None:
                    updates["teen_impact_score"] = score
                    fixes.append("teen_impact_score")
            else:
                logger.warning(f"  Summaries generated but failed quality check for {bill_id}")
        except Exception as e:
            logger.warning(f"  Summary generation failed for {bill_id}: {e}")

    if needs_arguments and not skip_summaries:
        effective_overview = updates.get("summary_overview") or (bill.get("summary_overview") or "")
        effective_detailed = updates.get("summary_detailed") or (bill.get("summary_detailed") or "")
        if effective_overview and effective_detailed:
            try:
                from src.processors.argument_generator import generate_bill_arguments

                args = generate_bill_arguments(
                    bill_title=effective_title,
                    summary_overview=effective_overview,
                    summary_detailed=effective_detailed,
                )
                support = (args.get("support") or "").strip()
                oppose = (args.get("oppose") or "").strip()
                if support and oppose:
                    updates["argument_support"] = support
                    updates["argument_oppose"] = oppose
                    fixes.append("arguments")
            except Exception as e:
                logger.warning(f"  Argument generation failed for {bill_id}: {e}")

    return updates, fixes


# ---------------------------------------------------------------------------
# DB write helpers
# ---------------------------------------------------------------------------


def apply_updates(conn, bill_id: str, updates: Dict[str, Any]) -> bool:
    if not updates:
        return True
    set_clauses = []
    values = []
    for col, val in updates.items():
        set_clauses.append(f"{col} = %s")
        values.append(val)
    values.append(bill_id)
    sql = f"UPDATE bills SET {', '.join(set_clauses)} WHERE bill_id = %s"
    try:
        with conn.cursor() as cur:
            cur.execute(sql, values)
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        logger.error(f"  DB update failed for {bill_id}: {e}")
        return False


def unmark_problematic(conn, bill_id: str) -> bool:
    """
    Clear the problematic flag but **keep hidden = TRUE**.

    Bills are intentionally left hidden so a human can verify them
    in the admin panel before making them visible on the site.
    """
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
    parser = argparse.ArgumentParser(description="Comprehensive backfill for problematic bills.")
    parser.add_argument("--apply", action="store_true", help="Write changes to DB (default: dry-run).")
    parser.add_argument("--target", choices=["staging", "prod"], default="staging",
                        help="Which database to target (default: staging).")
    parser.add_argument("--limit", type=int, default=0, help="Max bills (0 = all).")
    parser.add_argument("--bill-ids", type=str, default="",
                        help="Comma-separated bill IDs to target (e.g. 'sres573-119,s3578-119'). "
                             "Overrides --limit. Targets these specific bills regardless of "
                             "their current problematic/status state.")
    parser.add_argument("--skip-summaries", action="store_true",
                        help="Skip AI summary/argument generation (faster, metadata only).")
    args = parser.parse_args()

    if not CONGRESS_API_KEY:
        logger.error("CONGRESS_API_KEY not set. Aborting.")
        sys.exit(1)

    if args.target == "prod":
        db_url = os.environ.get("DATABASE_URL", "")
        if not db_url:
            logger.error("DATABASE_URL not set. Aborting.")
            sys.exit(1)
        logger.info("TARGET: PRODUCTION database.")
    else:
        db_url = os.environ.get("STAGING_DATABASE_URL", "")
        if not db_url:
            logger.error("STAGING_DATABASE_URL not set. Aborting.")
            sys.exit(1)
        logger.info("TARGET: STAGING database.")

    connect_url = db_url
    if "sslmode" not in connect_url:
        sep = "&" if "?" in connect_url else "?"
        connect_url += f"{sep}sslmode=require"

    conn = psycopg2.connect(connect_url)
    conn.autocommit = False

    mode_label = "APPLY" if args.apply else "DRY-RUN"

    try:
        if args.bill_ids:
            # Targeted mode: fetch only the specified bills
            target_ids = [bid.strip().lower() for bid in args.bill_ids.split(",") if bid.strip()]
            bills = fetch_specific_bills(conn, target_ids)
            logger.info(f"Targeted {len(target_ids)} bill IDs, found {len(bills)} in DB ({mode_label}).")
        else:
            bills = fetch_target_bills(conn, limit=args.limit)
        logger.info(f"Found {len(bills)} bills to process ({mode_label}).")
        if not bills:
            print("\n  No bills need backfilling.\n")
            return

        stats = {
            "processed": 0,
            "updated": 0,
            "now_ready": 0,
            "still_problematic": 0,
            "skipped_parse": 0,
            "no_issues": 0,
        }
        fix_counts: Dict[str, int] = {}

        for i, bill in enumerate(bills):
            bill_id = bill.get("bill_id", "???")
            is_prob = bill.get("problematic", False)
            stats["processed"] += 1

            issues = diagnose(bill)
            if not issues:
                logger.info(f"  [{i+1}/{len(bills)}] {bill_id}: no issues detected")
                stats["no_issues"] += 1

                # Even if no issues, check if we should unmark
                if is_prob and args.apply:
                    ready, reason = is_bill_ready_for_posting(bill)
                    if ready:
                        unmark_problematic(conn, bill_id)
                        stats["now_ready"] += 1
                        logger.info(f"    Unmarked problematic (kept hidden for manual review)")
                    else:
                        stats["still_problematic"] += 1
                        logger.info(f"    Still not ready: {reason}")
                continue

            logger.info(f"  [{i+1}/{len(bills)}] {bill_id}: issues={issues}")

            updates, fixes = repair_bill(bill, skip_summaries=args.skip_summaries)

            if not fixes:
                logger.info(f"    Could not fix any issues for {bill_id}")
                stats["still_problematic"] += 1
                continue

            for f in fixes:
                fix_counts[f] = fix_counts.get(f, 0) + 1

            logger.info(f"    Fixes: {fixes}")

            if args.apply:
                if apply_updates(conn, bill_id, updates):
                    stats["updated"] += 1

                    # Re-evaluate readiness with patched data
                    patched = dict(bill)
                    patched.update(updates)
                    ready, reason = is_bill_ready_for_posting(patched)

                    if ready:
                        unmark_problematic(conn, bill_id)
                        stats["now_ready"] += 1
                        logger.info(f"    Now post-ready -- unmarked (kept hidden for manual review)")
                    else:
                        stats["still_problematic"] += 1
                        logger.info(f"    Partially fixed but still not ready: {reason}")
                else:
                    stats["still_problematic"] += 1
            else:
                stats["updated"] += 1
                patched = dict(bill)
                patched.update(updates)
                ready, reason = is_bill_ready_for_posting(patched)
                if ready:
                    stats["now_ready"] += 1
                else:
                    stats["still_problematic"] += 1
                    logger.info(f"    Would still not be ready: {reason}")

            # Rate-limit API calls
            time.sleep(0.3)

        # -- Summary --
        print()
        print("=" * 72)
        print(f"  BACKFILL REPORT ({mode_label} -- {args.target.upper()})")
        print("=" * 72)
        print(f"  Total bills scanned:            {stats['processed']}")
        print(f"  Already OK (no issues):         {stats['no_issues']}")
        print(f"  Bills with fixes applied:       {stats['updated']}")
        print(f"  Now post-ready (unmarked):      {stats['now_ready']}")
        print(f"  Still problematic:              {stats['still_problematic']}")
        print()
        if fix_counts:
            print("  Fixes by category:")
            for cat, count in sorted(fix_counts.items(), key=lambda x: -x[1]):
                print(f"    {cat:30s} {count}")
        print("=" * 72)
        print()

    except KeyboardInterrupt:
        logger.info("\nInterrupted by user.")
        conn.rollback()
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        conn.rollback()
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
