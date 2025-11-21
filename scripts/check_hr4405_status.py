"""
Check current status of HR4405-119 in the database
"""
import sys
import os

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.database.db import db_connect

def check_bill_status():
    """Check the current status of HR4405-119 in the database"""
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT bill_id, title, status, latest_action, latest_action_date, 
                       source_url, date_introduced
                FROM bills
                WHERE bill_id = %s
            """, ("hr4405-119",))
            
            bill = cur.fetchone()
            
            if bill:
                print(f"Found HR4405-119 in database:")
                print(f"  Bill ID: {bill[0]}")
                print(f"  Title: {bill[1]}")
                print(f"  Current Status: {bill[2]}")
                print(f"  Latest Action: {bill[3]}")
                print(f"  Latest Action Date: {bill[4]}")
                print(f"  Source URL: {bill[5]}")
                print(f"  Date Introduced: {bill[6]}")
            else:
                print("❌ HR4405-119 not found in database")

if __name__ == "__main__":
    check_bill_status()
