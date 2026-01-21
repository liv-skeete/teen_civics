#!/usr/bin/env python3
"""
Script to reprocess H.R. 2184 (Firearm Due Process Protection Act of 2025)
to verify that the database fix produces comprehensive summaries.

This script:
1. Retrieves and displays the old summary (if exists)
2. Deletes the existing H.R. 2184 record from the database
3. Fetches and processes H.R. 2184 fresh using the orchestrator
4. Displays the new summary generated
5. Shows the length of the stored full_text to confirm it was saved
6. Compares old vs new summaries
"""

import os
import sys
import logging

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '.'))

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def main():
    """Main function to reprocess H.R. 2184"""
    
    try:
        # Import required modules
        from src.database.db import get_bill_by_id, init_db, db_connect
        from src.fetchers.congress_fetcher import fetch_bill_text_from_api
        from src.processors.summarizer import summarize_bill_enhanced
        from src.database.db import insert_bill, generate_website_slug, normalize_bill_id
        import os
        
        # Initialize database
        logger.info("🗄️ Initializing database...")
        init_db()
        
        # Bill ID to reprocess
        bill_id = "hr2184-119"
        normalized_id = normalize_bill_id(bill_id)
        
        logger.info(f"📋 Target bill: {normalized_id}")
        logger.info("=" * 80)
        
        # Step 1: Get old summary if exists
        logger.info("\n📖 STEP 1: Retrieving existing bill data...")
        old_bill = get_bill_by_id(normalized_id)
        
        old_summary = None
        old_full_text_length = 0
        
        if old_bill:
            logger.info(f"✅ Found existing record for {normalized_id}")
            old_summary = old_bill.get('summary_detailed', '') or old_bill.get('summary_long', '')
            old_full_text = old_bill.get('full_text') or ''
            old_full_text_length = len(old_full_text) if old_full_text else 0
            
            logger.info(f"\n📊 OLD SUMMARY STATS:")
            logger.info(f"   - Summary length: {len(old_summary)} characters")
            logger.info(f"   - Full text length: {old_full_text_length} characters")
            logger.info(f"\n📝 OLD SUMMARY PREVIEW (first 500 chars):")
            logger.info("-" * 80)
            logger.info(old_summary[:500] if old_summary else "(No summary)")
            logger.info("-" * 80)
        else:
            logger.info(f"ℹ️ No existing record found for {normalized_id}")
        
        # Step 2: Delete existing record
        logger.info(f"\n🗑️ STEP 2: Deleting existing record for {normalized_id}...")
        
        with db_connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute('DELETE FROM bills WHERE bill_id = %s', (normalized_id,))
                deleted_count = cursor.rowcount
                
        if deleted_count > 0:
            logger.info(f"✅ Deleted {deleted_count} record(s)")
        else:
            logger.info("ℹ️ No records to delete")
        
        # Step 3: Fetch fresh bill data
        logger.info(f"\n📥 STEP 3: Fetching fresh data for {normalized_id}...")
        
        # Extract congress and bill number from normalized_id
        import re
        match = re.match(r'([a-z]+)(\d+)-(\d+)', normalized_id)
        if not match:
            logger.error(f"❌ Invalid bill_id format: {normalized_id}")
            return 1
        
        bill_type, bill_number, congress = match.groups()
        
        logger.info(f"   Bill type: {bill_type}")
        logger.info(f"   Bill number: {bill_number}")
        logger.info(f"   Congress: {congress}")
        
        # Get API key
        api_key = os.getenv('CONGRESS_API_KEY')
        if not api_key:
            logger.error("❌ CONGRESS_API_KEY not found in environment")
            return 1
        
        # Fetch bill text from API
        logger.info(f"📥 Fetching bill text from Congress.gov API...")
        full_text, format_type = fetch_bill_text_from_api(congress, bill_type, bill_number, api_key)
        
        if not full_text or len(full_text.strip()) < 100:
            logger.error(f"❌ Failed to fetch sufficient bill text for {normalized_id}")
            logger.error(f"   Text length: {len(full_text) if full_text else 0} characters")
            return 1
        
        logger.info(f"✅ Successfully fetched bill text")
        logger.info(f"   Format: {format_type}")
        logger.info(f"   Text length: {len(full_text)} characters")
        
        # Create bill_data structure
        bill_data = {
            'bill_id': normalized_id,
            'bill_type': bill_type,
            'bill_number': bill_number,
            'congress': congress,
            'title': f"H.R. {bill_number} - Firearm Due Process Protection Act of 2025",
            'short_title': "Firearm Due Process Protection Act of 2025",
            'status': "Introduced",
            'introduced_date': "2025-01-03",
            'source_url': f"https://www.congress.gov/bill/{congress}th-congress/house-bill/{bill_number}",
            'full_text': full_text,
            'text_source': f'api-{format_type}',
            'text_version': 'Introduced',
            'text_received_date': None
        }
        
        # Step 4: Generate new summary
        logger.info(f"\n🧠 STEP 4: Generating new summary with enhanced format...")
        
        summary = summarize_bill_enhanced(bill_data)
        
        if not summary:
            logger.error("❌ Failed to generate summary")
            return 1
        
        logger.info("✅ Summary generated successfully")
        
        new_summary = summary.get('detailed', '') or summary.get('long', '')
        
        logger.info(f"\n📊 NEW SUMMARY STATS:")
        logger.info(f"   - Tweet summary: {len(summary.get('tweet', ''))} characters")
        logger.info(f"   - Long summary: {len(summary.get('long', ''))} characters")
        logger.info(f"   - Overview: {len(summary.get('overview', ''))} characters")
        logger.info(f"   - Detailed summary: {len(summary.get('detailed', ''))} characters")
        logger.info(f"   - Term dictionary: {len(summary.get('term_dictionary', ''))} characters")
        
        logger.info(f"\n📝 NEW DETAILED SUMMARY:")
        logger.info("=" * 80)
        logger.info(new_summary)
        logger.info("=" * 80)
        
        # Step 5: Insert into database
        logger.info(f"\n💾 STEP 5: Inserting bill into database...")
        
        bill_record = {
            "bill_id": normalized_id,
            "title": bill_data.get("title", ""),
            "short_title": bill_data.get("short_title", ""),
            "status": bill_data.get("status", ""),
            "summary_tweet": summary.get("tweet", ""),
            "summary_long": summary.get("long", ""),
            "summary_overview": summary.get("overview", ""),
            "summary_detailed": summary.get("detailed", ""),
            "term_dictionary": summary.get("term_dictionary", ""),
            "congress_session": congress,
            "date_introduced": bill_data.get("introduced_date", ""),
            "source_url": bill_data.get("source_url", ""),
            "website_slug": generate_website_slug(bill_data.get("title", ""), normalized_id),
            "tags": "",
            "tweet_posted": False,
            "tweet_url": None,
            "text_source": bill_data.get("text_source", "api"),
            "text_version": bill_data.get("text_version", "Introduced"),
            "text_received_date": bill_data.get("text_received_date"),
            "processing_attempts": 0,
            "full_text": full_text
        }
        
        if insert_bill(bill_record):
            logger.info("✅ Bill inserted successfully")
        else:
            logger.error("❌ Failed to insert bill")
            return 1
        
        # Step 6: Verify full_text was stored
        logger.info(f"\n🔍 STEP 6: Verifying full_text storage...")
        
        verified_bill = get_bill_by_id(normalized_id)
        if verified_bill:
            stored_full_text = verified_bill.get('full_text', '')
            logger.info(f"✅ Full text stored successfully")
            logger.info(f"   Stored length: {len(stored_full_text)} characters")
            
            if len(stored_full_text) != len(full_text):
                logger.warning(f"⚠️ WARNING: Stored length ({len(stored_full_text)}) != Original length ({len(full_text)})")
        else:
            logger.error("❌ Failed to retrieve bill for verification")
            return 1
        
        # Step 7: Compare old vs new
        logger.info(f"\n📊 STEP 7: COMPARISON SUMMARY")
        logger.info("=" * 80)
        
        if old_summary:
            logger.info(f"OLD Summary Length: {len(old_summary)} characters")
            logger.info(f"NEW Summary Length: {len(new_summary)} characters")
            logger.info(f"Improvement: {len(new_summary) - len(old_summary):+d} characters")
            logger.info(f"\nOLD Full Text: {old_full_text_length} characters")
            logger.info(f"NEW Full Text: {len(stored_full_text)} characters")
            logger.info(f"Improvement: {len(stored_full_text) - old_full_text_length:+d} characters")
            
            # Check for key terms that should be in a comprehensive summary
            key_terms = [
                "NICS", "60 days", "30 days", "expedited hearing",
                "burden of proof", "clear and convincing",
                "attorney fees", "litigation costs", "annual report",
                "18 U.S.C.", "925A", "due process"
            ]
            
            logger.info(f"\n🔍 KEY TERMS CHECK:")
            old_found = sum(1 for term in key_terms if term.lower() in old_summary.lower())
            new_found = sum(1 for term in key_terms if term.lower() in new_summary.lower())
            
            logger.info(f"   OLD summary contains {old_found}/{len(key_terms)} key terms")
            logger.info(f"   NEW summary contains {new_found}/{len(key_terms)} key terms")
            
            if new_found > old_found:
                logger.info(f"   ✅ IMPROVEMENT: +{new_found - old_found} key terms")
            elif new_found == old_found:
                logger.info(f"   ➡️ SAME: No change in key term coverage")
            else:
                logger.info(f"   ⚠️ REGRESSION: -{old_found - new_found} key terms")
        else:
            logger.info("No old summary to compare (this was a new bill)")
            logger.info(f"NEW Summary Length: {len(new_summary)} characters")
            logger.info(f"NEW Full Text: {len(stored_full_text)} characters")
        
        logger.info("=" * 80)
        logger.info("\n✅ Reprocessing complete!")
        
        return 0
        
    except Exception as e:
        logger.error(f"❌ Error during reprocessing: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())