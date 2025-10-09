#!/usr/bin/env python3
"""Check recent posts and has_posted_today() status"""

import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from src.load_env import load_env
load_env()

from src.database.db import has_posted_today, init_db
from src.database.connection import postgres_connect
import logging

logging.basicConfig(level=logging.INFO)

init_db()

# Check has_posted_today
result = has_posted_today()
print(f'\n=== has_posted_today() Result ===')
print(f'Result: {result}')
print(f'Interpretation: {"BLOCKED - A bill was posted in the last 24 hours" if result else "ALLOWED - No bills posted in the last 24 hours"}')

# Check recent posts
print(f'\n=== Recent Posts (Last 5) ===')
with postgres_connect() as conn:
    cursor = conn.cursor()
    cursor.execute('''
        SELECT bill_id, title, date_processed, tweet_posted, tweet_url
        FROM bills
        WHERE tweet_posted = TRUE
        ORDER BY date_processed DESC
        LIMIT 5
    ''')
    rows = cursor.fetchall()
    if rows:
        for row in rows:
            print(f'\nBill: {row[0]}')
            print(f'  Title: {row[1][:80]}...')
            print(f'  Posted: {row[2]}')
            print(f'  Tweet URL: {row[4] or "None"}')
    else:
        print('No posted bills found in database')

    # Check all bills from today
    print(f'\n=== All Bills Processed Today ===')
    cursor.execute('''
        SELECT bill_id, title, date_processed, tweet_posted
        FROM bills
        WHERE date_processed >= CURRENT_DATE
        ORDER BY date_processed DESC
    ''')
    rows = cursor.fetchall()
    if rows:
        for row in rows:
            print(f'\nBill: {row[0]}')
            print(f'  Title: {row[1][:80]}...')
            print(f'  Processed: {row[2]}')
            print(f'  Posted: {row[3]}')
    else:
        print('No bills processed today')
    
    cursor.close()