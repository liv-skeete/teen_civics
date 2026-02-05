#!/usr/bin/env python3
"""
Migration script to update the FTS (Full-Text Search) trigger to include sponsor_name.
This enables searching for bills by sponsor name using PostgreSQL's full-text search.

The sponsor_name is added with weight 'A' (highest) since sponsor search is important.

Usage:
    python scripts/update_fts_for_sponsor.py
"""

import os
import sys
import logging

# Load environment variables first
from dotenv import load_dotenv
load_dotenv()

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database.connection import postgres_connect

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def update_fts_trigger():
    """
    Update the FTS trigger function to include sponsor_name in the search vector.
    """
    logger.info("=" * 60)
    logger.info("Updating FTS Trigger to Include Sponsor Name")
    logger.info("=" * 60)
    
    try:
        with postgres_connect() as conn:
            with conn.cursor() as cursor:
                # Step 1: Update the trigger function to include sponsor_name
                logger.info("Step 1: Updating trigger function 'update_bills_fts_vector'...")
                cursor.execute("""
                    CREATE OR REPLACE FUNCTION update_bills_fts_vector()
                    RETURNS TRIGGER AS $$
                    BEGIN
                        NEW.fts_vector :=
                            setweight(to_tsvector('english', COALESCE(NEW.title, '')), 'A') ||
                            setweight(to_tsvector('english', COALESCE(NEW.sponsor_name, '')), 'A') ||
                            setweight(to_tsvector('english', COALESCE(NEW.summary_long, '')), 'B') ||
                            setweight(to_tsvector('english', COALESCE(NEW.summary_overview, '')), 'C') ||
                            setweight(to_tsvector('english', COALESCE(NEW.summary_detailed, '')), 'C') ||
                            setweight(to_tsvector('english', COALESCE(NEW.summary_tweet, '')), 'C') ||
                            setweight(to_tsvector('english', COALESCE(NEW.tags, '')), 'D');
                        RETURN NEW;
                    END;
                    $$ LANGUAGE plpgsql;
                """)
                logger.info("✅ Trigger function updated to include sponsor_name with weight 'A'")
                
                # Step 2: Re-index all existing bills to include sponsor_name in FTS vector
                logger.info("Step 2: Re-indexing all existing bills...")
                cursor.execute("""
                    UPDATE bills
                    SET fts_vector =
                        setweight(to_tsvector('english', COALESCE(title, '')), 'A') ||
                        setweight(to_tsvector('english', COALESCE(sponsor_name, '')), 'A') ||
                        setweight(to_tsvector('english', COALESCE(summary_long, '')), 'B') ||
                        setweight(to_tsvector('english', COALESCE(summary_overview, '')), 'C') ||
                        setweight(to_tsvector('english', COALESCE(summary_detailed, '')), 'C') ||
                        setweight(to_tsvector('english', COALESCE(summary_tweet, '')), 'C') ||
                        setweight(to_tsvector('english', COALESCE(tags, '')), 'D');
                """)
                rows_updated = cursor.rowcount
                logger.info(f"✅ Re-indexed {rows_updated} bills")
                
                conn.commit()
                logger.info("✅ FTS trigger update completed successfully!")
                return True
                
    except Exception as e:
        logger.error(f"❌ Failed to update FTS trigger: {e}")
        return False


def verify_fts_update():
    """
    Verify that sponsor_name is now included in FTS search.
    """
    logger.info("\n" + "=" * 60)
    logger.info("Verifying FTS Update")
    logger.info("=" * 60)
    
    try:
        with postgres_connect() as conn:
            with conn.cursor() as cursor:
                # Check if we can find bills by sponsor name via FTS
                cursor.execute("""
                    SELECT bill_id, sponsor_name, 
                           fts_vector @@ to_tsquery('english', 'estes') as fts_matches_estes
                    FROM bills
                    WHERE sponsor_name IS NOT NULL 
                    AND sponsor_name != ''
                    LIMIT 5
                """)
                rows = cursor.fetchall()
                
                if rows:
                    logger.info("Sample bills with sponsor data:")
                    for row in rows:
                        bill_id, sponsor_name, fts_matches = row
                        status = "✓ FTS matches" if fts_matches else "✗ FTS no match"
                        logger.info(f"  - {bill_id}: {sponsor_name} [{status}]")
                    
                    # Test a specific search
                    cursor.execute("""
                        SELECT COUNT(*) FROM bills
                        WHERE fts_vector @@ websearch_to_tsquery('english', 'estes')
                        AND tweet_posted = TRUE
                    """)
                    fts_count = cursor.fetchone()[0]
                    logger.info(f"\n📊 FTS search for 'estes': {fts_count} results")
                    
                    cursor.execute("""
                        SELECT COUNT(*) FROM bills
                        WHERE LOWER(sponsor_name) LIKE '%estes%'
                        AND tweet_posted = TRUE
                    """)
                    like_count = cursor.fetchone()[0]
                    logger.info(f"📊 LIKE search for 'estes': {like_count} results")
                    
                    if fts_count > 0:
                        logger.info("✅ FTS is now indexing sponsor_name correctly!")
                    else:
                        logger.warning("⚠️ FTS might not be working for sponsor_name yet. Run backfill if needed.")
                else:
                    logger.warning("⚠️ No bills with sponsor data found. Run backfill script first.")
                    
                return True
                
    except Exception as e:
        logger.error(f"❌ Verification failed: {e}")
        return False


def main():
    success = update_fts_trigger()
    if success:
        verify_fts_update()
    
    logger.info("\n" + "=" * 60)
    if success:
        logger.info("✅ Migration completed successfully!")
        logger.info("📝 Note: Run 'python scripts/backfill_sponsor_data.py' to populate")
        logger.info("   sponsor data for all existing bills.")
    else:
        logger.info("❌ Migration failed. Check logs above for errors.")
    logger.info("=" * 60)
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
