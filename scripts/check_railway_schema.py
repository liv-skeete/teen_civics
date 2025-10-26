#!/usr/bin/env python3
"""
Script to check the schema of the bills table in Railway database.
"""

import sys
import os

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Load environment variables first
from src.load_env import load_env
load_env()

# Import the database initialization function
from src.database.db import init_db
from src.database.connection import postgres_connect

def check_schema():
    """Check the schema of the bills table."""
    init_db()
    
    with postgres_connect() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name = 'bills' 
                ORDER BY ordinal_position
            """)
            columns = cursor.fetchall()
            
            print("Railway database bills table schema:")
            for column_name, data_type in columns:
                print(f"  - {column_name}: {data_type}")

if __name__ == "__main__":
    check_schema()