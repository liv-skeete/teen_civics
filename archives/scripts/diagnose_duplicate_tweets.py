#!/usr/bin/env python3
"""
Diagnostic script to investigate duplicate tweet issues.
This script adds detailed logging to track the bill selection and update process.
"""

import os
import sys
import logging
from datetime import datetime

# Configure detailed logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s.%(msecs)03d - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '.'))

def diagnose_duplicate_issue():
    """
    Run diagnostic checks to identify the duplicate tweet issue.
    """
    logger.info("=" * 80)
    logger.info("DUPLICATE TWEET DIAGNOSTIC SCRIPT")
    logger.info("=" * 80)
    
    try:
        from src.database.db import (
            bill_already_posted, 
            get_bill_by_id, 
            get_most_recent_unposted_bill,
            get_all_bills,
            init_db,
            normalize_bill_id
        )
        
        # Initialize database
        logger.info("Initializing database...")
        init_db()
        
        # Get all bills from database
        logger.info("\n" + "=" * 80)
        logger.info("STEP 1: Fetching bills from database")
        logger.info("=" * 80)
        bills = get_all_bills(limit=10)
        logger.info(f"Retrieved {len(bills)} bills from database")
        
        # Check each bill's status
        logger.info("\n" + "=" * 80)
        logger.info("STEP 2: Checking bill posting status")
        logger.info("=" * 80)
        
        for i, bill in enumerate(bills[:5], 1):  # Check first 5
            bill_id = bill.get("bill_id", "unknown")
            
            logger.info(f"\n--- Bill {i}: {bill_id} ---")
            
            # Check if already posted
            timestamp_before = datetime.now().isoformat()
            is_posted = bill_already_posted(bill_id)
            timestamp_after = datetime.now().isoformat()
            
            logger.info(f"bill_already_posted() called at: {timestamp_before}")
            logger.info(f"bill_already_posted() returned: {is_posted}")
            logger.info(f"bill_already_posted() completed at: {timestamp_after}")
            
            # Compare with actual database values
            logger.info(f"Database values:")
            logger.info(f"  - tweet_posted: {bill.get('tweet_posted')}")
            logger.info(f"  - tweet_url: {bill.get('tweet_url')}")
            logger.info(f"  - date_processed: {bill.get('date_processed')}")
            
            # Check for inconsistencies
            if is_posted != bill.get('tweet_posted'):
                logger.error(f"⚠️  INCONSISTENCY DETECTED!")
                logger.error(f"bill_already_posted() returned {is_posted} but tweet_posted={bill.get('tweet_posted')}")
        
        # Check for unposted bills
        logger.info("\n" + "=" * 80)
        logger.info("STEP 3: Checking for unposted bills in database")
        logger.info("=" * 80)
        
        unposted = get_most_recent_unposted_bill()
        if unposted:
            logger.info(f"Found unposted bill: {unposted['bill_id']}")
            logger.info(f"  - tweet_posted: {unposted.get('tweet_posted')}")
            logger.info(f"  - tweet_url: {unposted.get('tweet_url')}")
            logger.info(f"  - date_processed: {unposted.get('date_processed')}")
        else:
            logger.info("No unposted bills found in database")
        
        # Test race condition scenario
        logger.info("\n" + "=" * 80)
        logger.info("STEP 4: Simulating race condition scenario")
        logger.info("=" * 80)
        
        if bills:
            test_bill_id = bills[0].get("bill_id")
            logger.info(f"Testing with bill: {test_bill_id}")
            
            # Simulate two concurrent checks
            logger.info("\nSimulating Process A checking bill status...")
            check_a_time = datetime.now().isoformat()
            check_a_result = bill_already_posted(test_bill_id)
            logger.info(f"Process A at {check_a_time}: bill_already_posted() = {check_a_result}")
            
            logger.info("\nSimulating Process B checking bill status (concurrent)...")
            check_b_time = datetime.now().isoformat()
            check_b_result = bill_already_posted(test_bill_id)
            logger.info(f"Process B at {check_b_time}: bill_already_posted() = {check_b_result}")
            
            if check_a_result == check_b_result == False:
                logger.warning("⚠️  RACE CONDITION POSSIBLE!")
                logger.warning("Both processes would select the same bill for posting!")
                logger.warning("This is the likely cause of duplicate tweets!")
            else:
                logger.info("✓ No race condition in this scenario")
        
        # Check for bills with tweet_posted=False but tweet_url set
        logger.info("\n" + "=" * 80)
        logger.info("STEP 5: Checking for inconsistent bill states")
        logger.info("=" * 80)
        
        inconsistent_bills = [
            b for b in bills 
            if (not b.get('tweet_posted') and b.get('tweet_url')) or
               (b.get('tweet_posted') and not b.get('tweet_url'))
        ]
        
        if inconsistent_bills:
            logger.warning(f"⚠️  Found {len(inconsistent_bills)} bills with inconsistent state:")
            for bill in inconsistent_bills:
                logger.warning(f"  - {bill['bill_id']}: tweet_posted={bill.get('tweet_posted')}, tweet_url={bill.get('tweet_url')}")
        else:
            logger.info("✓ No inconsistent bill states found")
        
        logger.info("\n" + "=" * 80)
        logger.info("DIAGNOSTIC COMPLETE")
        logger.info("=" * 80)
        logger.info("\nSUMMARY OF FINDINGS:")
        logger.info(f"- Total bills checked: {len(bills)}")
        logger.info(f"- Unposted bills: {1 if unposted else 0}")
        logger.info(f"- Inconsistent states: {len(inconsistent_bills)}")
        
    except Exception as e:
        logger.error(f"Error during diagnosis: {e}", exc_info=True)
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(diagnose_duplicate_issue())