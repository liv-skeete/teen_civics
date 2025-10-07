#!/usr/bin/env python3
"""
Test script to verify database connection after fixes.
"""

import os
import sys

# Load environment variables first
from src.load_env import load_env
load_env()

print("=" * 60)
print("DATABASE CONNECTION TEST")
print("=" * 60)

# Check if DATABASE_URL is loaded
database_url = os.environ.get('DATABASE_URL')
print(f"\n1. DATABASE_URL in environment: {bool(database_url)}")
if database_url:
    # Show first 50 chars for security
    print(f"   Value (first 50 chars): {database_url[:50]}...")

# Test connection string retrieval
from src.database.connection import get_connection_string
conn_string = get_connection_string()
print(f"\n2. Connection string retrieved: {bool(conn_string)}")
if conn_string:
    print(f"   Value (first 50 chars): {conn_string[:50]}...")

# Test if PostgreSQL is available
from src.database.connection import is_postgres_available
postgres_available = is_postgres_available()
print(f"\n3. PostgreSQL available: {postgres_available}")

# Test database type detection
try:
    from src.database.connection import get_database_type
    db_type = get_database_type()
    print(f"\n4. Database type: {db_type}")
except Exception as e:
    print(f"\n4. Database type detection failed: {e}")

# Test actual database query
try:
    from src.database.db import get_latest_tweeted_bill
    print("\n5. Testing database query (get_latest_tweeted_bill)...")
    bill = get_latest_tweeted_bill()
    if bill:
        print(f"   ✓ Success! Retrieved bill: {bill.get('bill_id', 'unknown')}")
    else:
        print("   ✓ Query succeeded but no bills found (database may be empty)")
except Exception as e:
    print(f"   ✗ Query failed: {e}")

print("\n" + "=" * 60)
print("TEST COMPLETE")
print("=" * 60)