#!/usr/bin/env python3
"""
Debug script to see what the summarizer is actually returning for these bills.
"""

import os
import sys
import json
import logging
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from processors.summarizer import summarize_bill_enhanced

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Test bill data for sres428-119
test_bill = {
    'bill_id': 'sres428-119',
    'title': 'A resolution recognizing Hispanic Heritage Month and celebrating the heritage and culture of Latinos in the United States and the immense contributions of Latinos to the United States.',
    'short_title': None,
    'status': 'passed_senate',
    'congress_session': 119,
    'date_introduced': '2025-09-30',
    'latest_action': 'Submitted in the Senate, considered, and agreed to without amendment and with a preamble by Unanimous Consent.',
    'full_text': ''  # No full text available
}

logger.info("Testing summarizer with bill that has no full text...")
logger.info(f"Bill: {test_bill['bill_id']}")
logger.info(f"Title: {test_bill['title']}")
logger.info("")

try:
    result = summarize_bill_enhanced(test_bill)
    
    logger.info("="*60)
    logger.info("SUMMARIZER RESULT:")
    logger.info("="*60)
    logger.info(json.dumps(result, indent=2, ensure_ascii=False))
    logger.info("")
    logger.info("Field lengths:")
    for key, value in result.items():
        logger.info(f"  {key}: {len(value)} chars")
        if len(value) > 0 and len(value) < 500:
            logger.info(f"    Content: {value[:200]}...")
    
except Exception as e:
    logger.error(f"Error: {e}")
    import traceback
    logger.error(traceback.format_exc())