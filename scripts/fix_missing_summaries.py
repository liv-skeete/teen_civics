#!/usr/bin/env python3
"""
Script to fix missing summaries for bills sres428-119 and sres429-119.
This script fetches the full bill text and generates proper summaries using the summarizer.
"""

import os
import sys
import logging
from dotenv import load_dotenv

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from database.db_utils import get_bill_by_id, update_bill_summaries
from processors.summarizer import summarize_bill_enhanced

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

def fix_bill_summary(bill_id: str) -> bool:
    """
    Fix missing summary for a specific bill by:
    1. Fetching the bill from database
    2. Fetching full text from Congress API
    3. Generating summaries using the summarizer
    4. Updating the database
    
    Args:
        bill_id: The bill ID to fix (e.g., 'sres428-119')
        
    Returns:
        bool: True if successful, False otherwise
    """
    logger.info(f"Processing bill: {bill_id}")
    
    # Step 1: Get bill from database
    logger.info(f"Fetching bill {bill_id} from database...")
    bill = get_bill_by_id(bill_id)
    
    if not bill:
        logger.error(f"Bill {bill_id} not found in database")
        return False
    
    logger.info(f"Found bill in database: {bill.get('title', 'No title')}")
    
    # Step 2: Fetch full bill text from Congress API
    logger.info(f"Fetching full text from Congress API...")
    try:
        # Import the function to fetch bill with text
        from fetchers.congress_fetcher import _enrich_bill_with_text, _process_bill_data
        
        # We need to fetch the bill data fresh from the API
        # Extract congress and bill type/number from bill_id
        import re
        match = re.match(r'([a-z]+)(\d+)-(\d+)', bill_id)
        if not match:
            logger.error(f"Invalid bill_id format: {bill_id}")
            return False
        
        bill_type, bill_number, congress = match.groups()
        
        # Fetch from Congress API
        import requests
        CONGRESS_API_KEY = os.getenv('CONGRESS_API_KEY')
        if not CONGRESS_API_KEY:
            logger.error("CONGRESS_API_KEY not found in environment")
            return False
        
        # Build API URL for specific bill
        api_url = f"https://api.congress.gov/v3/bill/{congress}/{bill_type}/{bill_number}"
        headers = {"X-API-Key": CONGRESS_API_KEY}
        params = {"format": "json"}
        
        logger.info(f"Fetching from: {api_url}")
        response = requests.get(api_url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        
        api_data = response.json()
        bill_data = api_data.get('bill', {})
        
        if not bill_data:
            logger.error(f"No bill data returned from API for {bill_id}")
            return False
        
        # Process the bill data to get it in the right format
        from fetchers.congress_fetcher import _process_bill_data, _enrich_bill_with_text
        processed_bill = _process_bill_data(bill_data)
        
        # Enrich with full text
        enriched_bill = _enrich_bill_with_text(processed_bill, text_chars=50000)
        
        if not enriched_bill.get('full_text'):
            logger.warning(f"No full text available for {bill_id}, using metadata only")
            enriched_bill = processed_bill
        
    except Exception as e:
        logger.error(f"Error fetching bill text from API: {e}")
        logger.info("Attempting to generate summaries from existing metadata...")
        enriched_bill = bill
    
    # Step 3: Generate summaries using the summarizer
    logger.info(f"Generating summaries for {bill_id}...")
    try:
        summaries = summarize_bill_enhanced(enriched_bill)
        
        if not summaries:
            logger.error(f"Failed to generate summaries for {bill_id}")
            return False
        
        logger.info(f"Generated summaries:")
        logger.info(f"  - overview: {len(summaries.get('overview', ''))} chars")
        logger.info(f"  - detailed: {len(summaries.get('detailed', ''))} chars")
        logger.info(f"  - tweet: {len(summaries.get('tweet', ''))} chars")
        logger.info(f"  - term_dictionary: {len(summaries.get('term_dictionary', ''))} chars")
        
    except Exception as e:
        logger.error(f"Error generating summaries: {e}")
        return False
    
    # Step 4: Update the database
    logger.info(f"Updating database for {bill_id}...")
    try:
        # If overview or detailed are empty, use tweet as fallback for overview
        overview = summaries.get('overview')
        detailed = summaries.get('detailed')
        tweet = summaries.get('tweet')
        
        if not overview and tweet:
            overview = tweet
            logger.info(f"Using tweet as overview fallback")
        
        if not detailed and tweet:
            detailed = f"This resolution {tweet.lower()}"
            logger.info(f"Using tweet-based detailed fallback")
        
        success = update_bill_summaries(
            bill_id=bill_id,
            summary_overview=overview,
            summary_detailed=detailed,
            term_dictionary=summaries.get('term_dictionary'),
            summary_long=detailed  # Use detailed as long summary
        )
        
        if success:
            logger.info(f"✅ Successfully updated summaries for {bill_id}")
            return True
        else:
            logger.error(f"Failed to update database for {bill_id}")
            return False
            
    except Exception as e:
        logger.error(f"Error updating database: {e}")
        return False

def main():
    """Main function to fix missing summaries for both bills."""
    logger.info("=" * 60)
    logger.info("Starting missing summaries fix script")
    logger.info("=" * 60)
    
    bills_to_fix = ['sres428-119', 'sres429-119']
    
    results = {}
    for bill_id in bills_to_fix:
        logger.info(f"\n{'=' * 60}")
        logger.info(f"Processing: {bill_id}")
        logger.info(f"{'=' * 60}")
        
        success = fix_bill_summary(bill_id)
        results[bill_id] = success
        
        if success:
            logger.info(f"✅ {bill_id}: SUCCESS")
        else:
            logger.error(f"❌ {bill_id}: FAILED")
    
    # Print summary
    logger.info(f"\n{'=' * 60}")
    logger.info("SUMMARY")
    logger.info(f"{'=' * 60}")
    
    for bill_id, success in results.items():
        status = "✅ SUCCESS" if success else "❌ FAILED"
        logger.info(f"{bill_id}: {status}")
    
    all_success = all(results.values())
    if all_success:
        logger.info("\n🎉 All bills processed successfully!")
        return 0
    else:
        logger.error("\n⚠️  Some bills failed to process")
        return 1

if __name__ == "__main__":
    sys.exit(main())