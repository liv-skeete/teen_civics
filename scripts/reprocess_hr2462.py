#!/usr/bin/env python3
"""
Reprocess HR.2462 (Black Vulture Relief Act) to regenerate its summary.
This verifies the fix for the "full text needed" placeholder bug.
"""

import sys
sys.path.insert(0, 'src')

from dotenv import load_dotenv
load_dotenv()

from database.db import get_bill_by_id, update_bill_summaries
from processors.summarizer import summarize_bill_enhanced
import json

def main():
    bill_id = "hr2462-119"
    
    print(f"Fetching bill data for {bill_id}...")
    bill = get_bill_by_id(bill_id)
    
    if not bill:
        print(f"ERROR: Bill {bill_id} not found in database")
        return 1
    
    print(f"\nBill found: {bill['title']}")
    print(f"Current summary length: {len(bill.get('summary', ''))}")
    
    # Check if bill has full_text
    has_full_text = bool(bill.get('full_text'))
    print(f"Has full_text: {has_full_text}")
    if has_full_text:
        print(f"Full text length: {len(bill['full_text'])} characters")
    
    print("\n" + "="*80)
    print("REGENERATING SUMMARY...")
    print("="*80 + "\n")
    
    # Regenerate the summary
    summary_result = summarize_bill_enhanced(bill)
    
    if not summary_result:
        print("ERROR: summarize_bill_enhanced returned None")
        return 1
    
    # DEBUG: Show what we actually got
    print(f"\nDEBUG - Result type: {type(summary_result)}")
    print(f"DEBUG - Result keys: {list(summary_result.keys()) if isinstance(summary_result, dict) else 'N/A'}")
    print(f"DEBUG - overview length: {len(summary_result.get('overview', ''))}")
    print(f"DEBUG - long length: {len(summary_result.get('long', ''))}")
    print(f"DEBUG - detailed length: {len(summary_result.get('detailed', ''))}")
    
    # Extract the summary sections
    short_summary = summary_result.get('overview', '')
    long_summary = summary_result.get('long', '')
    detailed_summary = summary_result.get('detailed', '')
    term_dictionary_str = summary_result.get('term_dictionary', '[]')
    
    # Parse key_points from term_dictionary JSON string
    try:
        key_points = json.loads(term_dictionary_str) if term_dictionary_str else []
    except json.JSONDecodeError:
        key_points = []
    
    print("NEW SUMMARY GENERATED:")
    print("\n" + "-"*80)
    print("SHORT SUMMARY:")
    print("-"*80)
    print(short_summary)
    
    print("\n" + "-"*80)
    print("LONG SUMMARY:")
    print("-"*80)
    print(long_summary)
    
    print("\n" + "-"*80)
    print("KEY POINTS:")
    print("-"*80)
    for i, point in enumerate(key_points, 1):
        print(f"{i}. {point}")
    
    # Check for placeholder text
    print("\n" + "="*80)
    print("VERIFICATION:")
    print("="*80)
    
    placeholder_found = False
    if "full text needed" in short_summary.lower():
        print("❌ SHORT SUMMARY still contains 'full text needed' placeholder")
        placeholder_found = True
    else:
        print("✓ SHORT SUMMARY does not contain placeholder text")
    
    if "full text needed" in long_summary.lower():
        print("❌ LONG SUMMARY still contains 'full text needed' placeholder")
        placeholder_found = True
    else:
        print("✓ LONG SUMMARY does not contain placeholder text")
    
    # Check if key_points contain placeholder text (handle both string and dict formats)
    key_points_text = []
    for point in key_points:
        if isinstance(point, dict):
            key_points_text.extend([str(v) for v in point.values()])
        else:
            key_points_text.append(str(point))
    
    if any("full text needed" in text.lower() for text in key_points_text):
        print("❌ KEY POINTS contain 'full text needed' placeholder")
        placeholder_found = True
    else:
        print("✓ KEY POINTS do not contain placeholder text")
    
    if placeholder_found:
        print("\n⚠️  WARNING: Placeholder text still present after fix!")
        return 1
    
    # Update the database
    print("\n" + "="*80)
    print("UPDATING DATABASE...")
    print("="*80)
    
    success = update_bill_summaries(
        bill_id=bill_id,
        summary_overview=short_summary,
        summary_long=long_summary,
        summary_detailed=detailed_summary,
        term_dictionary=term_dictionary_str
    )
    
    if success:
        print("✓ Database updated successfully")
        print("\n✅ SUCCESS: HR.2462 summary regenerated without placeholder text!")
        return 0
    else:
        print("❌ ERROR: Failed to update database")
        return 1

if __name__ == "__main__":
    sys.exit(main())