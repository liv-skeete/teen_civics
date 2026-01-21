#!/usr/bin/env python3
"""
Standalone script to correct bill statuses by re-scraping data from Congress.gov.

This script provides a robust, production-ready solution for identifying and
correcting outdated or incorrect bill statuses in the database. It leverages the
refactored scraping logic from `congress_fetcher.py` and offers detailed
logging, reporting, and flexible targeting options.

Key Features:
- Targets bills by specific IDs, an entire Congress session, or all bills.
- Primary scraping via Playwright for full accuracy.
- Fallback scraping using BeautifulSoup for resilience.
- Dry-run mode for safe, no-change reporting.
- Rate-limiting to respect Congress.gov's servers.
- Detailed logging and summary reporting of corrections.
- Atomic database updates to ensure data integrity.
"""

import argparse
import logging
import sys
import time
import json
from typing import Dict, Any, Optional, List

# Ensure the script can find modules in the 'src' directory
sys.path.append(sys.path[0] + "/..")

from src.database.db import get_all_bills, get_bill_by_id, update_bill, get_bills_by_congress
from src.fetchers.congress_fetcher import scrape_bill_tracker, download_bill_text

# --- Configuration ---
# Rate-limiting: seconds to wait between requests to Congress.gov
RATE_LIMIT_SECONDS = 2.0

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


# --- Database Functions ---
def load_bills_from_storage(
    bill_ids: Optional[List[str]] = None, congress: Optional[int] = None
) -> List[Dict[str, Any]]:
    """
    Load bills from the database based on specified criteria.

    Args:
        bill_ids: A list of specific bill IDs to load.
        congress: A specific Congress session to load all bills from.

    Returns:
        A list of bill dictionaries from the database.
    """
    if bill_ids:
        logger.info(f"Loading {len(bill_ids)} specific bills from the database...")
        bills = [get_bill_by_id(bill_id) for bill_id in bill_ids]
        return [bill for bill in bills if bill]  # Filter out any None results
    elif congress:
        logger.info(f"Loading all bills for the {congress}th Congress...")
        return get_bills_by_congress(str(congress), limit=10000)
    else:
        logger.info("Loading all bills from the database...")
        return get_all_bills(limit=10000)  # Adjust limit as needed


def save_bill_to_storage(
    bill_id: str, corrected_status: str, corrected_tracker: List[Dict[str, Any]]
) -> bool:
    """
    Save the corrected bill status and tracker to the database.

    Args:
        bill_id: The ID of the bill to update.
        corrected_status: The new, corrected status.
        corrected_tracker: The new, corrected tracker data.

    Returns:
        True if the update was successful, False otherwise.
    """
    update_data = {
        "status": corrected_status,
        "tracker_raw": json.dumps(corrected_tracker),
        "normalized_status": corrected_status.lower().replace(" ", "_"),
    }
    logger.debug(f"Saving bill {bill_id} with data: {update_data}")
    return update_bill(bill_id, update_data)


# --- Scraping Functions ---
def scrape_current_status(
    bill: Dict[str, Any]
) -> Optional[tuple[str, List[Dict[str, Any]]]]:
    """
    Scrape the current status and tracker for a bill from Congress.gov.

    Uses Playwright as the primary method and falls back to BeautifulSoup.

    Args:
        bill: The bill dictionary, containing at least 'source_url'.

    Returns:
        A tuple of (status, tracker) if successful, otherwise None.
    """
    source_url = bill.get("source_url")
    if not source_url:
        logger.warning(f"Bill {bill.get('bill_id')} has no source URL, skipping.")
        return None

    try:
        # Primary method: Playwright-based scraping
        logger.debug(f"Attempting to scrape {source_url} with Playwright...")
        tracker = scrape_bill_tracker(source_url)
        if tracker:
            # Find the selected status (the current status)
            latest_status = "unknown"
            for step in reversed(tracker):
                if step.get("selected", False):
                    latest_status = step.get("name", "unknown")
                    break
            
            logger.debug(f"Playwright success for {bill.get('bill_id')}: {latest_status}")
            return latest_status, tracker
    except Exception as e:
        logger.warning(
            f"Playwright scraping failed for {source_url}: {e}. Trying fallback."
        )

    try:
        # Fallback method: BeautifulSoup-based scraping
        logger.debug(f"Attempting to scrape {source_url} with BeautifulSoup...")
        # The `download_bill_text` function now contains the BS parsing logic
        bill_data = download_bill_text(source_url)
        if bill_data and bill_data.get("tracker"):
            tracker = bill_data["tracker"]
            # Find the selected status (the current status)
            latest_status = "unknown"
            for step in reversed(tracker):
                if step.get("selected", False):
                    latest_status = step.get("name", "unknown")
                    break
                    
            logger.debug(f"BeautifulSoup success for {bill.get('bill_id')}: {latest_status}")
            return latest_status, tracker
    except Exception as e:
        logger.error(f"BeautifulSoup fallback also failed for {source_url}: {e}")

    return None


