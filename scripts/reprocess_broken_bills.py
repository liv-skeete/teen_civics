#!/usr/bin/env python3
"""
Script to reprocess specific bills with broken summaries.
Targets bills sres428-119 and sres429-119 which have truncated summaries.
"""

import os
import sys
import logging
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from database.connection import postgres_connect, is_postgres_available
from processors.summarizer import summarize_bill_enhanced
from fetchers.congress_fetcher import _process_bill_data, _enrich_bill_with_text

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

BROKEN_BILLS = [
    "sres428-119",
    "sres429-119"
]

def get_bill_from_db(bill_id: str):
    """Fetch bill data from database."""
    if not is_postgres_available():
        logger.error("PostgreSQL database not available")
        return None
    
    try:
        with postgres_connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT bill_id, title, short_title, status, source_url, 
                           congress_session, date_introduced, website_slug
                    FROM bills 
                    WHERE bill_id = %s
                """, (bill_id,))
                row = cursor.fetchone()
                
                if not row:
                    logger.warning(f"Bill {bill_id} not found in database")
                    return None
                
                return {
                    'bill_id': row[0],
                    'title': row[1],
                    'short_title': row[2],
                    'status': row[3],
                    'source_url': row[4],
                    'congress_session': row[5],
                    'date_introduced': row[6],
                    'website_slug': row[7]
                }
    except Exception as e:
        logger.error(f"Error fetching bill {bill_id} from database: {e}")
        return None

def update_bill_summary(bill_id: str, summaries: dict):
    """Update bill summaries in database."""
    if not is_postgres_available():
        logger.error("PostgreSQL database not available")
        return False
    
    try:
        with postgres_connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    UPDATE bills 
                    SET summary_tweet = %s,
                        summary_long = %s,
                        summary_overview = %s,
                        summary_detailed = %s,
                        term_dictionary = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE bill_id = %s
                """, (
                    summaries.get('tweet', ''),
                    summaries.get('long', ''),
                    summaries.get('overview', ''),
                    summaries.get('detailed', ''),
                    summaries.get('term_dictionary', '[]'),
                    bill_id
                ))
                
                if cursor.rowcount > 0:
                    logger.info(f"✓ Updated summaries for {bill_id}")
                    return True
                else:
                    logger.warning(f"No rows updated for {bill_id}")
                    return False
                    
    except Exception as e:
        logger.error(f"Error updating bill {bill_id}: {e}")
        return False

