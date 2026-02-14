#!/usr/bin/env python3
"""
Backfill subject_tags for existing bills that have no tags assigned.

Uses Venice AI to classify bills based on their title and summary_overview,
then validates tags against the canonical taxonomy.

Usage:
    python -m scripts.backfill_subject_tags            # live run
    python -m scripts.backfill_subject_tags --dry-run  # preview only
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

from openai import OpenAI
from src.utils.subject_tags import validate_tags, SUBJECT_TAGS
from src.database.connection import postgres_connect

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

VENICE_BASE_URL = os.getenv("VENICE_BASE_URL", "https://api.venice.ai/api/v1")
PREFERRED_MODEL = os.getenv("SUMMARIZER_MODEL", "claude-sonnet-45")
RATE_LIMIT_SECONDS = 1.5  # delay between API calls

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Venice AI helper
# ---------------------------------------------------------------------------

def _get_venice_client() -> OpenAI:
    api_key = os.getenv("VENICE_API_KEY")
    if not api_key:
        raise ValueError("VENICE_API_KEY not found in environment variables")
    return OpenAI(api_key=api_key, base_url=VENICE_BASE_URL)


TAGGING_SYSTEM_PROMPT = f"""You are a bill classifier. Given a bill's title and summary, return 1-3 subject tag slugs from the following list. Return ONLY a comma-separated list of slugs, nothing else.

Valid slugs:
{chr(10).join(f"  {slug} — {name}" for slug, name in SUBJECT_TAGS.items())}
  miscellaneous — use only if none of the above fit

Rules:
- Return 1 to 3 tags, comma-separated, no spaces around commas.
- Choose the most specific tags that apply.
- Use "miscellaneous" only as a last resort.
- Do NOT include any explanation, just the slugs.

Example output: economy-finance,education-youth
"""


def classify_bill(client: OpenAI, title: str, overview: str) -> str:
    """Call Venice AI to classify a bill and return validated tags CSV."""
    user_msg = f"Title: {title}\n\nSummary: {overview}"
    try:
        response = client.chat.completions.create(
            model=PREFERRED_MODEL,
            max_tokens=60,
            temperature=0.2,
            messages=[
                {"role": "system", "content": TAGGING_SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
        )
        raw = response.choices[0].message.content.strip()
        validated = validate_tags(raw)
        if not validated:
            logger.warning("AI returned no valid tags for '%s'. Raw: %s", title[:60], raw)
        return validated
    except Exception as e:
        logger.error("Venice AI call failed for '%s': %s", title[:60], e)
        return ""

# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def fetch_untagged_bills():
    """Return list of dicts with id, bill_id, title, summary_overview for untagged bills."""
    with postgres_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, bill_id, title, summary_overview
                FROM bills
                WHERE (subject_tags IS NULL OR subject_tags = '')
                  AND summary_overview IS NOT NULL
                  AND summary_overview != ''
                ORDER BY id
            """)
            cols = [desc[0] for desc in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]


def update_bill_tags(bill_id: str, tags: str):
    """Write subject_tags for a bill."""
    with postgres_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE bills SET subject_tags = %s WHERE bill_id = %s",
                (tags, bill_id),
            )

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Backfill subject_tags for bills")
    parser.add_argument("--dry-run", action="store_true", help="Preview tags without writing to DB")
    args = parser.parse_args()

    bills = fetch_untagged_bills()
    total = len(bills)
    logger.info("Found %d bills needing subject tags%s", total, " (DRY RUN)" if args.dry_run else "")

    if total == 0:
        logger.info("Nothing to do — all bills already have tags.")
        return

    client = _get_venice_client()
    tagged = 0
    skipped = 0

    for i, bill in enumerate(bills, 1):
        title = bill["title"] or ""
        overview = bill["summary_overview"] or ""
        bill_id = bill["bill_id"]

        if not title and not overview:
            logger.warning("[%d/%d] Skipping %s — no title or overview", i, total, bill_id)
            skipped += 1
            continue

        tags = classify_bill(client, title, overview)

        if tags:
            if args.dry_run:
                logger.info("[%d/%d] DRY RUN — Tagged bill %s: %s", i, total, bill_id, tags)
            else:
                update_bill_tags(bill_id, tags)
                logger.info("[%d/%d] Tagged bill %s: %s", i, total, bill_id, tags)
            tagged += 1
        else:
            logger.warning("[%d/%d] No valid tags for %s — skipping", i, total, bill_id)
            skipped += 1

        # Rate limiting between API calls
        if i < total:
            time.sleep(RATE_LIMIT_SECONDS)

    logger.info("Done. Tagged: %d, Skipped: %d, Total: %d", tagged, skipped, total)


if __name__ == "__main__":
    main()
