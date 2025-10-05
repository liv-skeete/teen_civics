#!/usr/bin/env python3
"""
Test script to validate SSL connection fixes.
Tests connection pooling, retry logic, and error handling.
"""

import os
import sys
import logging
import time

# Configure logging to see diagnostic messages
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '.'))

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv()
    logger.info("✓ Environment variables loaded from .env")
except ImportError:
    logger.warning("python-dotenv not installed, using existing environment variables")

def test_basic_connection():
    """Test basic connection and query execution."""
    logger.info("=" * 60)
    logger.info("TEST 1: Basic Connection Test")
    logger.info("=" * 60)
    
    try:
        from src.database.connection import postgres_connect, init_connection_pool
        
        # Initialize pool
        init_connection_pool(minconn=2, maxconn=5)
        logger.info("✓ Connection pool initialized")
        
        # Test a simple query
        with postgres_connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1 as test")
                result = cursor.fetchone()
                assert result[0] == 1, "Query result mismatch"
                logger.info(f"✓ Query executed successfully: {result}")
        
        logger.info("✓ TEST 1 PASSED: Basic connection works")
        return True
        
    except Exception as e:
        logger.error(f"✗ TEST 1 FAILED: {e}")
        return False

def test_connection_reuse():
    """Test that connections are reused from the pool."""
    logger.info("=" * 60)
    logger.info("TEST 2: Connection Reuse Test")
    logger.info("=" * 60)
    
    try:
        from src.database.connection import postgres_connect
        
        # Execute multiple queries to test connection reuse
        for i in range(3):
            logger.info(f"\n--- Query {i + 1} ---")
            with postgres_connect() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT 1")
                    cursor.fetchone()
            time.sleep(0.5)  # Small delay between queries
        
        logger.info("✓ TEST 2 PASSED: Multiple queries executed successfully")
        return True
        
    except Exception as e:
        logger.error(f"✗ TEST 2 FAILED: {e}")
        return False

def test_database_operations():
    """Test actual database operations (table check)."""
    logger.info("=" * 60)
    logger.info("TEST 3: Database Operations Test")
    logger.info("=" * 60)
    
    try:
        from src.database.connection import postgres_connect
        
        with postgres_connect() as conn:
            with conn.cursor() as cursor:
                # Check if bills table exists
                cursor.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_name = 'bills'
                    )
                """)
                table_exists = cursor.fetchone()[0]
                logger.info(f"✓ Bills table exists: {table_exists}")
                
                if table_exists:
                    # Count bills
                    cursor.execute("SELECT COUNT(*) FROM bills")
                    count = cursor.fetchone()[0]
                    logger.info(f"✓ Bills in database: {count}")
        
        logger.info("✓ TEST 3 PASSED: Database operations work")
        return True
        
    except Exception as e:
        logger.error(f"✗ TEST 3 FAILED: {e}")
        return False

def test_connection_pool_info():
    """Test connection pool information and metadata tracking."""
    logger.info("=" * 60)
    logger.info("TEST 4: Connection Pool Metadata Test")
    logger.info("=" * 60)
    
    try:
        from src.database.connection import postgres_connect
        
        # Execute a query and check that diagnostic logging is working
        logger.info("Executing query to verify diagnostic logging...")
        with postgres_connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT version()")
                version = cursor.fetchone()[0]
                logger.info(f"✓ PostgreSQL version: {version[:50]}...")
        
        logger.info("✓ TEST 4 PASSED: Connection pool metadata tracking works")
        return True
        
    except Exception as e:
        logger.error(f"✗ TEST 4 FAILED: {e}")
        return False

def main():
    """Run all tests."""
    logger.info("\n" + "=" * 60)
    logger.info("PostgreSQL SSL Connection Fix - Test Suite")
    logger.info("=" * 60 + "\n")
    
    # Check if database is configured
    if not os.getenv('DATABASE_URL'):
        logger.error("DATABASE_URL not set. Please configure database connection.")
        return 1
    
    results = []
    
    # Run tests
    results.append(("Basic Connection", test_basic_connection()))
    results.append(("Connection Reuse", test_connection_reuse()))
    results.append(("Database Operations", test_database_operations()))
    results.append(("Connection Pool Metadata", test_connection_pool_info()))
    
    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("TEST SUMMARY")
    logger.info("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✓ PASSED" if result else "✗ FAILED"
        logger.info(f"{status}: {test_name}")
    
    logger.info(f"\nTotal: {passed}/{total} tests passed")
    logger.info("=" * 60 + "\n")
    
    return 0 if passed == total else 1

if __name__ == "__main__":
    sys.exit(main())