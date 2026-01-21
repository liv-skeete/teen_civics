#!/usr/bin/env python3
"""
Verify that HR.2462 has been updated with the correct summary_detailed field.
"""

import sys
sys.path.insert(0, 'src')

from database.db import get_bill_by_id

def main():
    bill_id = "hr2462-119"
    
    print(f"Fetching bill data for {bill_id}...")
    bill = get_bill_by_id(bill_id)
    
    if not bill:
        print(f"ERROR: Bill {bill_id} not found in database")
        return 1
    
    print(f"\nBill: {bill['title']}")
    print("\n" + "="*80)
    print("DATABASE FIELD VERIFICATION")
    print("="*80)
    
    # Check summary_detailed field
    summary_detailed = bill.get('summary_detailed', '')
    print(f"\n--- summary_detailed field ---")
    print(f"Length: {len(summary_detailed)} characters")
    if summary_detailed:
        print(f"First 300 chars:\n{summary_detailed[:300]}...")
        if "full text needed" in summary_detailed.lower():
            print("❌ CONTAINS PLACEHOLDER TEXT")
        else:
            print("✓ No placeholder text found")
    else:
        print("❌ FIELD IS EMPTY")
    
    # Check summary_long field
    summary_long = bill.get('summary_long', '')
    print(f"\n--- summary_long field ---")
    print(f"Length: {len(summary_long)} characters")
    if summary_long:
        print(f"First 300 chars:\n{summary_long[:300]}...")
        if "full text needed" in summary_long.lower():
            print("❌ CONTAINS PLACEHOLDER TEXT")
        else:
            print("✓ No placeholder text found")
    else:
        print("❌ FIELD IS EMPTY")
    
    # Check summary_overview field
    summary_overview = bill.get('summary_overview', '')
    print(f"\n--- summary_overview field ---")
    print(f"Length: {len(summary_overview)} characters")
    if summary_overview:
        print(f"Content:\n{summary_overview}")
    else:
        print("❌ FIELD IS EMPTY")
    
    print("\n" + "="*80)
    print("CONCLUSION")
    print("="*80)
    
    if summary_detailed and "full text needed" not in summary_detailed.lower():
        print("✅ SUCCESS: summary_detailed field is properly populated!")
        print("The website should now display the correct summary.")
        return 0
    else:
        print("❌ ISSUE: summary_detailed field needs attention")
        return 1

if __name__ == "__main__":
    sys.exit(main())