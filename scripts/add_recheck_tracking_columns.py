#!/usr/bin/env python3
"""
Migration: Add recheck-tracking columns to bills table.

New columns:
  - problematic_marked_at  TIMESTAMP  — when the bill was first marked problematic
  - recheck_attempted      BOOLEAN    — TRUE after the single 15-day recheck has run

Together these enforce:
  1. A 15-day cooling-off period before a problematic bill is re-scraped.
  2. A single recheck attempt — once recheck_attempted is TRUE, the bill is
     permanently locked out (unless manually cleared or data resolves the issue).

Safe to run multiple times — checks for column existence first.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.database.connection import postgres_connect


def migrate():
    with postgres_connect() as conn:
        with conn.cursor() as cur:
            # Check which columns already exist
            cur.execute("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'bills'
                  AND column_name IN ('problematic_marked_at', 'recheck_attempted')
            """)
            existing = {row[0] for row in cur.fetchall()}

            if 'problematic_marked_at' in existing and 'recheck_attempted' in existing:
                print("✅ Both recheck-tracking columns already exist — nothing to do.")
                return

            if 'problematic_marked_at' not in existing:
                print("Adding 'problematic_marked_at' column to bills table...")
                cur.execute(
                    "ALTER TABLE bills ADD COLUMN problematic_marked_at TIMESTAMP;"
                )
                # Backfill: set existing problematic bills to NOW() so they are
                # eligible for recheck in 15 days from today rather than immediately.
                cur.execute("""
                    UPDATE bills
                    SET problematic_marked_at = CURRENT_TIMESTAMP
                    WHERE problematic = TRUE
                      AND problematic_marked_at IS NULL
                """)
                print(f"  ↳ Back-filled {cur.rowcount} existing problematic bills.")

            if 'recheck_attempted' not in existing:
                print("Adding 'recheck_attempted' column to bills table...")
                cur.execute(
                    "ALTER TABLE bills ADD COLUMN recheck_attempted BOOLEAN DEFAULT FALSE;"
                )

            # Index for the recovery query:
            #   WHERE problematic = TRUE AND recheck_attempted = FALSE
            #         AND problematic_marked_at <= NOW() - INTERVAL '15 days'
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_bills_problematic_recheck
                ON bills (problematic, recheck_attempted, problematic_marked_at)
                WHERE problematic = TRUE;
            """)

            print("✅ Migration complete — recheck-tracking columns added.")


if __name__ == "__main__":
    migrate()
