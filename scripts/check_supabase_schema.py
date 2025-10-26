#!/usr/bin/env python3
"""
Script to check the schema of the bills table in Supabase database.

Usage:
  SUPABASE_DB_URL="postgresql://..." python3 scripts/check_supabase_schema.py

Note: Set this environment variable with your actual Supabase database connection string.
"""

import sys
import os
import psycopg2
import psycopg2.extras
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Get database URL from environment variable for security
SUPABASE_DB_URL = os.environ.get('SUPABASE_DB_URL')

# Ensure environment variable is set
if not SUPABASE_DB_URL:
    raise ValueError("SUPABASE_DB_URL environment variable is not set")

def connect_to_database(db_url: str) -> psycopg2.extensions.connection:
    """Connect to a PostgreSQL database."""
    try:
        conn = psycopg2.connect(
            db_url,
            keepalives=1,
            keepalives_idle=30,
            keepalives_interval=10,
            keepalives_count=5,
            connect_timeout=10
        )
        logger.info(f"Successfully connected to database")
        return conn
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")
        raise

def check_schema():
    """Check the schema of the bills table."""
    try:
        # Connect to Supabase database
        logger.info("Connecting to Supabase database...")
        supabase_conn = connect_to_database(SUPABASE_DB_URL)
        
        with supabase_conn.cursor() as cursor:
            cursor.execute("""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name = 'bills' 
                ORDER BY ordinal_position
            """)
            columns = cursor.fetchall()
            
            print("Supabase database bills table schema:")
            for column_name, data_type in columns:
                print(f"  - {column_name}: {data_type}")
        
        # Close connection
        supabase_conn.close()
        
    except Exception as e:
        logger.error(f"Failed to check schema: {e}")
        raise

if __name__ == "__main__":
    check_schema()