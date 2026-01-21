import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from dotenv import load_dotenv
load_dotenv()

from src.database.connection import postgres_connect

with postgres_connect() as conn:
    with conn.cursor() as cursor:
        cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name = %s ORDER BY ordinal_position", ('bills',))
        columns = cursor.fetchall()
        print('All database columns:')
        for col in columns:
            print(f'  {col[0]}')