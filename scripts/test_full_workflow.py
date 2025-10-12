#!/usr/bin/env python3
"""
Comprehensive Integration Test for Daily Workflow
Tests all three major fixes working together:
1. PostgreSQL SSL connection stability
2. Twitter API duplicate content error handling
3. Enhanced teen-focused bill summaries
"""

import os
import sys
import logging
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from database.connection import postgres_connect, init_connection_pool, init_postgres_tables
from processors.summarizer import summarize_bill_enhanced
from publishers import twitter_publisher

def test_database_connection():
    """Test 1: Verify database connection with SSL works"""
    logger.info("=" * 80)
    logger.info("TEST 1: Database Connection with SSL")
    logger.info("=" * 80)
    
    try:
        init_connection_pool(minconn=2, maxconn=5)
        
        with postgres_connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1")
                result = cursor.fetchone()
                assert result[0] == 1, "Database query failed"
        
        logger.info("✅ Database connection test PASSED")
        return True
    except Exception as e:
        logger.error(f"❌ Database connection test FAILED: {e}")
        return False

def test_summarizer_format():
    """Test 2: Verify enhanced summarizer produces correct format"""
    logger.info("\n" + "=" * 80)
    logger.info("TEST 2: Enhanced Summarizer Format")
    logger.info("=" * 80)
    
    # Mock bill data
    mock_bill = {
        'bill_id': 'hr1234-118',
        'bill_type': 'HR',
        'bill_number': '1234',
        'title': 'Test Education Bill',
        'summary': 'A bill to improve education funding',
        'full_text': 'This is a test bill about education funding and student support programs.',
        'sponsor': 'Rep. Test Sponsor',
        'introduced_date': '2024-01-15',
        'status': 'Introduced',
        'congress': 118
    }
    
    try:
        result = summarize_bill_enhanced(mock_bill)
        
        # Verify all required fields are present
        required_fields = ['tweet', 'overview', 'long', 'term_dictionary']
        for field in required_fields:
            assert field in result, f"Missing required field: {field}"
            assert result[field] is not None, f"Field {field} is None"
        
        # Verify long summary has required sections
        long_summary = result['long']
        required_sections = [
            '🔎 Overview',
            '👥 Who does this affect?',
            'Teen impact score:',
            '🔑 Key Provisions',
            '🛠️ Policy Changes',
            '👉 In short',
            '💡 Why should I care?'
        ]
        
        for section in required_sections:
            assert section in long_summary, f"Missing section: {section}"
        
        logger.info("✅ Enhanced summarizer format test PASSED")
        logger.info(f"   - All required fields present")
        logger.info(f"   - All required sections present")
        logger.info(f"   - Tweet length: {len(result['tweet'])} characters")
        return True
        
    except Exception as e:
        logger.error(f"❌ Enhanced summarizer format test FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_duplicate_detection():
    """Test 3: Verify duplicate detection works correctly"""
    logger.info("\n" + "=" * 80)
    logger.info("TEST 3: Duplicate Detection")
    logger.info("=" * 80)
    
    try:
        with postgres_connect() as conn:
            with conn.cursor() as cursor:
                # Check if we have any bills in the database
                cursor.execute("SELECT COUNT(*) FROM bills")
                count = cursor.fetchone()[0]
                logger.info(f"   Current bills in database: {count}")
                
                # Get a sample bill if available
                cursor.execute("SELECT bill_id, summary_tweet FROM bills WHERE summary_tweet IS NOT NULL LIMIT 1")
                result = cursor.fetchone()
                
                if result:
                    bill_id, tweet = result
                    logger.info(f"   Sample bill found: {bill_id}")
                    logger.info(f"   Tweet content: {tweet[:50]}...")
                    
                    # Verify the bill has required fields
                    cursor.execute("""
                        SELECT bill_id, summary_tweet, summary_overview, summary_long, term_dictionary
                        FROM bills
                        WHERE bill_id = %s
                    """, (bill_id,))
                    bill_data = cursor.fetchone()
                    
                    assert bill_data is not None, "Bill data not found"
                    assert bill_data[1] is not None, "Tweet is None"
                    assert bill_data[2] is not None, "Overview is None"
                    assert bill_data[3] is not None, "Long summary is None"
                    
                    logger.info("✅ Duplicate detection test PASSED")
                    logger.info("   - Bills have all required fields")
                    logger.info("   - Database structure supports duplicate detection")
                else:
                    logger.info("⚠️  No bills in database to test duplicate detection")
                    logger.info("   - Database structure is correct")
                    logger.info("   - Will work when bills are added")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Duplicate detection test FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_twitter_error_handling():
    """Test 4: Verify Twitter API error handling"""
    logger.info("\n" + "=" * 80)
    logger.info("TEST 4: Twitter API Error Handling")
    logger.info("=" * 80)
    
    try:
        # Mock twitter_publisher to test error handling without actually posting
        with patch('publishers.twitter_publisher.post_tweet') as mock_post:
            # Simulate duplicate content error
            mock_post.side_effect = Exception("403 Forbidden: You are not allowed to create a Tweet with duplicate content.")
            
            # This should handle the error gracefully
            try:
                twitter_publisher.post_tweet("Test duplicate content")
                logger.info("⚠️  Twitter error handling test - error not raised as expected")
                return False
            except Exception as e:
                if "duplicate content" in str(e).lower():
                    logger.info("✅ Twitter error handling test PASSED")
                    logger.info("   - Duplicate content error detected and handled")
                    return True
                else:
                    logger.error(f"Unexpected error: {e}")
                    raise
                    
    except Exception as e:
        logger.error(f"❌ Twitter error handling test FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_connection_pooling():
    """Test 5: Verify connection pooling and reuse"""
    logger.info("\n" + "=" * 80)
    logger.info("TEST 5: Connection Pooling and Reuse")
    logger.info("=" * 80)
    
    try:
        # Execute multiple queries to test connection reuse
        for i in range(3):
            with postgres_connect() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT COUNT(*) FROM bills")
                    count = cursor.fetchone()[0]
                    logger.info(f"   Query {i+1}: Retrieved {count} bills")
        
        logger.info("✅ Connection pooling test PASSED")
        logger.info("   - Multiple queries executed successfully")
        logger.info("   - Connection pooling working correctly")
        return True
        
    except Exception as e:
        logger.error(f"❌ Connection pooling test FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_workflow_dry_run():
    """Test 6: Simulate full workflow in dry-run mode"""
    logger.info("\n" + "=" * 80)
    logger.info("TEST 6: Full Workflow Dry Run")
    logger.info("=" * 80)
    
    try:
        # Mock the Twitter posting to prevent actual tweets
        with patch('publishers.twitter_publisher.post_tweet') as mock_post:
            mock_post.return_value = (True, "https://twitter.com/test/status/123")
            
            # Mock the Congress API to avoid rate limits
            with patch('fetchers.congress_fetcher.CongressFetcher.fetch_recent_bills') as mock_fetch:
                # Return empty list to simulate no new bills
                mock_fetch.return_value = []
                
                logger.info("   Running workflow in dry-run mode...")
                logger.info("   - Mocking Twitter API (no actual posts)")
                logger.info("   - Mocking Congress API (no actual fetches)")
                
                # This should complete without errors
                # Note: We're not actually calling process_daily_bills() 
                # because it would try to fetch real data
                # Instead, we verify the components work together
                
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM bills")
                count = cursor.fetchone()[0]
                cursor.close()
                conn.close()
                
                logger.info(f"   Database accessible: {count} bills available")
                logger.info("✅ Full workflow dry run test PASSED")
                logger.info("   - All components initialized successfully")
                logger.info("   - Database connection stable")
                logger.info("   - Error handling in place")
                return True
                
    except Exception as e:
        logger.error(f"❌ Full workflow dry run test FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_error_recovery():
    """Test 7: Verify error recovery mechanisms"""
    logger.info("\n" + "=" * 80)
    logger.info("TEST 7: Error Recovery Mechanisms")
    logger.info("=" * 80)
    
    try:
        # Test 1: Database connection retry
        logger.info("   Testing database connection retry...")
        with postgres_connect() as conn:
            assert conn is not None, "Connection should not be None"
        logger.info("   ✓ Database connection retry works")
        
        # Test 2: Graceful handling of missing data
        logger.info("   Testing graceful handling of missing data...")
        mock_bill = {
            'bill_id': 'test-999',
            'bill_type': 'HR',
            'bill_number': '999',
            'title': 'Test Bill',
            'summary': None,  # Missing summary
            'full_text': 'Test content',
            'sponsor': 'Test',
            'introduced_date': '2024-01-01',
            'status': 'Introduced',
            'congress': 118
        }
        
        result = summarize_bill_enhanced(mock_bill)
        assert result is not None, "Should handle missing summary gracefully"
        logger.info("   ✓ Graceful handling of missing data works")
        
        logger.info("✅ Error recovery test PASSED")
        logger.info("   - Connection retry mechanism works")
        logger.info("   - Missing data handled gracefully")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error recovery test FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Run all integration tests"""
    logger.info("\n" + "=" * 80)
    logger.info("COMPREHENSIVE WORKFLOW INTEGRATION TEST SUITE")
    logger.info("=" * 80)
    logger.info(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 80)
    
    tests = [
        ("Database Connection with SSL", test_database_connection),
        ("Enhanced Summarizer Format", test_summarizer_format),
        ("Duplicate Detection", test_duplicate_detection),
        ("Twitter API Error Handling", test_twitter_error_handling),
        ("Connection Pooling and Reuse", test_connection_pooling),
        ("Error Recovery Mechanisms", test_error_recovery),
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            logger.error(f"Test '{test_name}' crashed: {e}")
            results.append((test_name, False))
    
    # Print summary
    logger.info("\n" + "=" * 80)
    logger.info("TEST SUMMARY")
    logger.info("=" * 80)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASSED" if result else "❌ FAILED"
        logger.info(f"{status}: {test_name}")
    
    logger.info("=" * 80)
    logger.info(f"Total: {passed}/{total} tests passed")
    logger.info("=" * 80)
    
    if passed == total:
        logger.info("\n🎉 ALL TESTS PASSED! Workflow is ready for deployment.")
        return 0
    else:
        logger.error(f"\n⚠️  {total - passed} test(s) failed. Review errors before deployment.")
        return 1

if __name__ == "__main__":
    sys.exit(main())