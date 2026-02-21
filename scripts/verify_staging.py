"""Read-only verification of staging DB: bills count + argument prefix check."""
import os, sys, psycopg2

url = os.environ.get("STAGING_DATABASE_URL") or os.environ.get("DATABASE_URL")
if not url:
    sys.exit("ERROR: Set STAGING_DATABASE_URL or DATABASE_URL")

if "sslmode" not in url:
    url += "?sslmode=require"

conn = psycopg2.connect(url)
conn.set_session(readonly=True)
cur = conn.cursor()

# --- counts ---
cur.execute("SELECT COUNT(*) FROM bills")
total = cur.fetchone()[0]

cur.execute("SELECT COUNT(*) FROM bills WHERE argument_support IS NOT NULL AND argument_support != ''")
n_support = cur.fetchone()[0]

cur.execute("SELECT COUNT(*) FROM bills WHERE argument_oppose IS NOT NULL AND argument_oppose != ''")
n_oppose = cur.fetchone()[0]

print(f"Total bills:            {total}")
print(f"With argument_support:  {n_support}")
print(f"With argument_oppose:   {n_oppose}")

# --- sample prefix check ---
cur.execute("""
    SELECT bill_id, LEFT(argument_support, 80), LEFT(argument_oppose, 80)
    FROM bills
    WHERE argument_support IS NOT NULL AND argument_support != ''
      AND argument_oppose  IS NOT NULL AND argument_oppose  != ''
    ORDER BY date_processed DESC
    LIMIT 5
""")
rows = cur.fetchall()
print(f"\n--- Prefix check on {len(rows)} most-recent samples ---")
for bill_id, sup, opp in rows:
    sup_ok = sup.strip().startswith("I SUPPORT")
    opp_ok = opp.strip().startswith("I OPPOSE")
    print(f"  {bill_id}: support starts 'I SUPPORT' = {sup_ok} | oppose starts 'I OPPOSE' = {opp_ok}")
    if not sup_ok:
        print(f"    -> actual support prefix: {sup[:40]}")
    if not opp_ok:
        print(f"    -> actual oppose prefix:  {opp[:40]}")

conn.close()
print("\n✅ Read-only staging verification complete.")
