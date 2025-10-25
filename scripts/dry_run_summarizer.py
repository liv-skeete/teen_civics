#!/usr/bin/env python3
"""
Dry-run test script for the summarizer that outputs results to terminal without posting to Twitter.
"""

import os
import sys
import json
import logging
from dotenv import load_dotenv

load_dotenv()

# Add the project root to the Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

from src.processors.summarizer import summarize_bill_enhanced

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Test bill data - you can modify this to test with different bills
test_bill = {
    'bill_id': 'hr1234-119',
    'title': 'Sample Bill for Testing the Summarizer',
    'short_title': None,
    'status': 'introduced',
    'congress_session': 119,
    'date_introduced': '2025-10-20',
    'latest_action': 'Referred to the House Committee on Education',
    'full_text': 'This is sample full text for testing the summarizer. The bill proposes to improve education by authorizing $2.5 billion over 5 years (FY2026-2030) for school infrastructure improvements. Grants will be allocated by formula: 40% based on student enrollment, 60% based on district poverty rate. Eligibility is limited to districts with greater than 40% students qualifying for free/reduced lunch programs. The bill requires infrastructure improvement plans within 90 days of grant approval and technology standards finalized within 180 days. Use of funds is prohibited for athletic facilities, administrative offices, or non-instructional buildings. The bill mandates annual compliance reports to House Education Committee beginning 12 months post-enactment. It also establishes an Office of School Infrastructure within the Department of Education to oversee implementation.'  # Sample full text with specific details
}

def dry_run_summarizer():
    """
    Run the summarizer in dry-run mode, outputting results to terminal without posting to Twitter.
    """
    logger.info("Running summarizer in dry-run mode...")
    logger.info(f"Bill: {test_bill['bill_id']}")
    logger.info(f"Title: {test_bill['title']}")
    logger.info("")
    
    try:
        result = summarize_bill_enhanced(test_bill)
        
        logger.info("="*60)
        logger.info("SUMMARIZER RESULT (DRY RUN):")
        logger.info("="*60)
        
        # Print each field separately for better readability
        for key, value in result.items():
            logger.info(f"\n{key.upper()}:")
            logger.info("-" * len(key))
            if key == "term_dictionary":
                # Pretty print term dictionary
                try:
                    term_dict = json.loads(value)
                    if term_dict:
                        for item in term_dict:
                            logger.info(f"  {item['term']}: {item['definition']}")
                    else:
                        logger.info("  (empty)")
                except json.JSONDecodeError:
                    logger.info(f"  {value}")
            else:
                logger.info(f"  {value}")
        
        logger.info("")
        logger.info("Field lengths:")
        for key, value in result.items():
            logger.info(f"  {key}: {len(str(value))} chars")
            
        # Simulate what would be posted to Twitter
        logger.info("\n" + "="*60)
        logger.info("SIMULATED TWITTER POST:")
        logger.info("="*60)
        tweet_content = result.get("tweet", "")
        logger.info(f"Tweet content ({len(tweet_content)} chars):")
        logger.info(tweet_content)
        logger.info("="*60)
        
    except Exception as e:
        logger.error(f"Error: {e}")
        import traceback
        logger.error(traceback.format_exc())

if __name__ == "__main__":
    dry_run_summarizer()