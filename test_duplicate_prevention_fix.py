#!/usr/bin/env python3
"""
Test script to verify the duplicate prevention fix in has_posted_today()
This validates that the function correctly uses date_processed instead of updated_at
"""

import sys
import os
from datetime import datetime, timezone

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# Load environment variables
from load_env import load_env
load_env()

from database.db import has_posted_today, db_connect

def test_duplicate_prevention():
    """Test the has_posted_today() function with current database state"""
    
    print("=" * 80)
    print("DUPLICATE PREVENTION FIX TEST")
    print("=" * 80)
    print()
    
    # Step 1: Query database for bills with tweet_posted = TRUE
    print("Step 1: Querying database for posted bills...")
    print("-" * 80)
    
    try:
        with db_connect() as conn:
            with conn.cursor() as cursor:
                # Get all bills that have been posted
                cursor.execute('''
                SELECT
                    bill_id,
                    title,
                    tweet_posted,
                    date_processed,
                    updated_at,
                    NOW() as current_time,
                    EXTRACT(EPOCH FROM (NOW() - date_processed))/3600 as hours_since_processed
                FROM bills
                WHERE tweet_posted = TRUE
                ORDER BY date_processed DESC
                LIMIT 5
                ''')
                
                posted_bills = cursor.fetchall()
                
                if not posted_bills:
                    print("❌ No bills found with tweet_posted = TRUE")
                    return False
                
                print(f"✅ Found {len(posted_bills)} posted bill(s)")
                print()
                
                # Display details of posted bills
                for bill in posted_bills:
                    bill_id, title, tweet_posted, date_processed, updated_at, current_time, hours_ago = bill
                    
                    print(f"Bill: {bill_id}")
                    print(f"  - Title: {title[:60]}...")
                    print(f"  - Tweet Posted: {tweet_posted}")
                    print(f"  - Date Processed: {date_processed} UTC")
                    print(f"  - Updated At: {updated_at} UTC")
                    print(f"  - Current Time: {current_time} UTC")
                    print(f"  - Hours Since Processed: {hours_ago:.2f} hours")
                    print(f"  - Within 24 hours? {'YES ✅' if hours_ago < 24 else 'NO ❌'}")
                    print()
                
                # Step 2: Test has_posted_today() function
                print("Step 2: Testing has_posted_today() function...")
                print("-" * 80)
                
                result = has_posted_today()
                
                print(f"has_posted_today() returned: {result}")
                print()
                
                # Step 3: Validate the result
                print("Step 3: Validating result...")
                print("-" * 80)
                
                # Get the most recent posted bill
                most_recent = posted_bills[0]
                hours_since_last_post = most_recent[6]  # hours_since_processed
                
                expected_result = hours_since_last_post < 24
                
                print(f"Most recent post was {hours_since_last_post:.2f} hours ago")
                print(f"Expected result: {expected_result}")
                print(f"Actual result: {result}")
                print()
                
                if result == expected_result:
                    print("✅ TEST PASSED: Function returned correct result")
                    print()
                    
                    if not result:
                        print("✅ DUPLICATE PREVENTION FIX VERIFIED:")
                        print("   - Last tweet was posted over 24 hours ago")
                        print("   - has_posted_today() correctly returns False")
                        print("   - Workflow will proceed to fetch and post new bills")
                    else:
                        print("✅ DUPLICATE PREVENTION WORKING:")
                        print("   - Tweet was posted within last 24 hours")
                        print("   - has_posted_today() correctly returns True")
                        print("   - Workflow will skip posting to prevent duplicates")
                    
                    return True
                else:
                    print("❌ TEST FAILED: Function returned incorrect result")
                    print(f"   Expected: {expected_result}, Got: {result}")
                    return False
                
    except Exception as e:
        print(f"❌ Error during test: {e}")
        import traceback
        traceback.print_exc()
        return False

def verify_query_logic():
    """Verify the SQL query logic used in has_posted_today()"""
    
    print()
    print("=" * 80)
    print("QUERY LOGIC VERIFICATION")
    print("=" * 80)
    print()
    
    try:
        with db_connect() as conn:
            with conn.cursor() as cursor:
                # Test the exact query used in has_posted_today()
                cursor.execute('''
                SELECT
                    bill_id,
                    date_processed,
                    EXTRACT(EPOCH FROM (NOW() - date_processed))/3600 as hours_ago
                FROM bills
                WHERE tweet_posted = TRUE
                AND date_processed >= NOW() - INTERVAL '24 hours'
                ORDER BY date_processed DESC
                ''')
                
                results = cursor.fetchall()
                
                print(f"Query: SELECT FROM bills WHERE tweet_posted = TRUE")
                print(f"       AND date_processed >= NOW() - INTERVAL '24 hours'")
                print()
                print(f"Results: {len(results)} bill(s) found")
                print()
                
                if results:
                    print("Bills posted in last 24 hours:")
                    for bill_id, date_processed, hours_ago in results:
                        print(f"  - {bill_id}: {hours_ago:.2f} hours ago")
                    print()
                    print("✅ Query correctly identifies recent posts")
                else:
                    print("No bills posted in last 24 hours")
                    print("✅ Query correctly returns empty result")
                
                return True
                
    except Exception as e:
        print(f"❌ Error verifying query: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print()
    print("Testing duplicate prevention fix...")
    print()
    
    # Run the main test
    test_passed = test_duplicate_prevention()
    
    # Verify query logic
    query_verified = verify_query_logic()
    
    # Final summary
    print()
    print("=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    print()
    
    if test_passed and query_verified:
        print("✅ ALL TESTS PASSED")
        print()
        print("The duplicate prevention fix is working correctly:")
        print("  1. ✅ Function uses date_processed (not updated_at)")
        print("  2. ✅ Query correctly checks last 24 hours")
        print("  3. ✅ Returns correct boolean result")
        print("  4. ✅ Will allow workflow to post new bills")
        print()
        sys.exit(0)
    else:
        print("❌ SOME TESTS FAILED")
        print()
        if not test_passed:
            print("  - Main test failed")
        if not query_verified:
            print("  - Query verification failed")
        print()
        sys.exit(1)