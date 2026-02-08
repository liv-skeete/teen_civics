#!/usr/bin/env python3
"""
Schema Cleanup Migration — 2026-02-08

Drops 12 dead/redundant columns from the `bills` table and renames
`tweet_posted` → `published` to reflect its true purpose as the site
publication flag.

Each ALTER TABLE runs in its own try/except so the script is idempotent:
  - DROP COLUMN IF EXISTS is safe to re-run.
  - RENAME COLUMN will raise an error if already renamed — caught gracefully.

Usage:
    python scripts/schema_cleanup_migration.py
"""

import os
import sys
import logging

# Ensure project root is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.load_env import load_env
load_env()

from src.database.connection import postgres_connect

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# ── Columns to DROP ──────────────────────────────────────────────────────────
DROP_COLUMNS = [
    "poll_results_unsure",
    "text_format",
    "term_dictionary",
    "tweet_url",
    "processing_attempts",
    "text_source",
    "text_version",
    "text_received_date",
    "raw_latest_action",
    "tracker_raw",
]

# ── Column to RENAME ─────────────────────────────────────────────────────────
RENAME_FROM = "tweet_posted"
RENAME_TO = "published"


def run_migration():
    logger.info("=" * 60)
    logger.info("  Schema Cleanup Migration — 2026-02-08")
    logger.info("=" * 60)

    success_count = 0
    skip_count = 0
    error_count = 0

    # ── Phase 1: DROP columns ────────────────────────────────────────────────
    logger.info("\n── Phase 1: Dropping dead columns ──")
    for col in DROP_COLUMNS:
        try:
            with postgres_connect() as conn:
                with conn.cursor() as cur:
                    sql = f"ALTER TABLE bills DROP COLUMN IF EXISTS {col};"
                    logger.info(f"  DROP COLUMN IF EXISTS {col}")
                    cur.execute(sql)
            success_count += 1
        except Exception as e:
            logger.warning(f"  ⚠️  DROP {col} failed (may already be dropped): {e}")
            skip_count += 1

    # ── Phase 2: RENAME tweet_posted → published ─────────────────────────────
    logger.info("\n── Phase 2: Renaming tweet_posted → published ──")
    try:
        with postgres_connect() as conn:
            with conn.cursor() as cur:
                # Check if 'published' column already exists
                cur.execute("""
                    SELECT column_name FROM information_schema.columns
                    WHERE table_name = 'bills' AND column_name = %s
                """, (RENAME_TO,))
                if cur.fetchone():
                    logger.info(f"  ✅ Column '{RENAME_TO}' already exists — skipping rename")
                    skip_count += 1
                else:
                    # Check if tweet_posted still exists (to rename it)
                    cur.execute("""
                        SELECT column_name FROM information_schema.columns
                        WHERE table_name = 'bills' AND column_name = %s
                    """, (RENAME_FROM,))
                    if cur.fetchone():
                        sql = f"ALTER TABLE bills RENAME COLUMN {RENAME_FROM} TO {RENAME_TO};"
                        logger.info(f"  RENAME COLUMN {RENAME_FROM} → {RENAME_TO}")
                        cur.execute(sql)
                        success_count += 1
                    else:
                        logger.warning(f"  ⚠️  Column '{RENAME_FROM}' not found — nothing to rename")
                        skip_count += 1
    except Exception as e:
        logger.error(f"  ❌ RENAME failed: {e}")
        error_count += 1

    # ── Phase 3: Update index name ───────────────────────────────────────────
    logger.info("\n── Phase 3: Updating index tweet_posted → published ──")
    try:
        with postgres_connect() as conn:
            with conn.cursor() as cur:
                # Drop old index if it exists
                cur.execute("DROP INDEX IF EXISTS idx_bills_tweet_posted;")
                logger.info("  Dropped old index idx_bills_tweet_posted (if existed)")
                # Create new index on published
                cur.execute("CREATE INDEX IF NOT EXISTS idx_bills_published ON bills (published);")
                logger.info("  Created index idx_bills_published")
                success_count += 1
    except Exception as e:
        logger.error(f"  ❌ Index update failed: {e}")
        error_count += 1

    # ── Phase 4: Verify final schema ─────────────────────────────────────────
    logger.info("\n── Phase 4: Verifying final schema ──")
    try:
        with postgres_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT column_name, data_type, column_default
                    FROM information_schema.columns
                    WHERE table_name = 'bills'
                    ORDER BY ordinal_position
                """)
                columns = cur.fetchall()
                logger.info(f"  bills table has {len(columns)} columns:")
                for col_name, data_type, default in columns:
                    logger.info(f"    {col_name:30s}  {data_type:20s}  default={default}")

                # Verify dropped columns are gone
                col_names = {row[0] for row in columns}
                all_dropped = DROP_COLUMNS + [RENAME_FROM]
                still_present = [c for c in all_dropped if c in col_names]
                if still_present:
                    logger.error(f"  ❌ These columns should be gone but still exist: {still_present}")
                    error_count += len(still_present)
                else:
                    logger.info(f"  ✅ All {len(all_dropped)} dropped/renamed columns confirmed absent")

                # Verify 'published' column exists
                if RENAME_TO in col_names:
                    logger.info(f"  ✅ Column '{RENAME_TO}' exists")
                else:
                    logger.error(f"  ❌ Column '{RENAME_TO}' NOT found!")
                    error_count += 1

    except Exception as e:
        logger.error(f"  ❌ Schema verification failed: {e}")
        error_count += 1

    # ── Summary ──────────────────────────────────────────────────────────────
    logger.info("\n" + "=" * 60)
    logger.info(f"  Migration complete: {success_count} succeeded, {skip_count} skipped, {error_count} errors")
    logger.info("=" * 60)

    return 0 if error_count == 0 else 1


if __name__ == "__main__":
    sys.exit(run_migration())
