#!/usr/bin/env python3
"""
Script to validate bill summaries and automatically fix those containing 
"full bill text" phrases by regenerating them with actual full text.
"""

import os
import sys
import logging
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.database.connection import postgres_connect
from src.database.db import get_bill_by_slug, update_bill_summaries, get_bill_by_id
from src.processors.summarizer import summarize_bill_enhanced
from src.fetchers.congress_fetcher import fetch_bill_text_from_api
import time

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def find_bills_with_full_bill_text_phrases():
    """Find all bills with summaries containing 'full bill text' phrases."""
    
    # Check if DATABASE_URL is set
    if not os.environ.get('DATABASE_URL'):
        logger.error("DATABASE_URL environment variable not set.")
        return []
    
    try:
        problematic_bills = []
        
        with postgres_connect() as conn:
            with conn.cursor() as cursor:
                # Query for bills where any summary field contains "full bill text"
                cursor.execute("""
                    SELECT bill_id,
                           website_slug,
                           congress_session,
                           summary_overview,
                           summary_detailed,
                           summary_tweet
                    FROM bills
                    WHERE COALESCE(summary_overview, '') ILIKE %s
                       OR COALESCE(summary_detailed, '') ILIKE %s
                       OR COALESCE(summary_tweet, '') ILIKE %s
                """, ('%full bill text%', '%full bill text%', '%full bill text%'))
                
                rows = cursor.fetchall()
                
                for row in rows:
                    bill_id, slug, congress_session, overview, detailed, tweet = row
                    bill_info = {
                        'bill_id': bill_id,
                        'website_slug': slug,
                        'congress_session': congress_session,
                        'problematic_fields': []
                    }
                    
                    # Extract bill type and number from bill_id
                    # bill_id format is like "hr318-119" or "s284-119"
                    if '-' in bill_id:
                        bill_type_number = bill_id.split('-')[0]
                        # Extract bill type (e.g., "hr", "s", "sjres") and number
                        import re
                        match = re.match(r'^([a-z]+)([0-9]+)$', bill_type_number, re.IGNORECASE)
                        if match:
                            bill_info['bill_type'] = match.group(1).lower()
                            bill_info['bill_number'] = match.group(2)
                    
                    # Check which fields contain the phrase
                    if overview and 'full bill text' in overview.lower():
                        bill_info['problematic_fields'].append('summary_overview')
                    
                    if detailed and 'full bill text' in detailed.lower():
                        bill_info['problematic_fields'].append('summary_detailed')
                    
                    if tweet and 'full bill text' in tweet.lower():
                        bill_info['problematic_fields'].append('summary_tweet')
                    
                    if bill_info['problematic_fields']:
                        problematic_bills.append(bill_info)
        
        return problematic_bills
        
    except Exception as e:
        logger.error(f"Error finding bills with 'full bill text' phrases: {e}")
        return []

def fetch_bill_with_text(bill_info):
    """Fetch bill with full text from Congress API."""
    try:
        logger.info(f"Fetching full text for bill {bill_info['bill_id']}")
        
        # Get API key
        api_key = os.environ.get('CONGRESS_API_KEY')
        if not api_key:
            logger.error("CONGRESS_API_KEY environment variable not set.")
            return None
            
        # Fetch bill text
        full_text, text_format = fetch_bill_text_from_api(
            bill_info['congress_session'],
            bill_info['bill_type'],
            bill_info['bill_number'],
            api_key
        )
        
        if not full_text:
            logger.warning(f"No full text available for bill {bill_info['bill_id']}")
            return None
            
        # Get current bill data
        bill = get_bill_by_slug(bill_info['website_slug'])
        if not bill:
            # Fallback to get by bill_id
            bill = get_bill_by_id(bill_info['bill_id'])
            
        if not bill:
            logger.error(f"Could not retrieve bill data for {bill_info['bill_id']}")
            return None
            
        # Add full text to bill data
        bill['full_text'] = full_text
        bill['text_format'] = text_format
        
        logger.info(f"Successfully fetched full text for bill {bill_info['bill_id']} ({len(full_text)} characters)")
        return bill
        
    except Exception as e:
        logger.error(f"Error fetching full text for bill {bill_info['bill_id']}: {e}")
        return None

