#!/usr/bin/env python3
"""
Script to check hr5371-119 data in the database
"""

import sqlite3
import json
import os

def get_db_path():
    """Get the database path"""
    return os.path.join(os.path.dirname(__file__), '..', 'data', 'bills.db')

def check_hr5371_data():
    """Check hr5371-119 data in the database"""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    try:
        # Query for hr5371-119
        cursor = conn.cursor()
        cursor.execute("""
            SELECT bill_id, title, status, 
                   summary_tweet, summary_long, date_processed
            FROM bills 
            WHERE bill_id = 'hr5371-119'
        """)
        
        row = cursor.fetchone()
        if row:
            print("\n=== hr5371-119 Data ===")
            print(f"Bill ID: {row[0]}")
            print(f"Title: {row[1]}")
            print(f"Status: {row[2]}")
            print(f"Summary Tweet: {row[3][:100]}...")
            print(f"Summary Long: {row[4][:100]}...")
            print(f"Date Processed: {row[5]}")
        else:
            print("\nhr5371-119 not found in database!")
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    check_hr5371_data()