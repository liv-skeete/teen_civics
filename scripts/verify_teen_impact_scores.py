#!/usr/bin/env python3
"""
This script verifies the consistency of teen impact scores in the database.

It checks all bills and compares the 'teen_impact_score' field with the score
mentioned in the 'summary_detailed' field. It then generates a report of any
mismatches found.
"""

import os
import sys
import re
import logging
import argparse
from typing import Optional, Tuple

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)

# Ensure the script can find the src directory
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

try:
    from src.database.db import get_all_bills, db_connect
    from src.load_env import load_env
    load_env()
except ImportError as e:
    logging.error(f"Error importing database modules: {e}")
    sys.exit(1)

def update_bill_score(bill_id: str, new_score: int) -> bool:
    """
    Updates the teen_impact_score for a specific bill.
    """
    try:
        with db_connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "UPDATE bills SET teen_impact_score = %s WHERE bill_id = %s",
                    (new_score, bill_id),
                )
        logging.info(f"Successfully updated bill {bill_id} to score {new_score}.")
        return True
    except Exception as e:
        logging.error(f"Error updating bill {bill_id}: {e}")
        return False

def extract_score_from_summary(summary: Optional[str]) -> Optional[int]:
    """
    Extracts the teen impact score from the detailed summary text.
    The summary format is expected to contain a line like 'Teen Impact Score: X/10'.
    """
    if not summary:
        return None
    
    match = re.search(r"Teen Impact Score:\s*(\d+)/10", summary, re.IGNORECASE)
    if match:
        return int(match.group(1))
    
    return None

def verify_scores():
    """
    Fetches all bills and verifies the consistency of teen impact scores.
    """
    logging.info("Starting teen impact score verification...")
    
    try:
        all_bills = get_all_bills(limit=10000)  # A high limit to get all bills
    except Exception as e:
        logging.error(f"Failed to retrieve bills from the database: {e}")
        return

    mismatches = []
    bills_processed = 0

    for bill in all_bills:
        bills_processed += 1
        bill_id = bill.get("bill_id")
        db_score = bill.get("teen_impact_score")
        summary_detailed = bill.get("summary_detailed")

        if summary_detailed is None:
            logging.warning(f"Bill {bill_id} has no detailed summary. Skipping.")
            continue

        summary_score = extract_score_from_summary(summary_detailed)

        if summary_score is None:
            logging.warning(f"Could not extract score from summary for bill {bill_id}.")
            continue

        if db_score != summary_score:
            mismatches.append({
                "bill_id": bill_id,
                "db_score": db_score,
                "summary_score": summary_score,
            })
            logging.warning(
                f"MISMATCH FOUND for bill {bill_id}: "
                f"DB score is {db_score}, but summary score is {summary_score}."
            )

    logging.info(f"Processed {bills_processed} bills.")
    
    if mismatches:
        logging.info("\n--- Mismatch Report ---")
        for mismatch in mismatches:
            logging.info(
                f"  Bill ID: {mismatch['bill_id']}, "
                f"DB Score: {mismatch['db_score']}, "
                f"Summary Score: {mismatch['summary_score']}"
            )
        logging.info(f"Total mismatches found: {len(mismatches)}")
        
        if args.fix:
            logging.info("\n--- Applying fixes ---")
            for mismatch in mismatches:
                update_bill_score(mismatch["bill_id"], mismatch["summary_score"])
            logging.info("Finished applying fixes.")
            
    else:
        logging.info("No teen impact score mismatches found. All scores are consistent.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Verify and optionally correct teen impact scores in the database."
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="If set, the script will attempt to fix the found mismatches.",
    )
    args = parser.parse_args()
    
    verify_scores()