import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from dotenv import load_dotenv
load_dotenv()

from src.database.connection import postgres_connect

with postgres_connect() as conn:
    with conn.cursor() as cursor:
        cursor.execute("SELECT enumlabel FROM pg_enum WHERE enumtypid = 'bill_status'::regtype::oid")
        values = cursor.fetchall()
        print('Valid bill_status values:')
        for val in values:
            print(f'  {val[0]}')