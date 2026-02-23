#!/usr/bin/env python3

import os, sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.database.connection import postgres_connect

import psycopg2.extras

with postgres_connect() as conn:

    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:

        queries = {

            "total_problematic": "SELECT COUNT(*) as cnt FROM bills WHERE problematic = TRUE",

            "locked_out": "SELECT COUNT(*) as cnt FROM bills WHERE problematic = TRUE AND recheck_attempted = TRUE",

            "eligible": """SELECT COUNT(*) as cnt FROM bills

                WHERE problematic = TRUE

                AND (recheck_attempted IS NULL OR recheck_attempted = FALSE)

                AND problematic_marked_at IS NOT NULL

                AND problematic_marked_at <= NOW() - INTERVAL '15 days'""",

            "waiting": """SELECT COUNT(*) as cnt FROM bills

                WHERE problematic = TRUE

                AND (recheck_attempted IS NULL OR recheck_attempted = FALSE)

                AND problematic_marked_at IS NOT NULL

                AND problematic_marked_at > NOW() - INTERVAL '15 days'""",

        }

        for label, sql in queries.items():

            cur.execute(sql)

            print(f"{label}: {cur.fetchone()['cnt']}")

        print("\n--- Locked out sample ---")

        cur.execute("""SELECT bill_id, problem_reason, problematic_marked_at

            FROM bills WHERE problematic = TRUE AND recheck_attempted = TRUE

            ORDER BY problematic_marked_at ASC LIMIT 10""")

        for row in cur.fetchall():

            print(f"  {row['bill_id']} | {row['problem_reason'][:60] if row['problem_reason'] else 'None'} | {row['problematic_marked_at']}")
