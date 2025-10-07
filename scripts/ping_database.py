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
        
        # Attempt connection using the full DATABASE_URL
        conn = psycopg2.connect(database_url)
        conn.close()
        
        logger.info("✅ Database connection successful!")
        return True
        
    except ImportError:
        logger.error("psycopg2-binary not installed. Install with: pip install psycopg2-binary")
        return