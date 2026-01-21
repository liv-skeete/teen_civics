#!/usr/bin/env python3
"""
Script to regenerate summaries for a specific list of bills.
"""

import os
import sys
import logging
import argparse
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Load environment variables
from dotenv import load_dotenv
load_dotenv(project_root / '.env')

from src.database.db_utils import get_bill_by_id, update_bill_summaries, update_bill_full_text
from src.fetchers.congress_fetcher import fetch_bill_text_from_api
from src.processors.summarizer import summarize_bill_enhanced

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def regenerate_bill(bill_id: str):
    logger.info(f"Starting reprocessing for bill: {bill_id}")
    
    bill = get_bill_by_id(bill_id)
    
    if not bill:
        logger.error(f"Bill with id '{bill_id}' not found.")
        return

    logger.info(f"Reprocessing bill {bill['bill_id']}...")

    # Extract congress, bill_type, and bill_number from bill_id
    parts = bill_id.replace('hr', '').replace('s', '').split('-')
    bill_number = parts[0]
    congress = parts[1]
    bill_type = 'hr' if 'hr' in bill_id else 's'

    # Try to fetch the full text using the API
    api_key = os.environ.get('CONGRESS_API_KEY')
    if not api_key:
        logger.error("CONGRESS_API_KEY environment variable not set.")
        return

    logger.info("Fetching full bill text from Congress.gov API...")
    try:
        full_text, text_format = fetch_bill_text_from_api(
            congress=congress,
            bill_type=bill_type,
            bill_number=bill_number,
            api_key=api_key
        )
        
        if full_text and len(full_text.strip()) > 100:
            logger.info(f"Successfully fetched bill text ({len(full_text)} characters)")
            bill['full_text'] = full_text
            bill['text_format'] = text_format
            update_bill_full_text(bill_id, full_text, text_format)
        else:
            logger.error(f"Failed to fetch valid bill text for {bill_id}. Skipping summary generation.")
            return
    except Exception as e:
        logger.error(f"Error fetching bill text for {bill_id}: {e}")
        return

    # Generate new summary
    new_summaries = summarize_bill_enhanced(bill)
    
    if not new_summaries:
        logger.error(f"Failed to generate summary for bill {bill['bill_id']}")
        return
        
    # Update the database
    update_bill_summaries(
        bill['bill_id'],
        new_summaries.get('overview'),
        new_summaries.get('detailed'),
        new_summaries.get('tweet'),
        new_summaries.get('term_dictionary')
    )
    
    logger.info(f"Successfully reprocessed bill {bill['bill_id']}")

def main(bill_ids: list[str]):
    for bill_id in bill_ids:
        regenerate_bill(bill_id)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Reprocess summaries for a list of bills.")
    parser.add_argument("bill_ids", nargs='+', help="The IDs of the bills to reprocess (e.g., hr4550-119 s976-119).")
    args = parser.parse_args()
    
    main(args.bill_ids)