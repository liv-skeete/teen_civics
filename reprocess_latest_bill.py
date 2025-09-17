#!/usr/bin/env python3
"""
Script to reprocess the latest bill with the new enhanced summary format.
This will update the existing bill with summary_overview, summary_detailed, and term_dictionary.
"""

import os
import sys
import logging
import json
from typing import Dict, Any

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def main():
    """Reprocess the latest bill with enhanced summary format"""
    try:
        logger.info("Starting reprocessing of latest bill...")
        
        # Import required modules
        from src.database.db import get_latest_bill, update_bill_summaries
        from src.processors.summarizer import summarize_bill_enhanced
        
        # Get the latest bill from database
        latest_bill = get_latest_bill()
        if not latest_bill:
            logger.error("No bills found in database")
            return 1
            
        bill_id = latest_bill['bill_id']
        logger.info(f"Reprocessing bill: {bill_id}")
        
        # Use the existing bill data for regenerating summaries
        bill_data = latest_bill
        logger.info(f"Using existing bill data: {bill_data.get('title', 'No title')}")
            
        # Generate enhanced summaries
        logger.info("Generating enhanced summaries...")
        enhanced_summary = summarize_bill_enhanced(bill_data)
        
        overview = enhanced_summary.get("overview", "").strip()
        detailed = enhanced_summary.get("detailed", "").strip()
        term_dictionary = enhanced_summary.get("term_dictionary", "").strip()
        summary_long = enhanced_summary.get("long", "").strip()
        
        if not overview or not detailed:
            logger.error("Failed to generate valid enhanced summaries")
            return 1
            
        logger.info(f"Generated overview ({len(overview)} chars)")
        logger.info(f"Generated detailed summary ({len(detailed)} chars)")
        logger.info(f"Generated term dictionary ({len(term_dictionary)} chars)")
        
        # Update the database
        logger.info("Updating database with enhanced summaries...")
        success = update_bill_summaries(
            bill_id=bill_id,
            summary_overview=overview,
            summary_detailed=detailed,
            term_dictionary=term_dictionary,
            summary_long=summary_long
        )
        
        if success:
            logger.info(f"✅ Successfully updated bill {bill_id} with enhanced summaries")
            
            # Print sample output for verification
            logger.info("=== SAMPLE OUTPUT ===")
            logger.info(f"Overview: {overview[:200]}...")
            logger.info(f"Detailed: {detailed[:200]}...")
            
            # Parse and display term dictionary
            try:
                terms = json.loads(term_dictionary)
                if terms and isinstance(terms, list):
                    logger.info(f"Term Dictionary: {len(terms)} terms defined")
                    for i, term in enumerate(terms[:3]):  # Show first 3 terms
                        logger.info(f"  - {term.get('term', 'N/A')}: {term.get('definition', 'N/A')[:100]}...")
                else:
                    logger.info(f"Term Dictionary: {term_dictionary[:100]}...")
            except:
                logger.info(f"Term Dictionary: {term_dictionary[:100]}...")
            
            return 0
        else:
            logger.error("Failed to update database")
            return 1
            
    except ImportError as e:
        logger.error(f"Import error: {e}")
        return 1
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())