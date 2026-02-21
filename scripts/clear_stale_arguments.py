#!/usr/bin/env python3
"""
Scan bills for old "generic" argument text (fallback) and clear them from the DB,
forcing the system to regenerate them on the next request.

This targets arguments containing the specific phrasing:
- "it takes meaningful action on"
- "meaningful action on" (looser match)
- "it fails to adequately protect the interests of everyday Americans regarding"

Usage:
    python scripts/clear_stale_arguments.py
"""

import sys
import os
import logging
from typing import List

# Ensure project root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database.connection import postgres_connect
from src.load_env import load_env

# Explicitly load .env
load_env()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

STALE_PHRASES = [
    "it takes meaningful action on",
    "meaningful action on",
    "it fails to adequately protect the interests of everyday Americans regarding",
]

def find_stale_arguments():
    """Identify bills with potential generic fallback text stored."""
    logger.info("🔍 Scanning for stale argument text...")
    
    stale_bills = []
    
    with postgres_connect() as conn:
        if not conn:
             logger.error("❌ Failed to connect to database.")
             return []
             
        with conn.cursor() as cur:
            # Check argument_support
            for phrase in STALE_PHRASES:
                try:
                    cur.execute(
                        "SELECT bill_id, argument_support FROM bills WHERE argument_support ILIKE %s",
                        (f"%{phrase}%",)
                    )
                    for row in cur.fetchall():
                        stale_bills.append({"bill_id": row[0], "col": "argument_support", "val": row[1]})
                except Exception as e:
                    logger.error(f"Error querying argument_support: {e}")

            # Check argument_oppose
            for phrase in STALE_PHRASES:
                try:
                    cur.execute(
                        "SELECT bill_id, argument_oppose FROM bills WHERE argument_oppose ILIKE %s",
                        (f"%{phrase}%",)
                    )
                    for row in cur.fetchall():
                        stale_bills.append({"bill_id": row[0], "col": "argument_oppose", "val": row[1]})
                except Exception as e:
                    logger.error(f"Error querying argument_oppose: {e}")
                    
    return stale_bills

def clear_stale(stale_items: List[dict]):
    """Null out the identified stale columns."""
    if not stale_items:
        logger.info("✅ No stale arguments found.")
        return

    logger.info(f"🧹 Clearing {len(stale_items)} stale argument entries...")
    
    processed_count = 0
    with postgres_connect() as conn:
        if not conn:
             return
             
        with conn.cursor() as cur:
            for item in stale_items:
                col = item["col"]
                bid = item["bill_id"]
                
                # Careful Update
                query = f"UPDATE bills SET {col} = NULL WHERE bill_id = %s"
                cur.execute(query, (bid,))
                processed_count += 1
                
        conn.commit()
    
    logger.info(f"✅ Successfully cleared {processed_count} argument fields.")

if __name__ == "__main__":
    stale = find_stale_arguments()
    if stale:
        clear_stale(stale)
        
        # Double check
        remaining = find_stale_arguments()
        if remaining:
            logger.warning(f"⚠️ {len(remaining)} stale items still remain!")
        else:
            logger.info("✨ Database clean.")
    else:
        logger.info("✅ No stale arguments found.")
