import os
import sys
import psycopg2.extras

# Add src to path to allow imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'src')))

from load_env import load_env
load_env()

from database.connection import postgres_connect
from orchestrator import main as run_orchestrator

def reprocess_latest():
    """
    Deletes the most recent bill and re-runs the orchestrator to test fixes.
    """
    try:
        with postgres_connect() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                # Find the most recent bill
                cursor.execute("SELECT id, bill_id FROM bills ORDER BY date_processed DESC LIMIT 1")
                latest_bill = cursor.fetchone()

                if not latest_bill:
                    print("No bills found to reprocess.")
                    return

                bill_db_id = latest_bill['id']
                bill_identifier = latest_bill['bill_id']
                print(f"Found latest bill: {bill_identifier} (DB ID: {bill_db_id})")

                # Delete the bill
                print(f"Deleting bill {bill_identifier} to allow reprocessing...")
                cursor.execute("DELETE FROM bills WHERE id = %s", (bill_db_id,))
                print("Bill deleted.")

        # Now, run the orchestrator
        print("\n--- Running Orchestrator ---")
        # We can run in dry-run mode to prevent tweeting, but still see the DB insertion logs
        run_orchestrator(dry_run=True)
        print("--------------------------\n")
        print("Orchestrator run complete. Check the logs for status and slug information.")

    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    reprocess_latest()