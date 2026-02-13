#!/usr/bin/env python3
"""
Migration script: Add composite indexes for /bills archive page performance.

These indexes target the most common query patterns on the archive page:
  1. Browse all published bills sorted by date
  2. Filter by status + date
  3. Sort by teen impact score
  4. Filter by normalized_status

Run once against the production database. Safe to run multiple times
(uses IF NOT EXISTS).

Usage:
    python scripts/add_archive_performance_indexes.py
"""

import sys
import os
import time

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.load_env import load_env
load_env()

from src.database.db import db_connect

INDEXES = [
    # Composite: browse published bills by date (covers WHERE published=TRUE ORDER BY date_processed DESC)
    "CREATE INDEX IF NOT EXISTS idx_bills_published_date ON bills (published, date_processed DESC);",
    # Composite: filter by status within published bills
    "CREATE INDEX IF NOT EXISTS idx_bills_published_status_date ON bills (published, normalized_status, date_processed DESC);",
    # Composite: sort by teen impact score within published bills
    "CREATE INDEX IF NOT EXISTS idx_bills_published_impact ON bills (published, teen_impact_score DESC NULLS LAST, date_processed DESC);",
    # Single-column: normalized_status for count queries
    "CREATE INDEX IF NOT EXISTS idx_bills_normalized_status ON bills (normalized_status);",
]


def main():
    print("=== Archive Performance Index Migration ===\n")
    
    with db_connect() as conn:
        if conn is None:
            print("ERROR: Could not connect to database. Check DATABASE_URL.")
            sys.exit(1)

        with conn.cursor() as cursor:
            for sql in INDEXES:
                # Extract index name for logging
                idx_name = sql.split("IF NOT EXISTS ")[1].split(" ON")[0]
                print(f"  Creating index: {idx_name} ... ", end="", flush=True)
                start = time.time()
                cursor.execute(sql)
                elapsed = time.time() - start
                print(f"OK ({elapsed:.2f}s)")

    print("\n✅ All indexes created successfully.")

    # Verify indexes exist
    print("\nVerifying indexes on 'bills' table:")
    with db_connect() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT indexname, indexdef
                FROM pg_indexes
                WHERE tablename = 'bills'
                ORDER BY indexname;
            """)
            for row in cursor.fetchall():
                print(f"  ✓ {row[0]}")

    print("\nDone.")


if __name__ == "__main__":
    main()
