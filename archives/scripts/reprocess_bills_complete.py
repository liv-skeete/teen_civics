#!/usr/bin/env python3
"""
Script to reprocess specific bills with broken summaries.
Targets bills sres428-119 and sres429-119 which have incomplete summary fields.
This script ensures ALL summary fields are populated correctly.
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
                           congress_session, date_introduced, website_slug,
                           summary_tweet, summary_overview, summary_detailed, summary_long
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
                    'website_slug': row[7],
                    'current_summary_tweet': row[8],
                    'current_summary_overview': row[9],
                    'current_summary_detailed': row[10],
                    'current_summary_long': row[11]
                }
    except Exception as e:
        logger.error(f"Error fetching bill {bill_id} from database: {e}")
        return None

def update_bill_summary(bill_id: str, summaries: dict):
    """Update bill summaries in database with ALL fields."""
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

def verify_bill_in_db(bill_id: str):
    """Verify bill summaries in database after update."""
    if not is_postgres_available():
        logger.error("PostgreSQL database not available")
        return False
    
    try:
        with postgres_connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT summary_tweet, summary_overview, summary_detailed, summary_long
                    FROM bills 
                    WHERE bill_id = %s
                """, (bill_id,))
                row = cursor.fetchone()
                
                if not row:
                    logger.error(f"Bill {bill_id} not found in database")
                    return False
                
                tweet, overview, detailed, long_sum = row
                
                logger.info(f"\n{'='*60}")
                logger.info(f"Database verification for {bill_id}:")
                logger.info(f"{'='*60}")
                logger.info(f"  summary_tweet: {len(tweet or '')} chars")
                logger.info(f"  summary_overview: {len(overview or '')} chars")
                logger.info(f"  summary_detailed: {len(detailed or '')} chars")
                logger.info(f"  summary_long: {len(long_sum or '')} chars")
                
                # Check if all fields have content
                all_populated = all([
                    tweet and len(tweet) >= 50,
                    overview and len(overview) >= 100,
                    detailed and len(detailed) >= 300,
                    long_sum and len(long_sum) >= 400
                ])
                
                if all_populated:
                    logger.info("✓ All summary fields properly populated")
                    return True
                else:
                    logger.warning("⚠️  Some summary fields are too short or empty")
                    if not tweet or len(tweet) < 50:
                        logger.warning(f"  - summary_tweet is too short: {len(tweet or '')} chars")
                    if not overview or len(overview) < 100:
                        logger.warning(f"  - summary_overview is too short: {len(overview or '')} chars")
                    if not detailed or len(detailed) < 300:
                        logger.warning(f"  - summary_detailed is too short: {len(detailed or '')} chars")
                    if not long_sum or len(long_sum) < 400:
                        logger.warning(f"  - summary_long is too short: {len(long_sum or '')} chars")
                    return False
                    
    except Exception as e:
        logger.error(f"Error verifying bill {bill_id}: {e}")
        return False

def reprocess_bill(bill_id: str):
    """Reprocess a single bill with fresh summaries."""
    logger.info(f"\n{'='*60}")
    logger.info(f"Reprocessing bill: {bill_id}")
    logger.info(f"{'='*60}")
    
    # First, check current state in database
    current_bill = get_bill_from_db(bill_id)
    if current_bill:
        logger.info("Current database state:")
        logger.info(f"  - summary_tweet: {len(current_bill.get('current_summary_tweet') or '')} chars")
        logger.info(f"  - summary_overview: {len(current_bill.get('current_summary_overview') or '')} chars")
        logger.info(f"  - summary_detailed: {len(current_bill.get('current_summary_detailed') or '')} chars")
        logger.info(f"  - summary_long: {len(current_bill.get('current_summary_long') or '')} chars")
    
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
        success = update_bill_summary(bill_id, summaries)
        if not success:
            logger.error(f"✗ Failed to update database for {bill_id}")
            return False
            
    except Exception as e:
        logger.error(f"Error updating database: {e}")
        return False
    
    # Verify the update
    try:
        logger.info("Verifying database update...")
        verified = verify_bill_in_db(bill_id)
        if verified:
            logger.info(f"✓ Successfully reprocessed and verified {bill_id}")
            return True
        else:
            logger.error(f"✗ Verification failed for {bill_id}")
            return False
            
    except Exception as e:
        logger.error(f"Error verifying database: {e}")
        return False

def main():
    """Main function to reprocess all broken bills."""
    logger.info("="*60)
    logger.info("REPROCESSING BROKEN BILLS - COMPLETE VERSION")
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