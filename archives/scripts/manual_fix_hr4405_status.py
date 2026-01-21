#!/usr/bin/env python3
"""
Script to manually fix the status of HR4405-119 bill in the database.
"""

import sys
import os
import logging
import json

# Ensure project root is on sys.path so the 'src' package can be imported when running from project root
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.database.db import init_db, normalize_bill_id, db_connect
from src.load_env import load_env

# Configure logging
LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO').upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def update_bill_fields(bill_id: str, update_data: dict) -> bool:
    """
    Update bill fields in the database. Only whitelisted fields are updated.

    Args:
        bill_id: The bill identifier to update
        update_data: Dict containing fields to update (e.g., 'tracker_raw', 'normalized_status', optional 'status')

    Returns:
        True if one row was updated; False otherwise
    """
    try:
        normalized_id = normalize_bill_id(bill_id)
        allowed_fields = {'tracker_raw', 'normalized_status', 'status'}
        fields = [k for k in update_data.keys() if k in allowed_fields]
        if not fields:
            logger.warning(f"No valid fields to update for {bill_id}; allowed: {sorted(allowed_fields)}")
            return False

        set_clause = ', '.join(f"{field} = %s" for field in fields)
        values = [update_data[field] for field in fields]

        with db_connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(f"""
                    UPDATE bills
                    SET {set_clause}
                    WHERE bill_id = %s
                """, (*values, normalized_id))
                if cursor.rowcount == 1:
                    return True
                else:
                    logger.error(f"Bill {normalized_id} not found; no rows updated")
                    return False
    except Exception as e:
        logger.error(f"Error updating bill {bill_id}: {e}")
        return False

def manual_fix_hr4405_status() -> None:
    """
    Manually fix the status of HR4405-119 bill with the correct tracker data.
    """
    logger.info("🔧 Starting manual HR4405-119 status fix")
    
    # Load environment variables from .env to ensure DATABASE_URL is available
    load_env()
    
    # Initialize database
    init_db()
    
    bill_id = "hr4405-119"
    
    # Correct tracker data based on the HTML provided
    tracker_data = [
        {
            "name": "Introduced",
            "selected": False
        },
        {
            "name": "Passed House",
            "selected": False
        },
        {
            "name": "Passed Senate",
            "selected": False
        },
        {
            "name": "To President",
            "selected": False
        },
        {
            "name": "Became Law",
            "selected": True
        }
    ]
    
    # Derive the correct normalized status
    normalized_status = "became_law"
    
    # Prepare update data
    update_data = {
        'tracker_raw': json.dumps(tracker_data),
        'normalized_status': normalized_status
    }
    
    try:
        logger.info(f"💾 Updating database for {bill_id} with status '{normalized_status}'")
        success = update_bill_fields(bill_id, update_data)
        if success:
            logger.info(f"✅ Successfully updated {bill_id}")
        else:
            logger.error(f"❌ Update returned False for {bill_id}")
    except Exception as e:
        logger.error(f"❌ Failed to update {bill_id}: {e}")

if __name__ == "__main__":
    manual_fix_hr4405_status()