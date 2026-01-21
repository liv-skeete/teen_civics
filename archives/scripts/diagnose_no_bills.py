#!/usr/bin/env python3
"""
Diagnostic script to investigate "No bills found" on Home and Archive.

It checks:
- DB configuration used by the web app (PostgreSQL connection string)
- Counts in PostgreSQL (total bills, tweeted bills, recent bills)
- Sample slugs returned by the same query the app uses (get_all_tweeted_bills)
- Optional: presence of local SQLite data (data/bills.db) to detect mismatch
"""

import os
import sys
from datetime import datetime

# Ensure we can import project modules under src/
sys.path.insert(0, 'src')

from database.connection import get_connection_string, is_postgres_available, postgres_connect
from database.db import get_all_tweeted_bills, get_all_bills


def count_postgres():
    with postgres_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM bills")
            total = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM bills WHERE tweet_posted = TRUE")
            tweeted = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM bills WHERE date_processed > NOW() - INTERVAL '90 days'")
            recent = cur.fetchone()[0]

            cur.execute("""
                SELECT bill_id, website_slug, status, date_processed
                FROM bills
                ORDER BY date_processed DESC
                LIMIT 5
            """)
            rows = cur.fetchall()

    return total, tweeted, recent, rows


def count_sqlite():
    """If local SQLite exists, count rows to detect mismatch."""
    path = os.path.join('data', 'bills.db')
    if not os.path.exists(path):
        return None
    try:
        import sqlite3
        conn = sqlite3.connect(path)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM bills")
        total = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM bills WHERE tweet_posted = 1")
        tweeted = cur.fetchone()[0]
        cur.execute("""
            SELECT bill_id, website_slug, status, date_processed
            FROM bills
            ORDER BY date_processed DESC
            LIMIT 5
        """)
        rows = cur.fetchall()
        conn.close()
        return total, tweeted, rows
    except Exception as e:
        return f"SQLITE_ERROR: {e}"


def main():
    print("=== Diagnose 'No bills found' ===")
    conn_str = get_connection_string()
    print(f"DATABASE_URL configured: {'YES' if conn_str else 'NO'}")
    if conn_str:
        safe = conn_str[:10] + '...' + conn_str[-10:] if len(conn_str) > 30 else conn_str
        print(f"Connection string preview: {safe}")
    print(f"Postgres available: {is_postgres_available()}")

    # PostgreSQL stats
    pg_stats = None
    try:
        pg_stats = count_postgres()
        total, tweeted, recent, rows = pg_stats
        print(f"Postgres bills total: {total}")
        print(f"Postgres tweeted: {tweeted}")
        print(f"Postgres recent (90d): {recent}")
        print("Postgres latest 5:")
        for r in rows:
            print(f" - {r[0]} slug={r[1]} status={r[2]} date={r[3]}")
    except Exception as e:
        print(f"Postgres query error: {e}")

    # SQLite stats (optional)
    sqlite_stats = count_sqlite()
    if sqlite_stats is None:
        print("SQLite data/bills.db: NOT PRESENT")
    elif isinstance(sqlite_stats, str):
        print(f"SQLite error: {sqlite_stats}")
    else:
        stotal, stweeted, srows = sqlite_stats
        print(f"SQLite bills total: {stotal}")
        print(f"SQLite tweeted: {stweeted}")
        print("SQLite latest 5:")
        for r in srows:
            print(f" - {r[0]} slug={r[1]} status={r[2]} date={r[3]}")

    # Compare with app query
    try:
        tweeted_bills = get_all_tweeted_bills(limit=10)
        print(f"\nget_all_tweeted_bills() returned: {len(tweeted_bills)}")
        print("First 5 slugs from app query:")
        for b in tweeted_bills[:5]:
            print(f" - {b.get('bill_id')} slug={b.get('website_slug')} status={b.get('status')}")
    except Exception as e:
        print(f"Error calling get_all_tweeted_bills(): {e}")

    # Guidance
    print("\n=== Diagnosis ===")
    if pg_stats and pg_stats[0] > 0 and pg_stats[1] == 0:
        print("* Root cause likely: tweet_posted filter too strict. No tweeted bills in Postgres.")
        print("* Fix options:")
        print("  - Flag at least one bill as tweeted (update tweet_posted=TRUE), or")
        print("  - Adjust app to fallback to latest processed bills if none tweeted.")
    if sqlite_stats and isinstance(sqlite_stats, tuple):
        if (pg_stats and pg_stats[0] == 0 and sqlite_stats[0] > 0):
            print("* Root cause likely: DB mismatch. Data present in SQLite but Postgres is empty.")
            print("* Fix: Set DATABASE_URL to the Postgres DB used by scripts, or migrate using scripts/migrate_to_postgresql.py.")

    print("=== End ===")


if __name__ == "__main__":
    main()