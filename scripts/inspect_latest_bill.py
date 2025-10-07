import os
import sys
import psycopg2.extras

# Add src to path to allow imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'src')))

from load_env import load_env
load_env()

from database.connection import postgres_connect

def inspect_latest_bill():
    """
    Fetches and prints the record for the most recently processed bill.
    """
    try:
        with postgres_connect() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                # Fetch the bill with the most recent 'date_processed' timestamp
                cursor.execute("SELECT * FROM bills ORDER BY date_processed DESC LIMIT 1")
                latest_bill = cursor.fetchone()

                if not latest_bill:
                    print("No bills found in the database.")
                    return

                print("--- Inspecting Latest Bill ---")
                for key, value in latest_bill.items():
                    print(f"{key}: {value}")
                print("----------------------------")

    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    inspect_latest_bill()