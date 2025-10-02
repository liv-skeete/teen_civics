import os
import sys
import logging

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from dotenv import load_dotenv
load_dotenv()

from src.database.db import get_latest_bill, update_bill_summaries
from src.processors.summarizer import summarize_bill_enhanced

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def reprocess_latest_bill():
    """
    Fetches the latest bill from the database, re-summarizes it, and updates the database with the new summary.
    """
    logger.info("Fetching the latest bill from the database...")
    latest_bill = get_latest_bill()

    if not latest_bill:
        logger.error("No bills found in the database.")
        return

    logger.info(f"Reprocessing bill: {latest_bill['bill_id']}")

    # Re-summarize the bill
    summary = summarize_bill_enhanced(latest_bill)

    # Update the bill in the database
    update_bill_summaries(
        bill_id=latest_bill['bill_id'],
        summary_overview=summary.get("overview", ""),
        summary_detailed=summary.get("detailed", ""),
        summary_long=summary.get("long", ""),
        term_dictionary=summary.get("term_dictionary", "")
    )

    logger.info(f"Successfully reprocessed bill: {latest_bill['bill_id']}")

if __name__ == "__main__":
    reprocess_latest_bill()