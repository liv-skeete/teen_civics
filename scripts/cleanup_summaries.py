#!/usr/bin/env python3
"""
One-time script to remove HTML <br> tags from bill summaries in the database.
"""

import os
import sys
import logging

# Add project root to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.database.db import get_all_bills, update_bill_summaries

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def cleanup_summaries():
    """
    Iterates through all bills and removes <br> tags from summary fields.
    """
    logger.info("Starting summary cleanup process...")
    
    try:
        all_bills = get_all_bills(limit=10000)  # Get all bills
        updated_count = 0

        for bill in all_bills:
            bill_id = bill.get("bill_id")
            updates = {}
            
            # Fields to check for <br> tags
            summary_fields = ["summary_long", "summary_overview", "summary_detailed"]
            
            for field in summary_fields:
                content = bill.get(field)
                if content and "<br>" in content:
                    updates[field] = content.replace("<br>", "")
            
            if updates:
                logger.info(f"Updating bill {bill_id} with cleaned summaries.")
                update_bill_summaries(bill_id=bill_id, **updates)
                updated_count += 1
                
        logger.info(f"Summary cleanup complete. Updated {updated_count} bills.")

    except Exception as e:
        logger.error(f"An error occurred during summary cleanup: {e}")

if __name__ == "__main__":
    cleanup_summaries()