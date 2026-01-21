#!/usr/bin/env python3
"""
Script to fix the status of HR4405-119 bill in the database.
"""

import sys
import os
import logging
from typing import List, Dict, Any
import json

# Ensure project root is on sys.path so the 'src' package can be imported when running from project root
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.database.db import init_db, normalize_bill_id, db_connect
from src.fetchers.feed_parser import scrape_bill_tracker
from src.load_env import load_env

# Configure logging
LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO').upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def generate_source_url(bill_id: str) -> str:
    """
    Generate the Congress.gov source URL for a bill.
    
    Args:
        bill_id: The bill ID (e.g., 'hr1234-119')
        
    Returns:
        The source URL for the bill page
    """
    # Parse bill_id to get congress, bill_type, and bill_number
    parts = bill_id.split('-')
    if len(parts) != 2:
        raise ValueError(f"Invalid bill_id format: {bill_id}")
    
    bill_info, congress = parts
    congress = str(congress)
    
    # Map bill types to full names for URL construction (order matters: longer prefixes first)
    bill_type_items = [
        ('sjres', 'senate-joint-resolution'),
        ('hjres', 'house-joint-resolution'),
        ('sconres', 'senate-concurrent-resolution'),
        ('hconres', 'house-concurrent-resolution'),
        ('sres', 'senate-resolution'),
        ('hres', 'house-resolution'),
        ('hr', 'house-bill'),
        ('s', 'senate-bill'),
    ]
    
    # Extract bill type and number (prefer longer prefixes first)
    for prefix, full_type in bill_type_items:
        if bill_info.startswith(prefix):
            bill_type_full = full_type
            bill_number = bill_info[len(prefix):]
            break
    else:
        # Default fallback
        bill_type_full = 'house-bill'
        bill_number = bill_info
    
    return f"https://www.congress.gov/bill/{congress}th-congress/{bill_type_full}/{bill_number}"

def derive_normalized_status_from_tracker(tracker_data: List[Dict[str, Any]]) -> str:
    """
    Derive normalized status from tracker data.
    
    Args:
        tracker_data: List of tracker steps
        
    Returns:
        Normalized status string
    """
    normalized_status = "unknown"
    if tracker_data:
        if isinstance(tracker_data, list):
            # List of steps with selected flag
            # Find the LAST step that is selected (most recent status)
            for step in reversed(tracker_data):
                if step.get("selected", False):
                    normalized_status = step["name"].lower().replace(" ", "_")
                    break
        elif isinstance(tracker_data, dict):
            # Dict with steps in 'steps' key
            steps = tracker_data.get("steps", [])
            # Find the LAST step that is selected (most recent status)
            for step in reversed(steps):
                if step.get("selected", False):
                    normalized_status = step["name"].lower().replace(" ", "_")
                    break
    return normalized_status

def update_bill_fields(bill_id: str, update_data: Dict[str, Any]) -> bool:
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

def fix_hr4405_status(dry_run: bool = True) -> None:
    """
    Fix the status of HR4405-119 bill.
    
    Args:
        dry_run: If True, only print what would be updated without making changes
    """
    logger.info(f"🔧 Starting HR4405-119 status fix script (dry_run: {dry_run})")
    
    # Load environment variables from .env to ensure DATABASE_URL is available
    load_env()
    
    # Initialize database
    init_db()
    
    bill_id = "hr4405-119"
    source_url = generate_source_url(bill_id)
    
    logger.info(f"🔗 Source URL for {bill_id}: {source_url}")
    
    try:
        # Scrape the current tracker data
        logger.info(f"🌐 Scraping tracker for {bill_id} from {source_url}")
        tracker_data = scrape_bill_tracker(source_url, force_scrape=True)
        
        if not tracker_data:
            logger.warning(f"⚠️ Could not scrape tracker for {bill_id}")
            return
        
        logger.info(f"✅ Scraped tracker data: {tracker_data}")
        
        # Derive the correct normalized status
        normalized_status = derive_normalized_status_from_tracker(tracker_data)
        logger.info(f"✅ Derived status for {bill_id}: {normalized_status}")
        
        # Prepare update data
        update_data = {
            'tracker_raw': json.dumps(tracker_data),
            'normalized_status': normalized_status
        }
        
        # Update the database record
        if dry_run:
            logger.info(f"📝 [DRY-RUN] Would update {bill_id} with status '{normalized_status}'")
            logger.info(f"📝 [DRY-RUN] Tracker data: {tracker_data}")
        else:
            try:
                logger.info(f"💾 Updating database for {bill_id} with status '{normalized_status}'")
                success = update_bill_fields(bill_id, update_data)
                if success:
                    logger.info(f"✅ Successfully updated {bill_id}")
                else:
                    logger.error(f"❌ Update returned False for {bill_id}")
            except Exception as e:
                logger.error(f"❌ Failed to update {bill_id}: {e}")
    
    except Exception as e:
        logger.error(f"❌ Error processing {bill_id}: {e}")

def main():
    """Main entry point for the script."""
    import argparse
    parser = argparse.ArgumentParser(description="Fix HR4405-119 bill status")
    parser.add_argument('--live', action='store_true', 
                       help='Actually update the database (default is dry-run)')
    
    args = parser.parse_args()
    
    fix_hr4405_status(dry_run=not args.live)

if __name__ == "__main__":
    main()