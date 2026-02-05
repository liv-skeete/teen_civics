#!/usr/bin/env python3
"""
Backfill script to populate sponsor data for existing bills.
Fetches sponsor information from the Congress.gov API for bills that don't have it.

Usage:
    python scripts/backfill_sponsor_data.py [--limit N] [--dry-run]

Options:
    --limit N    Maximum number of bills to process (default: all)
    --dry-run    Preview what would be updated without making changes
"""

import os
import sys
import re
import time
import logging
import argparse

# Load environment variables first
from dotenv import load_dotenv
load_dotenv()

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database.db import get_bills_without_sponsor, update_bill_sponsor
from src.fetchers.congress_fetcher import fetch_bill_details_from_api

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Congress.gov API key
CONGRESS_API_KEY = os.getenv('CONGRESS_API_KEY')

# Rate limiting: 1 request per second to be safe
REQUEST_DELAY = 1.0


def parse_bill_id(bill_id: str) -> tuple:
    """
    Parse a bill_id into its components.
    
    Examples:
        'hr1234-119' -> ('119', 'hr', '1234')
        'sjres83-119' -> ('119', 'sjres', '83')
        's456-118' -> ('118', 's', '456')
    
    Returns:
        tuple: (congress, bill_type, bill_number) or (None, None, None) if parsing fails
    """
    # Pattern: bill_type + number + '-' + congress
    # e.g., hr1234-119, sjres83-119, s456-118
    pattern = r'^([a-z]+)(\d+)-(\d+)$'
    match = re.match(pattern, bill_id.lower())
    
    if match:
        bill_type = match.group(1)
        bill_number = match.group(2)
        congress = match.group(3)
        return (congress, bill_type, bill_number)
    
    logger.warning(f"Could not parse bill_id: {bill_id}")
    return (None, None, None)


def backfill_sponsors(limit: int = None, dry_run: bool = False) -> dict:
    """
    Backfill sponsor data for existing bills.
    
    Args:
        limit: Maximum number of bills to process (None = all)
        dry_run: If True, don't actually update the database
    
    Returns:
        dict with counts: {'processed': N, 'updated': N, 'failed': N, 'skipped': N}
    """
    if not CONGRESS_API_KEY:
        logger.error("❌ CONGRESS_API_KEY not set in environment")
        return {'processed': 0, 'updated': 0, 'failed': 0, 'skipped': 0}
    
    # Get bills without sponsor data
    fetch_limit = limit if limit else 10000  # Large default
    bills = get_bills_without_sponsor(limit=fetch_limit)
    
    if not bills:
        logger.info("✅ No bills found without sponsor data. All bills are up to date!")
        return {'processed': 0, 'updated': 0, 'failed': 0, 'skipped': 0}
    
    logger.info(f"📋 Found {len(bills)} bills without sponsor data")
    if limit:
        bills = bills[:limit]
        logger.info(f"📋 Processing {len(bills)} bills (limited)")
    
    if dry_run:
        logger.info("🔍 DRY RUN MODE - No changes will be made")
    
    stats = {'processed': 0, 'updated': 0, 'failed': 0, 'skipped': 0}
    
    for i, bill in enumerate(bills):
        bill_id = bill['bill_id']
        stats['processed'] += 1
        
        logger.info(f"[{i+1}/{len(bills)}] Processing {bill_id}...")
        
        # Parse bill_id to get components
        congress, bill_type, bill_number = parse_bill_id(bill_id)
        
        if not congress or not bill_type or not bill_number:
            logger.warning(f"  ⚠️ Skipping {bill_id} - could not parse bill_id")
            stats['skipped'] += 1
            continue
        
        try:
            # Fetch bill details from API
            details = fetch_bill_details_from_api(congress, bill_type, bill_number, CONGRESS_API_KEY)
            
            if not details:
                logger.warning(f"  ⚠️ No API response for {bill_id}")
                stats['failed'] += 1
                continue
            
            # Extract sponsor data
            sponsors = details.get('sponsors', [])
            if not sponsors:
                logger.info(f"  ℹ️ No sponsor data available for {bill_id}")
                stats['skipped'] += 1
                continue
            
            primary_sponsor = sponsors[0]
            sponsor_name = primary_sponsor.get('fullName', '')
            sponsor_party = primary_sponsor.get('party', '')
            sponsor_state = primary_sponsor.get('state', '')
            
            if not sponsor_name:
                logger.info(f"  ℹ️ Sponsor name empty for {bill_id}")
                stats['skipped'] += 1
                continue
            
            logger.info(f"  📝 Sponsor: {sponsor_name} ({sponsor_party}-{sponsor_state})")
            
            # Update database
            if not dry_run:
                success = update_bill_sponsor(bill_id, sponsor_name, sponsor_party, sponsor_state)
                if success:
                    logger.info(f"  ✅ Updated {bill_id}")
                    stats['updated'] += 1
                else:
                    logger.error(f"  ❌ Failed to update {bill_id}")
                    stats['failed'] += 1
            else:
                logger.info(f"  🔍 Would update {bill_id} (dry run)")
                stats['updated'] += 1
            
            # Rate limiting
            time.sleep(REQUEST_DELAY)
            
        except Exception as e:
            logger.error(f"  ❌ Error processing {bill_id}: {e}")
            stats['failed'] += 1
            continue
    
    return stats


def main():
    parser = argparse.ArgumentParser(description='Backfill sponsor data for existing bills')
    parser.add_argument('--limit', type=int, default=None, help='Maximum number of bills to process')
    parser.add_argument('--dry-run', action='store_true', help='Preview changes without updating database')
    args = parser.parse_args()
    
    logger.info("=" * 60)
    logger.info("Sponsor Data Backfill Script")
    logger.info("=" * 60)
    
    stats = backfill_sponsors(limit=args.limit, dry_run=args.dry_run)
    
    logger.info("=" * 60)
    logger.info("Summary:")
    logger.info(f"  Processed: {stats['processed']}")
    logger.info(f"  Updated:   {stats['updated']}")
    logger.info(f"  Failed:    {stats['failed']}")
    logger.info(f"  Skipped:   {stats['skipped']}")
    logger.info("=" * 60)
    
    if stats['failed'] > 0:
        logger.warning("⚠️ Some bills failed to update. Check logs above for details.")
        sys.exit(1)
    else:
        logger.info("✅ Backfill completed successfully!")
        sys.exit(0)


if __name__ == "__main__":
    main()
