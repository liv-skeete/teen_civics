"""Regenerate the summary for one bill using the current prompt.

Staging by default: refuses to run if DATABASE_URL points at the prod
Postgres host ('centerbeam'). Use this to A/B-test prompt changes on
staging without any chance of touching prod data.

Prod regen (rare, deliberate): pass --i-mean-prod to allow running
against centerbeam. Intended for one-off cases like reformatting the
current homepage bill after a prompt change. Combine with --dry-run
first to preview the output before writing.

Usage:
    python3 scripts/regen_summary_test.py hr7308-119
    python3 scripts/regen_summary_test.py hr7308-119 --dry-run
    python3 scripts/regen_summary_test.py sres536-119 --i-mean-prod --dry-run
    python3 scripts/regen_summary_test.py sres536-119 --i-mean-prod
"""

import argparse
import logging
import os
import sys

# Make src/ importable when running from project root
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.load_env import load_env

load_env()

# When --i-mean-prod is passed, point DATABASE_URL at PROD_DATABASE_URL
# AFTER load_env (which would otherwise clobber any exported override
# with the staging URL from .env). Argparse runs after this import, so
# defer the swap into main().

from src.database.connection import postgres_connect
from src.processors.summarizer import summarize_bill_enhanced

PROD_HOST_MARKER = "centerbeam"


def _assert_not_prod(allow_prod: bool = False) -> None:
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        sys.exit("REFUSING TO RUN: DATABASE_URL not set.")
    if PROD_HOST_MARKER in url:
        if not allow_prod:
            sys.exit(
                f"REFUSING TO RUN: DATABASE_URL contains '{PROD_HOST_MARKER}' — "
                "this is the production database. Pass --i-mean-prod to override "
                "(intended only for deliberate one-off prod regens like reformatting "
                "the homepage bill after a prompt change)."
            )
        print("⚠️  PROD MODE: writing to centerbeam (production). --i-mean-prod set.")


def _load_bill(bill_id: str) -> dict:
    with postgres_connect() as conn:
        if conn is None:
            sys.exit("Could not get DB connection.")
        cur = conn.cursor()
        cur.execute(
            """
            SELECT bill_id, title, short_title, status, normalized_status,
                   congress_session, date_introduced, source_url,
                   sponsor_name, sponsor_party, sponsor_state,
                   full_text, summary_detailed
            FROM bills WHERE bill_id = %s
            """,
            (bill_id,),
        )
        row = cur.fetchone()
        cur.close()
        if not row:
            sys.exit(f"Bill {bill_id} not found.")
        cols = [
            "bill_id", "title", "short_title", "status", "normalized_status",
            "congress_session", "date_introduced", "source_url",
            "sponsor_name", "sponsor_party", "sponsor_state",
            "full_text", "summary_detailed",
        ]
        return dict(zip(cols, row))


def _persist(bill_id: str, summary: dict) -> None:
    with postgres_connect() as conn:
        if conn is None:
            sys.exit("Could not get DB connection for write.")
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
    parser.add_argument("bill_id", help="e.g. hr7308-119")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the new summary but do not write to DB.",
    )
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument(
        "--i-mean-prod",
        action="store_true",
        dest="allow_prod",
        help="Allow running against the production DB (centerbeam). Use deliberately.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if args.allow_prod:
        prod_url = os.environ.get("PROD_DATABASE_URL", "")
        if not prod_url:
            sys.exit("REFUSING TO RUN: --i-mean-prod set but PROD_DATABASE_URL not in .env.")
        os.environ["DATABASE_URL"] = prod_url

    _assert_not_prod(allow_prod=args.allow_prod)

    bill = _load_bill(args.bill_id)
    print(f"Bill: {bill['bill_id']}  |  {bill['title'][:100]}")
    print(f"Old summary length: {len((bill['summary_detailed'] or '').split())} words")
    print("-" * 70)

    new_summary = summarize_bill_enhanced(bill)
    if not new_summary or not new_summary.get("detailed"):
        sys.exit("Summarizer returned empty output.")

    detailed = new_summary["detailed"]
    print(detailed)
    print("-" * 70)
    print(f"New summary length: {len(detailed.split())} words")

    if args.dry_run:
        print("(dry-run: not persisting)")
        return

    _persist(args.bill_id, new_summary)
    target = "PROD" if args.allow_prod else "staging"
    print(f"Wrote new summary for {args.bill_id} to {target} DB.")


if __name__ == "__main__":
    main()
