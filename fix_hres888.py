#!/usr/bin/env python3
"""Fix missing date_introduced for hres888-119."""

import os
os.environ['FLASK_APP'] = 'app.py'

from app import app
from src.database.connection import postgres_connect

bill_id = 'hres888-119'
introduced_date = '2025-11-18'

with app.app_context():
    print(f"Updating {bill_id} with date_introduced={introduced_date}...")
    
    try:
        with postgres_connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    'UPDATE bills SET date_introduced = %s WHERE bill_id = %s',
                    (introduced_date, bill_id)
                )
                if cursor.rowcount > 0:
                    print("✅ Successfully updated bill")
                    conn.commit()
                else:
                    print("❌ Bill not found in database")
    except Exception as e:
        print(f"❌ Error updating bill: {e}")
