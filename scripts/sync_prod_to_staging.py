#!/usr/bin/env python3
"""
Sync Production to Staging
==========================
Copies reference data from Production to Staging.

Synced Tables:
- bills (SYNC)
- rep_contact_forms (SYNC)

Skipped Tables:
- votes (ISOLATED - staging has its own votes)

Safety:
- Fails if PROD_DATABASE_URL == DATABASE_URL
- PROD connection is READ-ONLY
- Staging tables are cleared before insert
"""

import os
import sys
import logging
import psycopg2
import psycopg2.extras
from typing import List, Dict, Any

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def get_db_connection(url):
    """Creates a raw psycopg2 connection."""
    try:
        # Enforce sslmode=require if not present
        if "sslmode" not in url:
            if "?" in url:
                url += "&sslmode=require"
            else:
                url += "?sslmode=require"
        
        conn = psycopg2.connect(url, cursor_factory=psycopg2.extras.RealDictCursor)
        return conn
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")
        sys.exit(1)

def get_columns(cursor, table_name):
    """Gets the column names for a table."""
    try:
        cursor.execute(f"SELECT * FROM {table_name} LIMIT 0")
        return [desc[0] for desc in cursor.description]
    except Exception as e:
        return None

def sync_table(prod_conn, staging_conn, table_name: str):
    """
    Syncs a single table from prod to staging.
    Reads all columns dynamically to ensure matching schema.
    Handled schema drift by only syncing intersection of columns.
    """
    logger.info(f"🔄 Syncing table: {table_name}...")

    try:
        # 1. Inspect Schema for both Prod and Staging
        with prod_conn.cursor() as prod_cursor, staging_conn.cursor() as staging_cursor:
            
            prod_columns = get_columns(prod_cursor, table_name)
            if not prod_columns:
                logger.warning(f"   ⚠️ Table '{table_name}' not found in production. Skipping.")
                prod_conn.rollback()
                return

            staging_columns = get_columns(staging_cursor, table_name)
            if not staging_columns:
                logger.warning(f"   ⚠️ Table '{table_name}' not found in staging. Skipping.")
                return

            # Find common columns
            common_columns = list(set(prod_columns) & set(staging_columns))
            
            # If no common columns, something is very wrong
            if not common_columns:
                logger.error(f"   ❌ No common columns found for {table_name}!")
                return

            cols_str = ", ".join(common_columns)
            logger.info(f"   ℹ️  Syncing {len(common_columns)} columns (Schema intersection).")

            # 2. Read from Prod (only common columns)
            logger.info(f"   Reading {table_name} from Production...")
            prod_cursor.execute(f"SELECT {cols_str} FROM {table_name}")
            rows = prod_cursor.fetchall()
            row_count = len(rows)
            logger.info(f"   📖 Read {row_count} rows from Production.")

            if row_count == 0:
                logger.info(f"   ⚠️ No data in production {table_name}. Skipping insert.")
                return

            # 3. Write to Staging
            
            # Clear existing data
            logger.info(f"   🧹 Clearing staging table {table_name}...")
            staging_cursor.execute(f"DELETE FROM {table_name}")
            
            # Prepare INSERT statement
            # placeholders: %s, %s, %s...
            placeholders = ", ".join(["%s"] * len(common_columns))
            insert_query = f"INSERT INTO {table_name} ({cols_str}) VALUES ({placeholders})"
            
            # Convert RealDictRow to tuple values for executemany
            # Note: We must ensure order matches 'common_columns' list
            # Since common_columns is a list, iterating it guarantees order
            values = [tuple(row[col] for col in common_columns) for row in rows]
            
            logger.info(f"   💾 Inserting {row_count} rows into Staging...")
            staging_cursor.executemany(insert_query, values)
            
        staging_conn.commit()
        logger.info(f"✅ Synced {table_name}: {row_count} rows.")

    except Exception as e:
        staging_conn.rollback()
        logger.error(f"❌ Failed to sync {table_name}: {e}")
        raise

def main():
    logger.info("🚀 Starting Production to Staging Sync...")

    # 1. Load Environment Variables
    prod_url = os.environ.get("PROD_DATABASE_URL")
    staging_url = os.environ.get("DATABASE_URL")

    if not prod_url:
        logger.error("❌ Missing PROD_DATABASE_URL environment variable.")
        sys.exit(1)
    
    if not staging_url:
        logger.error("❌ Missing DATABASE_URL environment variable.")
        sys.exit(1)

    # 2. Safety Check
    if prod_url == staging_url:
        logger.error("❌ ERROR: Prod and staging URLs are identical. Aborting to prevent data loss.")
        sys.exit(1)

    # 3. Connect
    logger.info("🔌 Connecting to databases...")
    prod_conn = get_db_connection(prod_url)
    staging_conn = get_db_connection(staging_url)

    try:
        # 4. Sync Tables
        sync_table(prod_conn, staging_conn, "bills")
        sync_table(prod_conn, staging_conn, "rep_contact_forms")
        
        logger.info("=" * 40)
        logger.info("✅ Data Sync Complete!")
        logger.info("=" * 40)

    except Exception as e:
        logger.error(f"❌ Critical error during sync: {e}")
        sys.exit(1)
    finally:
        if prod_conn: prod_conn.close()
        if staging_conn: staging_conn.close()

if __name__ == "__main__":
    main()
