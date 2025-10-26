#!/usr/bin/env python3
"""
Script to initialize the Railway PostgreSQL database tables.
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

if __name__ == "__main__":
    print("Initializing Railway PostgreSQL database tables...")
    try:
        init_db()
        print("✅ Database tables initialized successfully!")
    except Exception as e:
        print(f"❌ Failed to initialize database tables: {e}")
        sys.exit(1)