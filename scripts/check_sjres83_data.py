#!/usr/bin/env python3
"""
Script to check S.J.Res.83 data in the database
"""

import sqlite3
import json
import os

def get_db_path():
    """Get the database path"""
    return os.path.join(os.path.dirname(__file__), '..', 'data', 'bills.db')

def check_database_schema():
    """Check the database schema"""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(bills)")
        columns = cursor.fetchall()
        print("=== Database Schema ===")
        for col in columns:
            print(f"Column: {col[1]}, Type: {col[2]}, Not Null: {col[3]}, Default: {col[4]}, PK: {col[5]}")
    except Exception as e:
        print(f"Error checking schema: {e}")
    finally:
        conn.close()

def list_all_bills():
    """List all bills in the database"""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT bill_id, title, status FROM bills")
        rows = cursor.fetchall()
        print("\n=== All Bills in Database ===")
        for row in rows:
            print(f"Bill ID: {row[0]}, Title: {row[1][:50]}..., Status: {row[2]}")
    except Exception as e:
        print(f"Error listing bills: {e}")
    finally:
        conn.close()

def check_sjres83_data():
    """Check S.J.Res.83 data in the database"""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    try:
        # Query for S.J.Res.83 variations
        cursor = conn.cursor()
        cursor.execute("""
            SELECT bill_id, title, status, 
                   summary_tweet, summary_long, date_processed
            FROM bills 
            WHERE bill_id LIKE '%83%' OR bill_id LIKE '%sjres%'
        """)
        
        rows = cursor.fetchall()
        if rows:
            print("\n=== Potential S.J.Res.83 Related Data ===")
            for row in rows:
                print(f"Bill ID: {row[0]}")
                print(f"Title: {row[1]}")
                print(f"Status: {row[2]}")
                print(f"Summary Tweet: {row[3][:100]}...")
                print(f"Summary Long: {row[4][:100]}...")
                print(f"Date Processed: {row[5]}")
                print("---")
        else:
            print("\nNo S.J.Res.83 related bills found in database!")
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    check_database_schema()
    list_all_bills()
    check_sjres83_data()