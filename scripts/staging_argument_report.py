"""Read-only report on argument_support / argument_oppose in staging DB."""
import os, psycopg2

url = os.environ["DATABASE_URL"] + "?sslmode=require"
conn = psycopg2.connect(url)
conn.set_session(readonly=True)
cur = conn.cursor()

# Total bills
cur.execute("SELECT COUNT(*) FROM bills")
total = cur.fetchone()[0]
print(f"Total bills: {total}")

# Non-empty argument_support
cur.execute("SELECT COUNT(*) FROM bills WHERE argument_support IS NOT NULL AND argument_support != ''")
sup = cur.fetchone()[0]
print(f"Non-empty argument_support: {sup}")

# Non-empty argument_oppose
cur.execute("SELECT COUNT(*) FROM bills WHERE argument_oppose IS NOT NULL AND argument_oppose != ''")
opp = cur.fetchone()[0]
print(f"Non-empty argument_oppose: {opp}")

# 5 sample rows
print("\n=== 5 SAMPLE ROWS ===")
cur.execute(
    "SELECT bill_id, LEFT(argument_support, 140), LEFT(argument_oppose, 140) "
    "FROM bills "
    "WHERE argument_support IS NOT NULL AND argument_support != '' "
    "ORDER BY date_processed DESC LIMIT 5"
)
for row in cur.fetchall():
    print(f"\n--- {row[0]} ---")
    print(f"  SUPPORT: {row[1]}")
    print(f"  OPPOSE:  {row[2]}")

# Prefix checks
print("\n=== PREFIX CHECKS ===")

cur.execute("SELECT COUNT(*) FROM bills WHERE argument_support LIKE 'I SUPPORT%'")
print(f"argument_support starts with 'I SUPPORT': {cur.fetchone()[0]}")

cur.execute("SELECT COUNT(*) FROM bills WHERE argument_oppose LIKE 'I SUPPORT%'")
print(f"argument_oppose starts with 'I SUPPORT': {cur.fetchone()[0]}")

cur.execute("SELECT COUNT(*) FROM bills WHERE argument_support LIKE 'I OPPOSE%'")
print(f"argument_support starts with 'I OPPOSE': {cur.fetchone()[0]}")

cur.execute("SELECT COUNT(*) FROM bills WHERE argument_oppose LIKE 'I OPPOSE%'")
print(f"argument_oppose starts with 'I OPPOSE': {cur.fetchone()[0]}")

# Case-insensitive
cur.execute(
    "SELECT COUNT(*) FROM bills WHERE UPPER(argument_support) LIKE 'I SUPPORT%' "
    "OR UPPER(argument_support) LIKE 'I OPPOSE%'"
)
print(f"\nargument_support 'I SUPPORT/I OPPOSE' (case-insensitive): {cur.fetchone()[0]}")

cur.execute(
    "SELECT COUNT(*) FROM bills WHERE UPPER(argument_oppose) LIKE 'I SUPPORT%' "
    "OR UPPER(argument_oppose) LIKE 'I OPPOSE%'"
)
print(f"argument_oppose 'I SUPPORT/I OPPOSE' (case-insensitive): {cur.fetchone()[0]}")

conn.close()
print("\n✅ Done (read-only)")