def fetch_bill_from_api(congress: str, bill_type: str, bill_number: str):
    """Fetch bill details from Congress.gov API."""
    api_key = os.getenv('CONGRESS_API_KEY')
    if not api_key:
        logger.error("CONGRESS_API_KEY not found in environment")
        return None
    
    base_url = "https://api.congress.gov/v3/"
    bill_endpoint = f"{base_url}bill/{congress}/{bill_type}/{bill_number}"
    
    headers = {"X-API-Key": api_key}
    params = {"format": "json"}
    
    try:
        logger.info(f"Fetching bill from: {bill_endpoint}")
        response = requests.get(bill_endpoint, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        bill_raw = data.get('bill', {})
        
        if not bill_raw:
            logger.error("No bill data in API response")
            return None
        
        # Process the bill data
        bill_data = _process_bill_data(bill_raw)
        if not bill_data:
            logger.error("Failed to process bill data")
            return None
        
        # Enrich with full text (no character limit for reprocessing)
        bill_data = _enrich_bill_with_text(bill_data, text_chars=200000)
        
        return bill_data
        
    except Exception as e:
        logger.error(f"Error fetching bill from API: {e}")
        return None

def reprocess_bill(bill_id: str):
    """Reprocess a single bill with fresh summaries."""
    logger.info(f"\n{'='*60}")
    logger.info(f"Reprocessing bill: {bill_id}")
    logger.info(f"{'='*60}")
    
    # Parse bill ID: sres428-119 -> type=sres, number=428, congress=119
    try:
        parts = bill_id.split('-')
        congress = parts[1] if len(parts) > 1 else '119'
        
        bill_part = parts[0]
        # Find where digits start
        bill_type = ''
        bill_number = ''
        for i, char in enumerate(bill_part):
            if char.isdigit():
                bill_type = bill_part[:i]
                bill_number = bill_part[i:]
                break
        
        logger.info(f"Parsed: type={bill_type}, number={bill_number}, congress={congress}")
        
    except Exception as e:
        logger.error(f"Error parsing bill ID {bill_id}: {e}")
        return False
    
    # Fetch fresh bill details from Congress API
    try:
        logger.info("Fetching fresh bill details from Congress API...")
        fresh_bill = fetch_bill_from_api(congress, bill_type, bill_number)
        
        if not fresh_bill:
            logger.error(f"Could not fetch fresh details for {bill_id}")
            return False
            
        logger.info(f"Bill title: {fresh_bill.get('title', 'N/A')}")
        logger.info(f"Fetched bill with {len(fresh_bill.get('full_text', ''))} chars of full text")
        
    except Exception as e:
        logger.error(f"Error fetching fresh bill details: {e}")
        return False
    
    # Generate new summaries using Claude 3.5 Sonnet
    try:
        logger.info("Generating new summaries with Claude 3.5 Sonnet...")
        summaries = summarize_bill_enhanced(fresh_bill)
        
        # Log summary lengths
        logger.info(f"Generated summaries:")
        logger.info(f"  - Tweet: {len(summaries.get('tweet', ''))} chars")
        logger.info(f"  - Overview: {len(summaries.get('overview', ''))} chars")
        logger.info(f"  - Detailed: {len(summaries.get('detailed', ''))} chars")
        logger.info(f"  - Long: {len(summaries.get('long', ''))} chars")
        logger.info(f"  - Term dictionary: {len(summaries.get('term_dictionary', '[]'))} chars")
        
        # Check if summaries have proper formatting (emojis)
        detailed = summaries.get('detailed', '')
        has_emojis = any(emoji in detailed for emoji in ['🔎', '🔑', '🛠️', '⚖️', '📌', '👉'])
        logger.info(f"  - Has emoji headers: {has_emojis}")
        
        if len(summaries.get('long', '')) < 500:
            logger.warning(f"⚠️  Long summary is suspiciously short ({len(summaries.get('long', ''))} chars)")
        
        if not has_emojis:
            logger.warning("⚠️  Detailed summary missing emoji headers")
        
    except Exception as e:
        logger.error(f"Error generating summaries: {e}")
        return False
    
    # Update database
    try:
        logger.info("Updating database...")
        success = update_bill_summary(bill_id, summaries)
        if success:
            logger.info(f"✓ Successfully reprocessed {bill_id}")
            return True
        else:
            logger.error(f"✗ Failed to update database for {bill_id}")
            return False
            
    except Exception as e:
        logger.error(f"Error updating database: {e}")
        return False

def main():
    """Main function to reprocess all broken bills."""
    logger.info("="*60)
    logger.info("REPROCESSING BROKEN BILLS")
    logger.info("="*60)
    logger.info(f"Target bills: {', '.join(BROKEN_BILLS)}")
    logger.info("")
    
    # Check database connection
    if not is_postgres_available():
        logger.error("PostgreSQL database not available. Check your DATABASE_URL in .env")
        return 1
    
    logger.info("✓ PostgreSQL database connection verified")
    logger.info("")
    
    # Process each bill
    results = {}
    for bill_id in BROKEN_BILLS:
        try:
            success = reprocess_bill(bill_id)
            results[bill_id] = success
        except Exception as e:
            logger.error(f"Unexpected error processing {bill_id}: {e}")
            results[bill_id] = False
    
    # Summary
    logger.info("\n" + "="*60)
    logger.info("REPROCESSING SUMMARY")
    logger.info("="*60)
    
    successful = sum(1 for v in results.values() if v)
    failed = len(results) - successful
    
    for bill_id, success in results.items():
        status = "✓ SUCCESS" if success else "✗ FAILED"
        logger.info(f"{bill_id}: {status}")
    
    logger.info("")
    logger.info(f"Total: {len(results)} bills")
    logger.info(f"Successful: {successful}")
    logger.info(f"Failed: {failed}")
    
    return 0 if failed == 0 else 1

if __name__ == "__main__":
    sys.exit(main())