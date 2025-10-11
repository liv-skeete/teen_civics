#!/usr/bin/env python3
"""
Simple script to diagnose the database connection issue.
"""

import os
import sys
import psycopg2

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")

# Load environment variables
from src.load_env import load_env
load_env()

print("=" * 60)
print("DATABASE CONNECTION DIAGNOSTIC")
print("=" * 60)

# Check if DATABASE_URL is loaded
database_url = os.environ.get('DATABASE_URL')
print(f"\n1. DATABASE_URL in environment: {bool(database_url)}")
if database_url:
    print(f"   Value (first 50 chars): {database_url[:50]}...")

# Test connection with explicit client encoding
print("\n2. Testing connection with explicit encoding...")
try:
    conn = psycopg2.connect(database_url, client_encoding='UTF8')
    print("   ✓ Successfully connected with UTF8 encoding")
    
    # Test with a simple query
    with conn.cursor() as cursor:
        cursor.execute('SELECT version()')
        version = cursor.fetchone()[0]
        print(f"   ✓ PostgreSQL version: {version[:80]}...")
    
    conn.close()
except psycopg2.OperationalError as e:
    print(f"   ❌ Connection failed with explicit encoding: {e}")
except Exception as e:
    print(f"   ❌ Unexpected error with explicit encoding: {e}")

# Test connection with different encoding options
print("\n3. Testing connection with different encoding options...")

# Try with client_encoding=None
try:
    conn = psycopg2.connect(database_url, client_encoding=None)
    print("   ✓ Successfully connected with client_encoding=None")
    conn.close()
except Exception as e:
    print(f"   ❌ Failed with client_encoding=None: {e}")

# Try with default encoding
try:
    conn = psycopg2.connect(database_url)
    print("   ✓ Successfully connected with default encoding")
    print(f"   ✓ Connection encoding: {conn.encoding}")
    conn.close()
except Exception as e:
    print(f"   ❌ Failed with default encoding: {e}")

print("\n" + "=" * 60)
print("DIAGNOSTIC COMPLETE")
print("=" * 60)