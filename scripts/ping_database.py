#!/usr/bin/env python3
"""
Simple script to test PostgreSQL database connectivity.
Used by GitHub Actions to ensure the database is available before processing.
"""

import os
import sys
import logging
from dotenv import load_dotenv
import psycopg2

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Load environment variables from .env file
load_dotenv()

def check_database_connection():
    """
    Attempt to connect to the PostgreSQL database to verify connectivity.
    Returns True if successful, False otherwise.
    """
    database_url = os.getenv('DATABASE_URL')
    
    if not database_url:
        logger.error("DATABASE_URL environment variable not set.")
        logger.error("Please ensure the DATABASE_URL secret is configured in your repository settings.")
        return False
    
    logger.info("Testing database connectivity...")
    
    try:
        # Attempt to connect to the database
        conn = psycopg2.connect(database_url)
        conn.close()
        
        logger.info("✅ Database connection successful!")
        return True
        
    except ImportError:
        logger.error("psycopg2-binary is not installed. Please add it to your requirements.txt.")
        return False
        
    except psycopg2.OperationalError as e:
        logger.error(f"❌ Database connection failed: {e}")
        logger.error("Common causes:")
        logger.error("  1. Database server is not running or is unreachable.")
        logger.error("  2. Incorrect DATABASE_URL format or invalid credentials.")
        logger.error("  3. Firewall rules are blocking the connection.")
        return False
        
    except Exception as e:
        logger.error(f"❌ An unexpected error occurred: {e}")
        return False

if __name__ == "__main__":
    """Main entry point for the script."""
    logger.info("=== Database Connectivity Test ===")
    
    if check_database_connection():
        logger.info("=== Test Complete: SUCCESS ===")
        sys.exit(0)
    else:
        logger.error("=== Test Complete: FAILED ===")
        sys.exit(1)