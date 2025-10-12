import psycopg2
from src.database.connection import postgres_connect

with postgres_connect() as conn:
    with conn.cursor() as cursor:
        cursor.execute("""
        ALTER TABLE bills
        ADD COLUMN IF NOT EXISTS raw_latest_action TEXT,
        ADD COLUMN IF NOT EXISTS tracker_raw JSONB,
        ADD COLUMN IF NOT EXISTS normalized_status TEXT;
        """)
    conn.commit()

print("Added tracker fields to bills table")