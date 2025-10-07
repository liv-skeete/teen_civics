#!/usr/bin/env python3
"""
Script to reprocess ALL old bills in the database to give them the new structured format
with emoji headers. This will update all bills to use the enhanced summarizer.
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

def get_all_bill_ids():
    """Fetch all bill IDs from the database."""
    if not is_postgres_available():
        logger.error("PostgreSQL database not available")
        return []
    
    try:
        with postgres_connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT bill_id FROM bills 
                    ORDER BY date_processed DESC
                """)
                return [row[0] for row in cursor.fetchall()]
    except Exception as e:
        logger.error(f"Error fetching bill IDs: {e}")
        return []

def update_bill_summary(bill_id: str, summaries: dict, status: str = None):
    """Update bill summaries and status in database with ALL fields."""
    if not is_postgres_available():
        logger.error("PostgreSQL database not available")
        return False
    
    try:
        with postgres_connect() as conn:
            with conn.cursor() as cursor:
                # Verify all required fields are present
                required_fields = ['tweet', 'overview', 'detailed', 'long', 'term_dictionary']
                for field in required_fields:
                    if field not in summaries:
                        logger.error(f"Missing required field: {field}")
                        return False
                
                if status:
                    cursor.execute("""
                        UPDATE bills
                        SET summary_tweet = %s,
                            summary_overview = %s,
                            summary_detailed = %s,
                            summary_long = %s,
                            term_dictionary = %s,
                            status = %s,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE bill_id = %s
                    """, (
                        summaries['tweet'],
                        summaries['overview'],
                        summaries['detailed'],
                        summaries['long'],
                        summaries['term_dictionary'],
                        status,
                        bill_id
                    ))
                else:
                    cursor.execute("""
                        UPDATE bills
                        SET summary_tweet = %s,
                            summary_overview = %s,
                            summary_detailed = %s,
                            summary_long = %s,
                            term_dictionary = %s,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE bill_id = %s
                    """, (
                        summaries['tweet'],
                        summaries['overview'],
                        summaries['detailed'],
                        summaries['long'],
                        summaries['term_dictionary'],
                        bill_id
                    ))
                
                if cursor.rowcount > 0:
                    if status:
                        logger.info(f"✓ Updated summaries and status for {bill_id}")
                        logger.info(f"  - status: {status}")
                    else:
                        logger.info(f"✓ Updated summaries for {bill_id}")
                    logger.info(f"  - summary_tweet: {len(summaries['tweet'])} chars")
                    logger.info(f"  - summary_overview: {len(summaries['overview'])} chars")
                    logger.info(f"  - summary_detailed: {len(summaries['detailed'])} chars")
                    logger.info(f"  - summary_long: {len(summaries['long'])} chars")
                    logger.info(f"  - term_dictionary: {len(summaries['term_dictionary'])} chars")
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
        
        # Verify all required fields are present
        required_fields = ['tweet', 'overview', 'detailed', 'long', 'term_dictionary']
        for field in required_fields:
            if field not in summaries:
                logger.error(f"Missing required field in summaries: {field}")
                return False
        
        # Log summary lengths
        logger.info(f"Generated summaries:")
        logger.info(f"  - tweet: {len(summaries['tweet'])} chars")
        logger.info(f"  - overview: {len(summaries['overview'])} chars")
        logger.info(f"  - detailed: {len(summaries['detailed'])} chars")
        logger.info(f"  - long: {len(summaries['long'])} chars")
        logger.info(f"  - term_dictionary: {len(summaries['term_dictionary'])} chars")
        
        # Check if summaries have proper formatting (emojis)
        detailed = summaries['detailed']
        has_emojis = any(emoji in detailed for emoji in ['🔎', '🔑', '🛠️', '⚖️', '📌', '👉'])
        logger.info(f"  - Has emoji headers: {has_emojis}")
        
        # Validate summary lengths
        if len(summaries['tweet']) < 50:
            logger.warning(f"⚠️  Tweet summary is too short ({len(summaries['tweet'])} chars)")
        if len(summaries['overview']) < 100:
            logger.warning(f"⚠️  Overview is too short ({len(summaries['overview'])} chars)")
        if len(summaries['detailed']) < 300:
            logger.warning(f"⚠️  Detailed summary is too short ({len(summaries['detailed'])} chars)")
        if len(summaries['long']) < 400:
            logger.warning(f"⚠️  Long summary is too short ({len(summaries['long'])} chars)")
        
        if not has_emojis:
            logger.warning("⚠️  Detailed summary missing emoji headers")
        
    except Exception as e:
        logger.error(f"Error generating summaries: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False
    
    # Update database
    try:
        logger.info("Updating database...")
        # Get the status from the fresh bill data
        bill_status = fresh_bill.get('status')
        success = update_bill_summary(bill_id, summaries, bill_status)
        if not success:
            logger.error(f"✗ Failed to update database for {bill_id}")
            return False
            
    except Exception as e:
        logger.error(f"Error updating database: {e}")
        return False
    
    return True

def main():
    """Main function to reprocess all old bills."""
    logger.info("="*60)
    logger.info("REPROCESSING ALL OLD BILLS - ENHANCED FORMAT")
    logger.info("="*60)
    logger.info("This will update ALL bills with the new structured format")
    logger.info("with emoji headers and proper section organization")
    logger.info("")
    
    # Check database connection
    if not is_postgres_available():
        logger.error("PostgreSQL database not available. Check your DATABASE_URL in .env")
        return 1
    
    logger.info("✓ PostgreSQL database connection verified")
    logger.info("")
    
    # Get all bill IDs
    bill_ids = get_all_bill_ids()
    if not bill_ids:
        logger.error("No bills found in database")
        return 1
    
    logger.info(f"Found {len(bill_ids)} bills to reprocess")
    logger.info("")
    
    # Process each bill
    results = {}
    for bill_id in bill_ids:
        try:
            success = reprocess_bill(bill_id)
            results[bill_id] = success
        except Exception as e:
            logger.error(f"Unexpected error processing {bill_id}: {e}")
            import traceback
            logger.error(traceback.format_exc())
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