# --- Main Execution Logic ---
def main():
    """
    Main function to execute the bill status correction process.
    """
    parser = argparse.ArgumentParser(
        description="Correct bill statuses by re-scraping Congress.gov."
    )
    parser.add_argument(
        "--bill-ids",
        nargs="+",
        help="A space-separated list of specific bill IDs to check.",
    )
    parser.add_argument(
        "--congress",
        type=int,
        help="The Congress session number to check (e.g., 118).",
    )
    parser.add_argument(
        "--all", action="store_true", help="Check all bills in the database."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run the script without making any changes to the database.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-scraping even if the status appears correct.",
    )
    args = parser.parse_args()

    if not any([args.bill_ids, args.congress, args.all]):
        parser.error("You must specify which bills to process: --bill-ids, --congress, or --all.")
        return

    logger.info("--- Starting Bill Status Correction Script ---")
    if args.dry_run:
        logger.info("*** DRY RUN MODE ENABLED: No changes will be saved. ***")

    # Load bills from the database
    bills_to_check = load_bills_from_storage(args.bill_ids, args.congress)
    if not bills_to_check:
        logger.info("No bills found for the specified criteria. Exiting.")
        return

    # --- Processing Loop ---
    total_bills = len(bills_to_check)
    corrected_count = 0
    error_count = 0
    report = []

    for i, bill in enumerate(bills_to_check):
        bill_id = bill.get("bill_id")
        old_status = bill.get("status", "N/A")
        logger.info(
            f"({i+1}/{total_bills}) Processing {bill_id} | Current Status: {old_status}"
        )

        # Rate-limiting
        time.sleep(RATE_LIMIT_SECONDS)

        # Scrape the current status
        scrape_result = scrape_current_status(bill)
        if not scrape_result:
            error_count += 1
            report.append(
                {"bill_id": bill_id, "status": "ERROR", "details": "Scraping failed"}
            )
            continue

        new_status, new_tracker = scrape_result

        # Compare and decide whether to update
        if new_status != old_status or args.force:
            logger.info(f"  -> Status mismatch for {bill_id}: DB='{old_status}', Scraped='{new_status}'")
            report.append(
                {
                    "bill_id": bill_id,
                    "status": "CORRECTED",
                    "old_status": old_status,
                    "new_status": new_status,
                }
            )

            if not args.dry_run:
                if save_bill_to_storage(bill_id, new_status, new_tracker):
                    logger.info(f"  ✅ Successfully updated {bill_id} in the database.")
                    corrected_count += 1
                else:
                    logger.error(f"  ❌ Failed to update {bill_id} in the database.")
                    error_count += 1
        else:
            logger.info(f"  -> Status for {bill_id} is already correct.")
            report.append({"bill_id": bill_id, "status": "OK"})

    # --- Final Report ---
    logger.info("\n--- Correction Script Finished ---")
    logger.info(f"Total Bills Processed: {total_bills}")
    logger.info(f"Bills Corrected: {corrected_count}")
    logger.info(f"Errors Encountered: {error_count}")
    logger.info("---------------------------------")
    # Optional: Print detailed report
    # for item in report:
    #     logger.info(f"  - {item['bill_id']}: {item['status']}")


if __name__ == "__main__":
    main()