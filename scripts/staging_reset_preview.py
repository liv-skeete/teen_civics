#!/usr/bin/env python3
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from src.database.connection import postgres_connect
import psycopg2.extras

with postgres_connect() as conn:
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""
            SELECT bill_id, problem_reason, problematic_marked_at
            FROM bills
            WHERE problematic = TRUE AND recheck_attempted = TRUE
            ORDER BY problematic_marked_at ASC
        """)
        rows = cur.fetchall()
        print(f"Total locked out: {len(rows)}")
        print("--- First 10 ---")
        for row in rows[:10]:
            reason = (row['problem_reason'] or 'None')[:60]
            print(f"  {row['bill_id']} | {reason} | {row['problematic_marked_at']}")
