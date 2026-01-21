#!/usr/bin/env python3
"""
Script to update the database with the regenerated summary for bill HR3872-119.
"""

import sys
import os
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Load environment variables
from dotenv import load_dotenv
load_dotenv(project_root / '.env')

from src.database.db_utils import get_bill_by_id
from src.fetchers.congress_fetcher import fetch_bill_text_from_api
from src.processors.summarizer import summarize_bill_enhanced
import psycopg2
from src.database.connection import postgres_connect
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def update_bill_summaries_in_db(bill_id: str, summaries: dict) -> bool:
    """
    Update the bill summaries in the database.
    """
    try:
        with postgres_connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute('''
                UPDATE bills
                SET summary_overview = %s,
                    summary_detailed = %s,
                    summary_tweet = %s,
                    term_dictionary = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE bill_id = %s
                ''', (
                    summaries.get('overview'),
                    summaries.get('detailed'),
                    summaries.get('tweet'),
                    summaries.get('term_dictionary'),
                    bill_id
                ))
                
                if cursor.rowcount == 1:
                    logger.info(f"Successfully updated summaries for bill {bill_id}")
                    return True
                else:
                    logger.error(f"Failed to update bill {bill_id}: no rows affected")
                    return False
    except Exception as e:
        logger.error(f"Error updating summaries for {bill_id}: {e}")
        return False

def main():
    bill_id = 'hr3872-119'
    print(f"Updating summary for bill {bill_id}...")
    
    # Check if DATABASE_URL is set
    if not os.environ.get('DATABASE_URL'):
        print("❌ DATABASE_URL environment variable not set.")
        print("Please check your .env file or environment configuration.")
        return
    
    # Get the existing bill data
    bill_data = get_bill_by_id(bill_id)
    
    if not bill_data:
        print(f"❌ Bill {bill_id} not found in database.")
        return
    
    print("✅ Bill found in database!")
    
    # Extract congress, bill_type, and bill_number from bill_id
    # bill_id format: hr3872-119
    parts = bill_id.replace('hr', '').split('-')
    bill_number = parts[0]
    congress = parts[1]
    bill_type = 'hr'
    
    print(f"国会: {congress}, 类型: {bill_type}, 编号: {bill_number}")
    
    # Try to fetch the full text using the API
    api_key = os.environ.get('CONGRESS_API_KEY')
    if not api_key:
        print("❌ CONGRESS_API_KEY environment variable not set.")
        return
    
    print("🔄 Fetching full bill text from Congress.gov API...")
    try:
        full_text, format_type = fetch_bill_text_from_api(
            congress=congress,
            bill_type=bill_type,
            bill_number=bill_number,
            api_key=api_key
        )
        
        if full_text and len(full_text.strip()) > 100:  # Basic validity check
            print(f"✅ Successfully fetched bill text ({len(full_text)} characters) in {format_type} format")
        else:
            print("❌ Failed to fetch valid bill text from Congress.gov API")
            print("   This may be because the bill text is not yet available or accessible.")
            return
    except Exception as e:
        print(f"❌ Error fetching bill text: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # Create a bill object for summarization
    bill_for_summarization = {
        "bill_id": bill_id,
        "title": bill_data.get("title", ""),
        "introduced_date": bill_data.get("date_introduced", ""),
        "latest_action": bill_data.get("raw_latest_action", ""),
        "status": bill_data.get("status", ""),
        "congress": congress,
        "bill_type": bill_type,
        "bill_number": bill_number,
        "full_text": full_text,
        "text_format": format_type
    }
    
    # Generate new summaries
    print("🔄 Generating new summaries...")
    try:
        summaries = summarize_bill_enhanced(bill_for_summarization)
        
        if summaries:
            print("✅ New summaries generated successfully!")
            print("\n=== NEW SUMMARY TWEET ===")
            tweet_summary = summaries.get('tweet', 'N/A')
            print(tweet_summary)
            print(f"\nLength: {len(tweet_summary)} characters")
            
            print("\n=== NEW SUMMARY OVERVIEW ===")
            overview_summary = summaries.get('overview', 'N/A')
            print(overview_summary)
            print(f"\nLength: {len(overview_summary)} characters")
            
            print("\n=== NEW SUMMARY DETAILED ===")
            detailed_summary = summaries.get('detailed', 'N/A')
            # Print just the first 500 characters for brevity
            print(detailed_summary[:500] + "..." if len(detailed_summary) > 500 else detailed_summary)
            print(f"\nLength: {len(detailed_summary)} characters")
            
            # Update the database with new summaries
            print("\n🔄 Updating database with new summaries...")
            if update_bill_summaries_in_db(bill_id, summaries):
                print("✅ Database updated successfully!")
            else:
                print("❌ Failed to update database.")
                return
        else:
            print("❌ Failed to generate summaries")
            return
            
    except Exception as e:
        print(f"❌ Error generating summaries: {e}")
        import traceback
        traceback.print_exc()
        return

if __name__ == "__main__":
    main()