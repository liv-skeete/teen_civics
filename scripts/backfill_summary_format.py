"""Regenerate summaries for unpublished bills whose stored summary is
still in the pre-2026-05 6-section format.

Why this exists: when the prompt structure changed on 2026-05-24 from
6 sections (🔎 Overview / 👥 Who does this affect? / 🔑 What This Bill
Does / 📌 Legislative Status / 👉 In short / 💡 Why should I care?) to
4 sections (⚡ The gist / ⚖️ Who wins, who loses / 🔑 What it does /
💡 Why should I care?), ~140 already-summarized but not-yet-published
bills were left in the prod backlog with the old format. The daily
cron picks one each day and posts it as-is, so without backfill the
homepage would flip back to old format ~140 more times.

Staging by default; pass --i-mean-prod for prod. Always do --dry-run
first to see the candidate list before regenerating anything.

Usage:
    python3 scripts/backfill_summary_format.py --dry-run
    python3 scripts/backfill_summary_format.py --i-mean-prod --dry-run
    python3 scripts/backfill_summary_format.py --i-mean-prod
    python3 scripts/backfill_summary_format.py --i-mean-prod --limit 5
"""

import argparse
import logging
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.load_env import load_env

load_env()

from src.database.connection import postgres_connect
from src.processors.summarizer import summarize_bill_enhanced

PROD_HOST_MARKER = "centerbeam"

OLD_FORMAT_MARKERS = ("🔎 Overview", "🔑 What This Bill Does", "👉 In short")
NEW_FORMAT_MARKER = "⚡ The gist"


def _swap_to_prod_if_requested(allow_prod: bool) -> None:
    if not allow_prod:
        return
    prod_url = os.environ.get("PROD_DATABASE_URL", "")
    if not prod_url:
        sys.exit("REFUSING TO RUN: --i-mean-prod set but PROD_DATABASE_URL not in .env.")
    os.environ["DATABASE_URL"] = prod_url


def _assert_db_target(allow_prod: bool) -> None:
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        sys.exit("REFUSING TO RUN: DATABASE_URL not set.")
    is_prod = PROD_HOST_MARKER in url
    if is_prod and not allow_prod:
        sys.exit(
            f"REFUSING TO RUN: DATABASE_URL contains '{PROD_HOST_MARKER}'. "
            "Pass --i-mean-prod to allow."
        )
    target = "PROD (centerbeam)" if is_prod else "STAGING"
    print(f"📊 Target: {target}")


def _find_old_format_bills(limit: int | None) -> list[dict]:
    sql = """
        SELECT bill_id, title, short_title, status, normalized_status,
               congress_session, date_introduced, source_url,
               sponsor_name, sponsor_party, sponsor_state,
               full_text, summary_detailed, date_processed
        FROM bills
        WHERE published = false
          AND summary_detailed IS NOT NULL
          AND (summary_detailed LIKE '%🔎 Overview%'
               OR summary_detailed LIKE '%🔑 What This Bill Does%'
               OR summary_detailed LIKE '%👉 In short%')
          AND summary_detailed NOT LIKE '%⚡ The gist%'
        ORDER BY date_processed ASC NULLS LAST
    """
    if limit:
        sql += f"\nLIMIT {int(limit)}"

    with postgres_connect() as conn:
        if conn is None:
            sys.exit("Could not get DB connection.")
        cur = conn.cursor()
        cur.execute(sql)
        rows = cur.fetchall()
        cur.close()

    cols = [
        "bill_id", "title", "short_title", "status", "normalized_status",
        "congress_session", "date_introduced", "source_url",
        "sponsor_name", "sponsor_party", "sponsor_state",
        "full_text", "summary_detailed", "date_processed",
    ]
    return [dict(zip(cols, row)) for row in rows]


def _persist(bill_id: str, summary: dict) -> None:
    with postgres_connect() as conn:
        if conn is None:
            raise RuntimeError("Could not get DB connection.")
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE bills
            SET summary_overview = %s,
                summary_detailed = %s,
                summary_tweet = %s,
                updated_at = NOW()
            WHERE bill_id = %s
            """,
            (
                summary.get("overview"),
                summary.get("detailed"),
                summary.get("tweet"),
                bill_id,
            ),
        )
        conn.commit()
        cur.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--i-mean-prod", action="store_true", dest="allow_prod",
                        help="Run against production DB. Use deliberately.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Only list candidates; do not regenerate or write.")
    parser.add_argument("--limit", type=int, default=None,
                        help="Process at most N bills (default: all).")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    _swap_to_prod_if_requested(args.allow_prod)
    _assert_db_target(args.allow_prod)

    bills = _find_old_format_bills(args.limit)
    print(f"📋 Found {len(bills)} old-format unpublished bills.")

    if args.dry_run:
        for b in bills[:20]:
            ft_len = len((b.get("full_text") or "").strip())
            print(f"   {b['bill_id']:<14}  date_processed={b['date_processed']}  ft={ft_len}")
        if len(bills) > 20:
            print(f"   ... and {len(bills) - 20} more")
        print("(dry-run: nothing written)")
        return

    if not bills:
        print("Nothing to do.")
        return

    print(f"🚀 Regenerating {len(bills)} bills...")
    start = time.time()
    successes = 0
    failures = []
    skipped_no_text = []

    for i, bill in enumerate(bills, 1):
        bid = bill["bill_id"]
        ft_len = len((bill.get("full_text") or "").strip())
        if ft_len < 100:
            print(f"[{i}/{len(bills)}] {bid}: ⏭️  skip (full_text too short: {ft_len} chars)")
            skipped_no_text.append(bid)
            continue

        t0 = time.time()
        try:
            new_summary = summarize_bill_enhanced(bill)
            detailed = new_summary.get("detailed", "") if new_summary else ""
            if not detailed:
                raise RuntimeError("empty detailed summary")
            if NEW_FORMAT_MARKER not in detailed:
                raise RuntimeError(
                    f"regenerated summary still lacks '{NEW_FORMAT_MARKER}' marker"
                )
            _persist(bid, new_summary)
            elapsed = time.time() - t0
            successes += 1
            print(f"[{i}/{len(bills)}] {bid}: ✅ {elapsed:.1f}s ({successes} ok / {len(failures)} fail / {len(skipped_no_text)} skip)")
        except Exception as e:
            elapsed = time.time() - t0
            failures.append((bid, str(e)))
            print(f"[{i}/{len(bills)}] {bid}: ❌ {elapsed:.1f}s — {e}")
            # Sleep briefly to avoid hammering on cascading API errors
            time.sleep(2)

    total = time.time() - start
    print()
    print("=" * 60)
    print(f"✅ Regenerated: {successes}")
    print(f"❌ Failed:      {len(failures)}")
    print(f"⏭️  Skipped:    {len(skipped_no_text)} (full_text too short)")
    print(f"⏱  Total time: {total:.0f}s ({total/max(1,len(bills)):.1f}s/bill avg)")
    if failures:
        print("\nFailures:")
        for bid, err in failures[:10]:
            print(f"   {bid}: {err}")
    if skipped_no_text:
        print("\nSkipped (no full_text — leave unchanged; daily cron will skip these):")
        for bid in skipped_no_text[:20]:
            print(f"   {bid}")


if __name__ == "__main__":
    main()
