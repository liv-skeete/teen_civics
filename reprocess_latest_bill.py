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
    """Reprocess the latest bill with enhanced summary format, ensuring the model reads actual bill text."""
    try:
        logger.info("Starting reprocessing of latest bill...")
        
        # Import required modules
        from src.database.db import get_latest_bill, update_bill_summaries
        from src.processors.summarizer import summarize_bill_enhanced
        # Import fetcher utilities to attach the real bill text for this specific bill
        from src.fetchers.congress_fetcher import _enrich_bill_with_text  # internal, acceptable for script use
        import re
        
        # Get the latest bill from database
        latest_bill = get_latest_bill()
        if not latest_bill:
            logger.error("No bills found in database")
            return 1
            
        bill_id = latest_bill.get('bill_id', '')
        logger.info(f"Reprocessing bill: {bill_id}")
        
        # Derive congress/bill_type/bill_number from bill_id if missing so we can fetch text
        bill_data = dict(latest_bill)  # copy
        m = re.match(r'^([a-z\.]+?)(\d+)-(\d+)$', str(bill_id).lower())
        if m:
            bt_raw, num, cong = m.groups()
            bill_data.setdefault('bill_type', bt_raw.replace('.', ''))  # normalize like fetcher
            bill_data.setdefault('bill_number', str(num))
            # fetcher expects integer-ish for 'congress', but handles as JSON fine
            try:
                bill_data.setdefault('congress', int(cong))
            except Exception:
                bill_data.setdefault('congress', cong)
        else:
            logger.warning(f"Could not parse bill_id '{bill_id}' into components; summaries may be speculative without text.")
        
        # Attach full_text by trying all available formats (html/txt/xml/pdf) via fetcher
        try:
            before_len = len(bill_data.get('full_text') or '')
            enriched = _enrich_bill_with_text(bill_data, text_chars=2_000_000)
            after_len = len(enriched.get('full_text') or '')
            bill_data = enriched
            logger.info(f"Full text attached: {before_len} -> {after_len} chars; fmt={bill_data.get('text_format')} url={bill_data.get('text_url')}")
        except Exception as e:
            logger.warning(f"Failed to attach full_text for {bill_id}: {e}")
        
        # Generate enhanced summaries (summarizer will include full_text if present)
        logger.info("Generating enhanced summaries (using full_text if present)...")
        enhanced_summary = summarize_bill_enhanced(bill_data)
        
        overview = (enhanced_summary.get("overview") or "").strip()
        detailed = (enhanced_summary.get("detailed") or "").strip()
        term_dictionary = (enhanced_summary.get("term_dictionary") or "").strip()
        summary_long = (enhanced_summary.get("long") or "").strip()
        
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
            logger.info(f"✅ Successfully updated bill {bill_id} with enhanced summaries (grounded in full text when available)")
            
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
            except Exception:
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