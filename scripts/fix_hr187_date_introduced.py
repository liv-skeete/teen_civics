#!/usr/bin/env python3
"""
Script to fix the date_introduced field for hr187-119 in the database.
Fetches the correct date from the Congress.gov API and updates the database record.
"""

import os
import sys
import logging
import requests

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from src.database.db import db_connect, get_bill_by_id

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def fetch_introduced_date_from_api(bill_id: str) -> str | None:
    """Fetch the introducedDate from the Congress.gov API."""
    api_key = os.getenv('CONGRESS_API_KEY')
    if not api_key:
        logger.error("CONGRESS_API_KEY not set")
        return None
    
    # Parse bill_id (e.g., "hr187-119")
    import re
    match = re.match(r'([a-z]+)(\d+)-(\d+)', bill_id.lower())
    if not match:
        logger.error(f"Invalid bill_id format: {bill_id}")
        return None
    
    bill_type, bill_number, congress = match.groups()
    
    url = f"https://api.congress.gov/v3/bill/{congress}/{bill_type}/{bill_number}?api_key={api_key}"
    logger.info(f"Fetching bill details from: {url}")
    
    try:
        response = requests.get(url, headers={"Accept": "application/json"}, timeout=30)
        response.raise_for_status()
        data = response.json()
        bill_data = data.get('bill', {})
        introduced_date = bill_data.get('introducedDate')
        logger.info(f"API returned introducedDate: {introduced_date}")
        return introduced_date
    except Exception as e:
        logger.error(f"Failed to fetch from API: {e}")
        return None

def fix_bill_date_introduced(bill_id: str, dry_run: bool = False) -> bool:
    """Fix the date_introduced field for a specific bill."""
    
    # First, check current database value
    bill = get_bill_by_id(bill_id)
    if not bill:
        logger.error(f"Bill {bill_id} not found in database")
        return False
    
    current_date = bill.get('date_introduced')
    logger.info(f"Current date_introduced in database: {current_date}")
    
    # Fetch correct date from API
    correct_date = fetch_introduced_date_from_api(bill_id)
    if not correct_date:
        logger.error("Could not fetch correct date from API")
        return False
    
    if current_date == correct_date:
        logger.info(f"✅ Date is already correct: {correct_date}")
        return True
    
    logger.info(f"📝 Date needs update: {current_date} -> {correct_date}")
    
    if dry_run:
        logger.info("🔍 DRY RUN - no changes made")
        return True
    
    # Update the database
    try:
        with db_connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute('''
                UPDATE bills
                SET date_introduced = %s
                WHERE bill_id = %s
                ''', (correct_date, bill_id.lower()))
                
                if cursor.rowcount == 1:
                    logger.info(f"✅ Successfully updated date_introduced for {bill_id} to {correct_date}")
                    return True
                else:
                    logger.error(f"Update affected {cursor.rowcount} rows (expected 1)")
                    return False
    except Exception as e:
        logger.error(f"Database update failed: {e}")
        return False

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Fix date_introduced for a specific bill")
    parser.add_argument('bill_id', nargs='?', default='hr187-119', help='Bill ID to fix (default: hr187-119)')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be changed without making changes')
    args = parser.parse_args()
    
    logger.info(f"Fixing date_introduced for {args.bill_id}")
    success = fix_bill_date_introduced(args.bill_id, dry_run=args.dry_run)
    
    if success:
        logger.info("✅ Fix completed successfully")
        sys.exit(0)
    else:
        logger.error("❌ Fix failed")
        sys.exit(1)

if __name__ == '__main__':
    main()
