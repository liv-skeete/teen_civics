#!/usr/bin/env python3
"""
Migration: Add 'hidden' column to bills table for soft-delete support.

Safe to run multiple times — checks for column existence first.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.database.connection import postgres_connect

def migrate():
    with postgres_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'bills' AND column_name = 'hidden'
            """)
            if cur.fetchone():
                print("✅ 'hidden' column already exists — nothing to do.")
                return

            print("Adding 'hidden' column to bills table...")
            cur.execute("ALTER TABLE bills ADD COLUMN hidden BOOLEAN DEFAULT FALSE;")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_bills_hidden ON bills (hidden);")
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_bills_published_hidden_date "
                "ON bills (published, hidden, date_processed DESC);"
            )
            print("✅ Migration complete — 'hidden' column added with indexes.")

if __name__ == "__main__":
    migrate()
