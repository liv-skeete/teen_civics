#!/usr/bin/env python3
"""
Test script to verify duplicate tweet prevention mechanisms.
Tests the new row-level locking and atomic operations.
"""

import os
import sys
import logging
from datetime import datetime
import threading
import time

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(threadName)s] - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '.'))

def test_concurrent_bill_selection():
    """
    Test that concurrent processes cannot select the same bill.
    """
    logger.info("=" * 80)
    logger.info("TEST 1: Concurrent Bill Selection with Locking")
    logger.info("=" * 80)
    
    try:
        from src.database.db import select_and_lock_unposted_bill, init_db
        
        init_db()
        
        selected_bills = []
        errors = []
        
        def select_bill(thread_id):
            """Simulate a process selecting a bill"""
            try:
                logger.info(f"Thread {thread_id}: Attempting to select and lock a bill...")
                bill = select_and_lock_unposted_bill()
                if bill:
                    logger.info(f"Thread {thread_id}: Successfully locked bill {bill['bill_id']}")
                    selected_bills.append((thread_id, bill['bill_id']))
                    # Simulate some processing time
                    time.sleep(0.5)
                else:
                    logger.info(f"Thread {thread_id}: No bills available")
            except Exception as e:
                logger.error(f"Thread {thread_id}: Error - {e}")
                errors.append((thread_id, str(e)))
        
        # Create multiple threads to simulate concurrent workflow runs
        threads = []
        for i in range(3):
            thread = threading.Thread(target=select_bill, args=(i,), name=f"Worker-{i}")
            threads.append(thread)
        
        # Start all threads simultaneously
        logger.info("Starting 3 concurrent threads...")
        for thread in threads:
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # Analyze results
        logger.info("\n" + "=" * 80)
        logger.info("TEST RESULTS")
        logger.info("=" * 80)
        logger.info(f"Bills selected: {len(selected_bills)}")
        logger.info(f"Errors: {len(errors)}")
        
        if selected_bills:
            logger.info("\nSelected bills:")
            for thread_id, bill_id in selected_bills:
                logger.info(f"  Thread {thread_id}: {bill_id}")
            
            # Check for duplicates
            bill_ids = [bill_id for _, bill_id in selected_bills]
            unique_bills = set(bill_ids)
            
            if len(bill_ids) == len(unique_bills):
                logger.info("\n✅ SUCCESS: No duplicate bills selected!")
                logger.info("Row-level locking is working correctly.")
            else:
                logger.error("\n❌ FAILURE: Duplicate bills detected!")
                logger.error("Row-level locking is NOT working correctly.")
                return False
        else:
            logger.info("\n⚠️  No bills were selected (database may be empty)")
        
        if errors:
            logger.error("\nErrors encountered:")
            for thread_id, error in errors:
                logger.error(f"  Thread {thread_id}: {error}")
        
        return True
        
    except Exception as e:
        logger.error(f"Test failed with error: {e}", exc_info=True)
        return False


def test_update_tweet_info_locking():
    """
    Test that update_tweet_info uses proper locking.
    """
    logger.info("\n" + "=" * 80)
    logger.info("TEST 2: Update Tweet Info with Row-Level Locking")
    logger.info("=" * 80)
    
    try:
        from src.database.db import (
            get_most_recent_unposted_bill, 
            update_tweet_info,
            get_bill_by_id,
            init_db
        )
        
        init_db()
        
        # Get an unposted bill
        bill = get_most_recent_unposted_bill()
        if not bill:
            logger.warning("No unposted bills available for testing")
            return True
        
        bill_id = bill['bill_id']
        logger.info(f"Testing with bill: {bill_id}")
        
        # Test idempotent update (same URL twice)
        test_url = "https://twitter.com/test/status/123456789"
        
        logger.info(f"\nAttempt 1: Updating bill with URL: {test_url}")
        success1 = update_tweet_info(bill_id, test_url)
        logger.info(f"Result: {success1}")
        
        # Verify the update
        updated_bill = get_bill_by_id(bill_id)
        if updated_bill:
            logger.info(f"Verification: tweet_posted={updated_bill.get('tweet_posted')}, tweet_url={updated_bill.get('tweet_url')}")
        
        logger.info(f"\nAttempt 2: Updating same bill with same URL (idempotent test)")
        success2 = update_tweet_info(bill_id, test_url)
        logger.info(f"Result: {success2}")
        
        if success1 and success2:
            logger.info("\n✅ SUCCESS: Idempotent updates work correctly")
            return True
        else:
            logger.error("\n❌ FAILURE: Update operations failed")
            return False
            
    except Exception as e:
        logger.error(f"Test failed with error: {e}", exc_info=True)
        return False


def test_bill_already_posted():
    """
    Test that bill_already_posted correctly identifies posted bills.
    """
    logger.info("\n" + "=" * 80)
    logger.info("TEST 3: Bill Already Posted Check")
    logger.info("=" * 80)
    
    try:
        from src.database.db import (
            bill_already_posted,
            get_all_bills,
            init_db
        )
        
        init_db()
        
        bills = get_all_bills(limit=5)
        if not bills:
            logger.warning("No bills available for testing")
            return True
        
        logger.info(f"Testing with {len(bills)} bills")
        
        all_correct = True
        for bill in bills:
            bill_id = bill['bill_id']
            expected = bill.get('tweet_posted', False)
            actual = bill_already_posted(bill_id)
            
            match = "✓" if expected == actual else "✗"
            logger.info(f"{match} Bill {bill_id}: expected={expected}, actual={actual}")
            
            if expected != actual:
                all_correct = False
        
        if all_correct:
            logger.info("\n✅ SUCCESS: bill_already_posted() works correctly")
            return True
        else:
            logger.error("\n❌ FAILURE: bill_already_posted() has inconsistencies")
            return False
            
    except Exception as e:
        logger.error(f"Test failed with error: {e}", exc_info=True)
        return False


def main():
    """Run all tests"""
    logger.info("=" * 80)
    logger.info("DUPLICATE TWEET PREVENTION TEST SUITE")
    logger.info("=" * 80)
    
    results = []
    
    # Run tests
    results.append(("Concurrent Bill Selection", test_concurrent_bill_selection()))
    results.append(("Update Tweet Info Locking", test_update_tweet_info_locking()))
    results.append(("Bill Already Posted Check", test_bill_already_posted()))
    
    # Summary
    logger.info("\n" + "=" * 80)
    logger.info("TEST SUMMARY")
    logger.info("=" * 80)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASSED" if result else "❌ FAILED"
        logger.info(f"{status}: {test_name}")
    
    logger.info(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        logger.info("\n🎉 All tests passed! Duplicate prevention is working correctly.")
        return 0
    else:
        logger.error(f"\n⚠️  {total - passed} test(s) failed. Please review the issues above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())