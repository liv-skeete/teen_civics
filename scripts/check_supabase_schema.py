#!/usr/bin/env python3
"""
Script to check the schema of the bills table in Supabase database.
"""

import psycopg2
import psycopg2.extras
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Original Supabase connection string (provided by user)
SUPABASE_DB_URL = "postgresql://postgres.ogsonggpqnmwivimnpqu:kusnav-wyxdop-8qUfwo@aws-1-us-west-1.pooler.supabase.com:6543/postgres"

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