#!/usr/bin/env python3
"""
A utility script to delete a specific bill from the database.
"""

import os
import sys
import logging
import argparse

# Add src to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.load_env import load_env
from src.database.connection import postgres_connect
from src.database.db import normalize_bill_id

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def delete_bill(bill_id: str) -> bool:
    """
    Deletes a bill from the database by its bill_id.
    """
    normalized_id = normalize_bill_id(bill_id)
    logger.info(f"Attempting to delete bill: {normalized_id}")

    try:
        with postgres_connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute("DELETE FROM bills WHERE bill_id = %s", (normalized_id,))
                if cursor.rowcount == 1:
                    logger.info(f"✅ Successfully deleted bill {normalized_id} from the database.")
                    return True
                else:
                    logger.warning(f"⚠️ Bill {normalized_id} not found in the database. Nothing to delete.")
                    return False
    except Exception as e:
        logger.error(f"❌ An error occurred while trying to delete bill {normalized_id}: {e}")
        return False

if __name__ == "__main__":
    load_env()

    parser = argparse.ArgumentParser(description="Delete a bill from the database.")
    parser.add_argument("bill_id", type=str, help="The ID of the bill to delete (e.g., 'hr5811-119').")
    args = parser.parse_args()

    if delete_bill(args.bill_id):
        sys.exit(0)
    else:
        sys.exit(1)