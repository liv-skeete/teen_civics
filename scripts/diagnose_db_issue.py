#!/usr/bin/env python3
"""
Diagnostic script to investigate database connection and data issues.
"""

import os
import sys
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def test_connection():
    """Test basic database connection"""
    print("=" * 60)
    print("STEP 1: Testing Database Connection")
    print("=" * 60)
    
    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        print("❌ ERROR: DATABASE_URL not found in environment")
        return False
    
    print(f"✓ DATABASE_URL found: {database_url[:50]}...")
    
    try:
        conn = psycopg2.connect(database_url)
        print("✓ Successfully connected to PostgreSQL database")
        
        # Test with a simple query
        with conn.cursor() as cursor:
            cursor.execute('SELECT version()')
            version = cursor.fetchone()[0]
            print(f"✓ PostgreSQL version: {version[:80]}...")
        
        conn.close()
        return True
    except psycopg2.OperationalError as e:
        print(f"❌ Connection failed: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

def check_tables():
    """Check if bills table exists"""
    print("\n" + "=" * 60)
    print("STEP 2: Checking Database Tables")
    print("=" * 60)
    
    database_url = os.environ.get('DATABASE_URL')
    try:
        conn = psycopg2.connect(database_url)
        with conn.cursor() as cursor:
            # Check if bills table exists
            cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'bills'
                )
            """)
            table_exists = cursor.fetchone()[0]
            
            if table_exists:
                print("✓ 'bills' table exists")
            else:
                print("❌ 'bills' table does NOT exist")
                conn.close()
                return False
            
            # Get table schema
            cursor.execute("""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name = 'bills'
                ORDER BY ordinal_position
            """)
            columns = cursor.fetchall()
            print(f"\n✓ Table has {len(columns)} columns:")
            for col_name, col_type in columns[:10]:  # Show first 10
                print(f"  - {col_name}: {col_type}")
            if len(columns) > 10:
                print(f"  ... and {len(columns) - 10} more columns")
        
        conn.close()
        return True
    except Exception as e:
        print(f"❌ Error checking tables: {e}")
        return False

def check_data():
    """Check if bills table has data"""
    print("\n" + "=" * 60)
    print("STEP 3: Checking Bills Data")
    print("=" * 60)
    
    database_url = os.environ.get('DATABASE_URL')
    try:
        conn = psycopg2.connect(database_url)
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
            # Count total bills
            cursor.execute("SELECT COUNT(*) FROM bills")
            total_count = cursor.fetchone()[0]
            print(f"Total bills in database: {total_count}")
            
            if total_count == 0:
                print("❌ No bills found in database!")
                conn.close()
                return False
            
            # Count tweeted bills
            cursor.execute("SELECT COUNT(*) FROM bills WHERE tweet_posted = TRUE")
            tweeted_count = cursor.fetchone()[0]
            print(f"Bills marked as tweeted: {tweeted_count}")
            
            # Count untweeted bills
            cursor.execute("SELECT COUNT(*) FROM bills WHERE tweet_posted = FALSE")
            untweeted_count = cursor.fetchone()[0]
            print(f"Bills NOT tweeted: {untweeted_count}")
            
            # Get latest tweeted bill (what homepage should show)
            print("\n--- Latest Tweeted Bill (for homepage) ---")
            cursor.execute("""
                SELECT bill_id, title, date_processed, tweet_posted, tweet_url
                FROM bills
                WHERE tweet_posted = TRUE
                ORDER BY date_processed DESC
                LIMIT 1
            """)
            latest_tweeted = cursor.fetchone()
            
            if latest_tweeted:
                print(f"✓ Found latest tweeted bill:")
                print(f"  Bill ID: {latest_tweeted['bill_id']}")
                print(f"  Title: {latest_tweeted['title'][:60]}...")
                print(f"  Date Processed: {latest_tweeted['date_processed']}")
                print(f"  Tweet URL: {latest_tweeted['tweet_url']}")
            else:
                print("❌ No tweeted bills found!")
            
            # Get all tweeted bills (what archive should show)
            print("\n--- All Tweeted Bills (for archive) ---")
            cursor.execute("""
                SELECT bill_id, title, date_processed
                FROM bills
                WHERE tweet_posted = TRUE
                ORDER BY date_processed DESC
                LIMIT 5
            """)
            all_tweeted = cursor.fetchall()
            
            if all_tweeted:
                print(f"✓ Found {len(all_tweeted)} tweeted bills (showing first 5):")
                for i, bill in enumerate(all_tweeted, 1):
                    print(f"  {i}. {bill['bill_id']}: {bill['title'][:50]}...")
            else:
                print("❌ No tweeted bills found for archive!")
            
            # Show sample of all bills
            print("\n--- Sample of All Bills (regardless of tweet status) ---")
            cursor.execute("""
                SELECT bill_id, title, tweet_posted, date_processed
                FROM bills
                ORDER BY date_processed DESC
                LIMIT 5
            """)
            sample_bills = cursor.fetchall()
            
            if sample_bills:
                print(f"✓ Sample of {len(sample_bills)} most recent bills:")
                for i, bill in enumerate(sample_bills, 1):
                    status = "✓ Tweeted" if bill['tweet_posted'] else "✗ Not tweeted"
                    print(f"  {i}. {bill['bill_id']} ({status}): {bill['title'][:40]}...")
            
        conn.close()
        return tweeted_count > 0
    except Exception as e:
        print(f"❌ Error checking data: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_app_queries():
    """Test the exact queries used by the Flask app"""
    print("\n" + "=" * 60)
    print("STEP 4: Testing Flask App Queries")
    print("=" * 60)
    
    try:
        # Import the actual database functions
        from src.database.db import get_latest_tweeted_bill, get_all_tweeted_bills
        
        print("\nTesting get_latest_tweeted_bill()...")
        latest = get_latest_tweeted_bill()
        if latest:
            print(f"✓ Function returned: {latest.get('bill_id')} - {latest.get('title', '')[:50]}...")
        else:
            print("❌ Function returned None (no bills found)")
        
        print("\nTesting get_all_tweeted_bills()...")
        all_bills = get_all_tweeted_bills()
        if all_bills:
            print(f"✓ Function returned {len(all_bills)} bills")
            for i, bill in enumerate(all_bills[:3], 1):
                print(f"  {i}. {bill.get('bill_id')}: {bill.get('title', '')[:40]}...")
        else:
            print("❌ Function returned empty list")
        
        return latest is not None and len(all_bills) > 0
    except Exception as e:
        print(f"❌ Error testing app queries: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Run all diagnostic tests"""
    print("\n" + "=" * 60)
    print("DATABASE DIAGNOSTIC TOOL")
    print("=" * 60)
    
    results = {
        "connection": test_connection(),
        "tables": check_tables(),
        "data": check_data(),
        "app_queries": test_app_queries()
    }
    
    print("\n" + "=" * 60)
    print("DIAGNOSTIC SUMMARY")
    print("=" * 60)
    
    for test_name, passed in results.items():
        status = "✓ PASS" if passed else "❌ FAIL"
        print(f"{test_name.upper()}: {status}")
    
    all_passed = all(results.values())
    
    print("\n" + "=" * 60)
    if all_passed:
        print("✓ ALL TESTS PASSED - Database is working correctly")
        print("=" * 60)
        print("\nIf the website still shows 'no bills', the issue may be:")
        print("1. Flask server not running or not restarted after changes")
        print("2. Browser cache showing old content")
        print("3. Flask app not loading environment variables correctly")
    else:
        print("❌ SOME TESTS FAILED - Issues detected")
        print("=" * 60)
        print("\nRoot cause analysis:")
        if not results["connection"]:
            print("- Database connection failed - check DATABASE_URL in .env")
        elif not results["tables"]:
            print("- Bills table doesn't exist - run database migration")
        elif not results["data"]:
            print("- No bills in database or no tweeted bills - need to process bills")
        elif not results["app_queries"]:
            print("- App query functions failing - check src/database/db.py")
    
    print("=" * 60)
    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(main())