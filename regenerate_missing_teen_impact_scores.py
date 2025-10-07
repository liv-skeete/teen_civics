#!/usr/bin/env python3
"""
Script to regenerate summaries for bills missing teen impact scores.

This script identifies bills in the database that don't have teen impact scores
in their summaries and regenerates them using the current enhanced summarizer.

Usage:
    python3 regenerate_missing_teen_impact_scores.py           # Run with confirmation
    python3 regenerate_missing_teen_impact_scores.py --dry-run # Preview without updating
"""

import sys
import re
import argparse
import logging
from typing import Dict, Any, Optional, List

# Add src to path for imports
sys.path.insert(0, 'src')

from database.db import get_all_bills, db_connect
from processors.summarizer import summarize_bill_enhanced

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
            # Validate score is in valid range
            if 0 <= score <= 10:
                return score
        except (ValueError, IndexError):
            pass
    
    return None


def has_teen_impact_score(bill: Dict[str, Any]) -> bool:
    """
    Check if a bill has a teen impact score in any of its summary fields.
    
    Args:
        bill: Bill dictionary from database
        
    Returns:
        True if teen impact score is found, False otherwise
    """
    # Check all summary fields
    summary_fields = ['summary_detailed', 'summary_long', 'summary_overview']
    
    for field in summary_fields:
        summary = bill.get(field, '')
        if summary and extract_teen_impact_score(summary) is not None:
            return True
    
    return False


def regenerate_bill_summary(bill: Dict[str, Any], dry_run: bool = False) -> bool:
    """
    Regenerate summary for a single bill.
    
    Args:
        bill: Bill dictionary from database
        dry_run: If True, don't actually update the database
        
    Returns:
        True if successful, False otherwise
    """
    bill_id = bill.get('bill_id', 'unknown')
    
    try:
        logger.info(f"Processing bill {bill_id}...")
        
        # Check if bill has full text
        if not bill.get('full_text'):
            logger.warning(f"  ⚠️  Bill {bill_id} has no full text - summary may be limited")
        
        # Regenerate summary using enhanced summarizer
        logger.info(f"  🔄 Calling summarizer for {bill_id}...")
        new_summary = summarize_bill_enhanced(bill)
        
        if not new_summary:
            logger.error(f"  ❌ Summarizer returned None for {bill_id}")
            return False
        
        # Verify the new summary has a teen impact score
        # Note: summarizer returns 'detailed', 'long', 'overview' (not 'summary_*')
        has_score = False
        for field in ['detailed', 'long', 'overview']:
            if new_summary.get(field) and extract_teen_impact_score(new_summary[field]) is not None:
                has_score = True
                break
        
        if not has_score:
            logger.warning(f"  ⚠️  New summary for {bill_id} still missing teen impact score")
        else:
            logger.info(f"  ✅ New summary for {bill_id} includes teen impact score")
        
        if dry_run:
            logger.info(f"  [DRY RUN] Would update {bill_id} with new summary")
            return True
        
        # Update database with new summary
        # Note: summarizer returns 'overview', 'detailed', 'tweet', 'long', 'term_dictionary'
        logger.info(f"  💾 Updating database for {bill_id}...")
        with db_connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute('''
                UPDATE bills
                SET summary_overview = %s,
                    summary_detailed = %s,
                    summary_tweet = %s,
                    term_dictionary = %s,
                    summary_long = %s
                WHERE bill_id = %s
                ''', (
                    new_summary.get('overview', ''),
                    new_summary.get('detailed', ''),
                    new_summary.get('tweet', ''),
                    new_summary.get('term_dictionary', ''),
                    new_summary.get('long', ''),
                    bill_id
                ))
                
                if cursor.rowcount == 0:
                    logger.error(f"  ❌ Failed to update {bill_id} - no rows affected")
                    return False
        
        logger.info(f"  ✅ Successfully updated {bill_id}")
        return True
        
    except Exception as e:
        logger.error(f"  ❌ Error processing {bill_id}: {e}", exc_info=True)
        return False


def main():
    """Main function to regenerate summaries for bills missing teen impact scores."""
    parser = argparse.ArgumentParser(
        description='Regenerate summaries for bills missing teen impact scores'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview which bills would be updated without actually updating them'
    )
    parser.add_argument(
        '--limit',
        type=int,
        default=None,
        help='Limit the number of bills to process (useful for testing)'
    )
    
    args = parser.parse_args()
    
    logger.info("=" * 70)
    logger.info("Teen Impact Score Regeneration Script")
    logger.info("=" * 70)
    
    if args.dry_run:
        logger.info("🔍 DRY RUN MODE - No database changes will be made")
    
    # Fetch all bills from database
    logger.info("\n📚 Fetching all bills from database...")
    try:
        # Get a large number of bills (adjust if needed)
        all_bills = get_all_bills(limit=1000)
        logger.info(f"✅ Retrieved {len(all_bills)} bills from database")
    except Exception as e:
        logger.error(f"❌ Failed to fetch bills from database: {e}")
        return 1
    
    if not all_bills:
        logger.info("ℹ️  No bills found in database")
        return 0
    
    # Identify bills missing teen impact scores
    logger.info("\n🔍 Identifying bills missing teen impact scores...")
    bills_missing_scores = []
    
    for bill in all_bills:
        if not has_teen_impact_score(bill):
            bills_missing_scores.append(bill)
    
    logger.info(f"Found {len(bills_missing_scores)} bills missing teen impact scores")
    
    if not bills_missing_scores:
        logger.info("✅ All bills have teen impact scores!")
        return 0
    
    # Apply limit if specified
    if args.limit:
        bills_missing_scores = bills_missing_scores[:args.limit]
        logger.info(f"ℹ️  Limited to processing {len(bills_missing_scores)} bills")
    
    # Display bills that will be processed
    logger.info("\n📋 Bills to be processed:")
    for i, bill in enumerate(bills_missing_scores, 1):
        bill_id = bill.get('bill_id', 'unknown')
        title = bill.get('title', 'No title')[:60]
        logger.info(f"  {i}. {bill_id}: {title}...")
    
    # Confirmation prompt (skip in dry-run mode)
    if not args.dry_run:
        logger.info("\n" + "=" * 70)
        response = input(f"⚠️  Proceed with regenerating {len(bills_missing_scores)} bill summaries? (yes/no): ")
        if response.lower() not in ['yes', 'y']:
            logger.info("❌ Operation cancelled by user")
            return 0
    
    # Process each bill
    logger.info("\n" + "=" * 70)
    logger.info("🚀 Starting regeneration process...")
    logger.info("=" * 70)
    
    successful = 0
    failed = 0
    
    for i, bill in enumerate(bills_missing_scores, 1):
        bill_id = bill.get('bill_id', 'unknown')
        logger.info(f"\n[{i}/{len(bills_missing_scores)}] Processing {bill_id}")
        
        if regenerate_bill_summary(bill, dry_run=args.dry_run):
            successful += 1
        else:
            failed += 1
    
    # Summary statistics
    logger.info("\n" + "=" * 70)
    logger.info("📊 Summary Statistics")
    logger.info("=" * 70)
    logger.info(f"Total bills processed: {len(bills_missing_scores)}")
    logger.info(f"✅ Successful: {successful}")
    logger.info(f"❌ Failed: {failed}")
    
    if args.dry_run:
        logger.info("\n🔍 DRY RUN COMPLETE - No changes were made to the database")
    else:
        logger.info("\n✅ Regeneration complete!")
    
    return 0 if failed == 0 else 1


if __name__ == '__main__':
    sys.exit(main())