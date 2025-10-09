#!/usr/bin/env python3
"""
Fix the status for H.J.Res.104 to show "Passed House" instead of the latest action text.
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Load environment variables
from src.load_env import load_env
load_env()

from src.database.connection import postgres_connect, init_connection_pool

def fix_hjres104_status():
    """Update the status for H.J.Res.104 to 'Passed House'"""
    # Initialize connection pool
    init_connection_pool()
    
    with postgres_connect() as conn:
        cursor = conn.cursor()
        
        try:
            # Update the status for H.J.Res.104
            cursor.execute("""
                UPDATE bills
                SET status = 'Passed House'
                WHERE bill_id = 'hjres104-119'
            """)
            
            rows_updated = cursor.rowcount
            
            print(f"✅ Updated status for {rows_updated} bill(s)")
            
            # Verify the update
            cursor.execute("""
                SELECT bill_id, title, status
                FROM bills
                WHERE bill_id = 'hjres104-119'
            """)
            
            results = cursor.fetchall()
            for row in results:
                print(f"\nBill ID: {row[0]}")
                print(f"Title: {row[1][:100]}...")
                print(f"Status: {row[2]}")
                
        except Exception as e:
            print(f"❌ Error updating status: {e}")
            raise
        finally:
            cursor.close()

if __name__ == "__main__":
    fix_hjres104_status()