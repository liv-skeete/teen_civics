#!/usr/bin/env python3
"""
Shared validation logic for bills to ensure quality before posting.
This module consolidates validation rules that were previously scattered
across orchestrator.py and other modules.
"""

import logging
from typing import Dict, Any, List, Optional, Tuple

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Minimum required length for full text to be considered valid
MIN_FULL_TEXT_LENGTH = 100

def validate_bill_data(bill: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Validate that a bill has all required fields populated and content meets quality standards.
    Works with both API-format data (field: 'congress') and DB-format data (field: 'congress_session').
    
    Args:
        bill: Dictionary containing bill data
        
    Returns:
        tuple: (is_valid: bool, reasons: list[str])
    """
    reasons = []
    
    # 1. Title is absolutely required
    title = str(bill.get("title") or "").strip()
    if not title:
        reasons.append("Missing title")
    
    # 2. Bill ID is absolutely required
    bill_id = str(bill.get("bill_id") or "").strip()
    if not bill_id:
        reasons.append("Missing bill_id")
    
    # 3. Congress session — accept either 'congress' (API) or 'congress_session' (DB)
    congress = str(bill.get("congress") or bill.get("congress_session") or "").strip()
    if not congress:
        reasons.append("Missing congress session")

    # 4. Full Text Validation
    full_text = str(bill.get("full_text") or "").strip()
    if not full_text:
        reasons.append("Missing full text")
    elif len(full_text) < MIN_FULL_TEXT_LENGTH:
        reasons.append(f"Full text too short (length={len(full_text)}, min={MIN_FULL_TEXT_LENGTH})")

    # 5. Sponsor Validation
    sponsor_name = str(bill.get("sponsor_name") or "").strip()
    if not sponsor_name:
        reasons.append("Missing sponsor information")

    # 6. (Removed: status=='problematic' check is now ONLY in orchestrator's
    #     FINAL GATE at process_single_bill().  validate_bill_data() should
    #     evaluate legislative completeness, not DB metadata flags.)

    if reasons:
        return False, reasons
    
    return True, []

def is_bill_ready_for_posting(bill: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Comprehensive check to see if a bill is ready for the "published" state.
    Wraps validate_bill_data AND checks for summary/tweet generation success.
    
    Args:
        bill: Dictionary containing bill data including generated summaries
        
    Returns:
        tuple: (is_ready: bool, reason: str)
    """
    # 1. Base data validation
    is_valid_data, reasons = validate_bill_data(bill)
    if not is_valid_data:
        return False, f"Data validation failed: {', '.join(reasons)}"
        
    # 2. Summary Validation
    # Summaries must be present and not contain error placeholders
    overview = str(bill.get("summary_overview") or "").strip()
    detailed = str(bill.get("summary_detailed") or "").strip()
    tweet = str(bill.get("summary_tweet") or "").strip()
    
    if not overview:
        return False, "Missing summary overview"
    if not detailed:
        return False, "Missing detailed summary"
    if not tweet:
        return False, "Missing tweet text"
        
    # Check for failure patterns in summaries
    error_phrases = ["full bill text needed", "no summary available", "error generating summary"]
    combined_summary = (overview + detailed + tweet).lower()
    
    for phrase in error_phrases:
        if phrase in combined_summary:
            return False, f"Summary contains error phrase: '{phrase}'"
            
    # 3. Teen Impact Score (Specific requirement mentioned in instructions implicitly via 'missing info')
    # Use 0 as a valid score, check for None
    score = bill.get("teen_impact_score")
    if score is None:
        return False, "Missing Teen Impact Score"
        
    return True, "Ready for posting"
