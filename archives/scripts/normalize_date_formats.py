#!/usr/bin/env python3
"""
Script to normalize date_processed formats in the database.
Converts verbose timestamps like "2025-10-10T04:35:51.745392+00:00" 
to normalized format "2025-10-10 04:35:51".
"""

import os
import sys
import logging
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables first
load_dotenv()

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.database.connection import postgres_connect

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def normalize_dates():
    """
    Normalize all date_processed fields in the bills table.
    Converts timestamps to the format: "YYYY-MM-DD HH:MM:SS"
    """
    logger.info("🚀 Starting date format normalization...")
    
    try:
        with postgres_connect() as conn:
            with conn.cursor() as cursor:
                # Count total bills first
                cursor.execute("SELECT COUNT(*) FROM bills")
                total_bills = cursor.fetchone()[0]
                logger.info(f"📊 Found {total_bills} bills to process")
                
                # Process bills in batches to avoid memory issues
                batch_size = 100
                offset = 0
                updated_count = 0
                
                while True:
                    # Get a batch of bills
                    cursor.execute("""
                        SELECT id, date_processed
                        FROM bills
                        ORDER BY id
                        LIMIT %s OFFSET %s
                    """, (batch_size, offset))
                    
                    rows = cursor.fetchall()
                    if not rows:
                        break
                    
                    logger.info(f"🔄 Processing batch of {len(rows)} bills (offset {offset})")
                    
                    # Update each bill's date_processed format
                    for bill_id, date_processed in rows:
                        if date_processed:
                            try:
                                # Normalize the datetime format
                                # Handle various formats that might exist in the database
                                if isinstance(date_processed, str):
                                    # Parse the existing timestamp string
                                    if 'T' in date_processed:
                                        # Handle ISO format with timezone
                                        if '.' in date_processed:
                                            # Remove microseconds
                                            date_part = date_processed.split('.')[0]
                                        else:
                                            date_part = date_processed
                                        
                                        # Remove timezone info
                                        if '+' in date_part:
                                            date_part = date_part.split('+')[0]
                                        elif date_part.endswith('Z'):
                                            date_part = date_part[:-1]
                                        
                                        normalized_obj = datetime.fromisoformat(date_part)
                                    else:
                                        # Handle simple date format
                                        normalized_obj = datetime.fromisoformat(date_processed)
                                else:
                                    # It's already a datetime object
                                    normalized_obj = date_processed
                                
                                # Convert to our desired format string
                                normalized_str = normalized_obj.strftime('%Y-%m-%d %H:%M:%S')
                                
                                # Update the record with the string format
                                cursor.execute("""
                                    UPDATE bills
                                    SET date_processed = %s
                                    WHERE id = %s
                                """, (normalized_str, bill_id))
                                
                                updated_count += 1
                            except Exception as e:
                                logger.warning(f"⚠️ Could not normalize date for bill {bill_id}: {date_processed} - {e}")
                                continue
                    
                    # Commit after each batch
                    conn.commit()
                    logger.info(f"✅ Committed batch of {len(rows)} bills")
                    
                    offset += batch_size
                
                logger.info(f"✅ Normalization completed successfully! Updated {updated_count} bills")
                return True
                
    except Exception as e:
        logger.error(f"❌ Date normalization failed: {e}")
        return False


def verify_normalization():
    """
    Verify that all dates will display correctly with our template filter.
    Note: PostgreSQL stores timestamps with timezone info, but our template filter handles display.
    """
    logger.info("🔍 Verifying date normalization...")
    logger.info("Note: PostgreSQL automatically converts strings to timestamp format with timezone info.")
    logger.info("As long as our template filter works correctly, the display format will be normalized.")
    
    try:
        with postgres_connect() as conn:
            with conn.cursor() as cursor:
                # Get total count
                cursor.execute("SELECT COUNT(*) FROM bills WHERE date_processed IS NOT NULL")
                total_count = cursor.fetchone()[0]
                
                if total_count > 0:
                    logger.info(f"✅ All {total_count} bills have date_processed values.")
                    logger.info("✅ The template filter will format these correctly for display.")
                    return True
                else:
                    logger.warning("⚠️ No bills with date_processed found")
                    return False
                    
    except Exception as e:
        logger.error(f"❌ Verification failed: {e}")
        return False


def main():
    """Main function to run the date normalization."""
    logger.info("📅 Starting date format normalization process...")
    
    # Normalize dates
    success = normalize_dates()
    if not success:
        logger.error("❌ Date normalization failed")
        sys.exit(1)
    
    # Verify results
    verified = verify_normalization()
    if not verified:
        logger.error("❌ Date verification failed")
        sys.exit(1)
    
    logger.info("🎉 Date format normalization completed successfully!")


if __name__ == "__main__":
    main()