#!/usr/bin/env python3
"""
Simple script to ping the PostgreSQL database and verify connectivity.
Used by GitHub Actions to ensure database is available before processing.
"""

import os
import sys
import logging
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

def ping_database():
    """
    Attempt to connect to the PostgreSQL database to verify connectivity.
    Returns True if successful, False otherwise.
    """
    database_url = os.getenv('DATABASE_URL')
    
    if not database_url:
        logger.error("DATABASE_URL environment variable not set")
        logger.error("Please check that DATABASE_URL secret is configured in GitHub repository settings")
        logger.error("Go to: Settings → Secrets and variables → Actions → Repository secrets")
        return False
    
    logger.info(f"Attempting to connect to database: {database_url.split('@')[1] if '@' in database_url else database_url}")
    
    try:
        # Import psycopg2 for PostgreSQL
        import psycopg2
        
        # Attempt connection with explicit encoding settings
        # This fixes the "server didn't return client encoding" error
        conn = psycopg2.connect(
            database_url,
            client_encoding='UTF8'
        )
        conn.close()
        
        logger.info("✅ Database connection successful!")
        return True
        
    except ImportError:
        logger.error("psycopg2-binary not installed. Install with: pip install psycopg2-binary")
        return False
        
    except psycopg2.OperationalError as e:
        logger.error(f"❌ Database connection failed: {e}")
        logger.error("Common causes:")
        logger.error("  1. Database server is not running")
        logger.error("  2. Incorrect DATABASE_URL format")
        logger.error("  3. Network connectivity issues")
        logger.error("  4. Database credentials are incorrect")
        return False
        
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}")
        return False

if __name__ == "__main__":
    """Main entry point for the script."""
    logger.info("=== Database Connectivity Check ===")
    
    success = ping_database()
    
    if success:
        logger.info("=== Check Complete: SUCCESS ===")
        sys.exit(0)
    else:
        logger.error("=== Check Complete: FAILED ===")
        sys.exit(1)