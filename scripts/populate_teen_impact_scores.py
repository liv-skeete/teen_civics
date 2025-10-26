#!/usr/bin/env python3
"""
Script to populate the teen_impact_score column in the database.

This script extracts teen impact scores from existing bill summaries and populates
the new teen_impact_score column for faster retrieval.
"""

import sys
import re
import argparse
import logging
from typing import Optional
import psycopg2.extras

# Load environment variables first
from dotenv import load_dotenv
load_dotenv()

# Add parent directory to path for imports
sys.path.insert(0, '.')

from src.database.connection import postgres_connect

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def extract_teen_impact_score(summary: str) -> Optional[int]:
    """
    Extract teen impact score from a bill summary.
    
    Args:
        summary: The bill summary text
        
    Returns:
        The teen impact score (0-10) or None if not found
    """
    if not summary:
        return None
    
    # Pattern to match "Teen impact score: X/10" (case insensitive)
    pattern = r'teen\s+impact\s+score:\s*(\d+)/10'
    match = re.search(pattern, summary, re.IGNORECASE)
    
    if match:
        try:
            score = int(match.group(1))
            if 0 <= score <= 10:
                return score
        except (ValueError, IndexError):
            pass
    
    return None


def populate_teen_impact_scores(dry_run: bool = False) -> bool:
    """
    Populate the teen_impact_score column for all bills in the database.
    
    Args:
        dry_run: If True, only preview changes without updating the database
        
    Returns:
        True if successful, False otherwise
    """
    logger.info(f"{'[DRY RUN] ' if dry_run else ''}Starting to populate teen_impact_score column...")
    
    try:
        with postgres_connect() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                # Get all bills
                logger.info("Fetching all bills from database...")
                cursor.execute("SELECT id, bill_id, summary_detailed FROM bills")
                bills = cursor.fetchall()
                logger.info(f"Found {len(bills)} bills to process.")
                
                update_count = 0
                for bill in bills:
                    bill_id = bill["bill_id"]
                    summary = bill["summary_detailed"] or ""
                    
                    # Extract teen impact score from summary
                    teen_impact_score = extract_teen_impact_score(summary)
                    
                    # Update the database if we found a score
                    if teen_impact_score is not None:
                        if not dry_run:
                            cursor.execute(
                                "UPDATE bills SET teen_impact_score = %s WHERE id = %s",
                                (teen_impact_score, bill["id"])
                            )
                        logger.info(f"{'[DRY RUN] ' if dry_run else ''}Updated {bill_id} with teen_impact_score: {teen_impact_score}")
                        update_count += 1
                    else:
                        logger.debug(f"No teen impact score found for {bill_id}")
                
                if not dry_run:
                    conn.commit()
                    logger.info(f"Updated {update_count} bills with teen impact scores.")
                else:
                    logger.info(f"[DRY RUN] Would have updated {update_count} bills with teen impact scores.")
                
                return True
                
    except Exception as e:
        logger.error(f"Failed to populate teen_impact_score column: {e}")
        return False


def main():
    """Main function."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without updating the database")
    
    args = parser.parse_args()
    
    success = populate_teen_impact_scores(dry_run=args.dry_run)
    
    if success:
        logger.info("Done!")
        sys.exit(0)
    else:
        logger.error("Failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()