def regenerate_summary(bill):
    """Regenerate summary for a bill with full text."""
    try:
        logger.info(f"Regenerating summary for bill {bill['bill_id']}")
        
        # Generate new summary
        new_summary = summarize_bill_enhanced(bill)
        
        if not new_summary:
            logger.error(f"Failed to generate summary for bill {bill['bill_id']}")
            return None
            
        logger.info(f"Successfully regenerated summary for bill {bill['bill_id']}")
        return new_summary
        
    except Exception as e:
        logger.error(f"Error regenerating summary for bill {bill['bill_id']}: {e}")
        return None

def update_bill_summary_in_db(bill_id, summary):
    """Update bill summaries in the database."""
    try:
        success = update_bill_summaries(
            bill_id,
            summary.get('overview', ''),
            summary.get('detailed', ''),
            summary.get('tweet', ''),
            summary.get('term_dictionary', '[]')
        )
        
        if success:
            logger.info(f"Successfully updated summaries in database for bill {bill_id}")
            return True
        else:
            logger.error(f"Failed to update summaries in database for bill {bill_id}")
            return False
            
    except Exception as e:
        logger.error(f"Error updating database for bill {bill_id}: {e}")
        return False

def main():
    logger.info("Starting validation and fixing of bill summaries...")
    
    # Check required environment variables
    if not os.environ.get('DATABASE_URL'):
        logger.error("DATABASE_URL environment variable not set.")
        return 1
        
    if not os.environ.get('CONGRESS_API_KEY'):
        logger.error("CONGRESS_API_KEY environment variable not set.")
        return 1
    
    # Find all bills with "full bill text" phrases
    problematic_bills = find_bills_with_full_bill_text_phrases()
    
    if not problematic_bills:
        logger.info("✅ No bills with 'full bill text' phrases found!")
        return 0
    
    logger.info(f"Found {len(problematic_bills)} bills with 'full bill text' phrases")
    
    # Process each bill
    success_count = 0
    failure_count = 0
    
    for i, bill_info in enumerate(problematic_bills, 1):
        logger.info(f"Processing bill {i}/{len(problematic_bills)}: {bill_info['bill_id']}")
        logger.info(f"  Problematic fields: {', '.join(bill_info['problematic_fields'])}")
        
        try:
            # Fetch bill with full text
            bill = fetch_bill_with_text(bill_info)
            if not bill:
                logger.error(f"Skipping {bill_info['bill_id']} - could not fetch full text")
                failure_count += 1
                continue
                
            # Regenerate summary
            new_summary = regenerate_summary(bill)
            if not new_summary:
                logger.error(f"Skipping {bill_info['bill_id']} - could not regenerate summary")
                failure_count += 1
                continue
                
            # Check if regenerated summary still contains "full bill text" phrases
            summary_fields = [new_summary.get("overview", ""), new_summary.get("detailed", ""), new_summary.get("tweet", "")]
            if any("full bill text" in field.lower() for field in summary_fields):
                logger.error(f"Skipping {bill_info['bill_id']} - regenerated summary still contains 'full bill text' phrase")
                failure_count += 1
                continue
                
            # Update database
            if update_bill_summary_in_db(bill_info['bill_id'], new_summary):
                success_count += 1
                logger.info(f"✅ Successfully processed {bill_info['bill_id']}")
            else:
                failure_count += 1
                logger.error(f"❌ Failed to update database for {bill_info['bill_id']}")
                
            # Rate limiting to avoid API limits
            if i < len(problematic_bills):  # Don't sleep after the last item
                time.sleep(1)
                
        except Exception as e:
            failure_count += 1
            logger.error(f"Error processing {bill_info['bill_id']}: {e}")
    
    # Report results
    logger.info("=" * 80)
    logger.info("SUMMARY REPORT")
    logger.info("=" * 80)
    logger.info(f"Total bills processed: {len(problematic_bills)}")
    logger.info(f"Successfully processed: {success_count}")
    logger.info(f"Failures: {failure_count}")
    logger.info("=" * 80)
    
    if failure_count == 0:
        logger.info("🎉 All bills with problematic summaries have been successfully fixed!")
        return 0
    else:
        logger.warning(f"⚠️  {failure_count} bills failed to process. Check logs above for details.")
        return 1

if __name__ == "__main__":
    sys.exit(main())