import sys
import json
import logging
import os
from dotenv import load_dotenv

# Add project root to path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

from src.fetchers.congress_fetcher import fetch_bill_details_from_api
from src.fetchers.feed_parser import scrape_bill_tracker
from src.database.db import get_bill_by_id, normalize_bill_id
from src.database.connection import postgres_connect

load_dotenv()
CONGRESS_API_KEY = os.getenv('CONGRESS_API_KEY')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def update_tracker_in_db(bill_id, tracker, latest_action_text, normalized_status):
    with postgres_connect() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
            UPDATE bills
            SET tracker_raw = %s,
                raw_latest_action = %s,
                normalized_status = %s
            WHERE bill_id = %s
            """, (json.dumps(tracker), latest_action_text, normalized_status, bill_id))
        conn.commit()
    logger.info(f"Updated tracker for {bill_id}")

def main(raw_bill_id):
    bill_id = normalize_bill_id(raw_bill_id)
    bill = get_bill_by_id(bill_id)
    if not bill:
        logger.error(f"Bill {bill_id} not found")
        return

    source_url = bill.get('source_url')
    if not source_url:
        logger.error("No source_url available")
        return

    # Scrape tracker from HTML
    tracker = scrape_bill_tracker(source_url)
    if not tracker:
        logger.error("Failed to scrape tracker")
        return

    # Fetch latest action from API
    # Parse bill_id: e.g., 'sjres83-119' -> bill_type='sjres', bill_number='83', congress='119'
    parts = bill_id.split('-')
    if len(parts) != 2:
        logger.error("Invalid bill_id format")
        return
    full_type = parts[0]
    congress = parts[1]
    bill_type = ''.join([c for c in full_type if not c.isdigit()])
    bill_number = ''.join([c for c in full_type if c.isdigit()])
    
    details = fetch_bill_details_from_api(congress, bill_type, bill_number, CONGRESS_API_KEY)
    latest_action = details.get('latest_action', {})
    latest_action_text = latest_action.get('text')

    # Normalize status
    normalized_status = 'unknown'
    for step in tracker:
        if step.get('selected', False):
            normalized_status = step['name'].lower().replace(' ', '_')
            break

    update_tracker_in_db(bill_id, tracker, latest_action_text, normalized_status)

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python3 update_bill_tracker.py <bill_id>")
        sys.exit(1)
    main(sys.argv[1])