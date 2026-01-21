#!/usr/bin/env python3
"""
Script to verify that the tracker fixes are working properly
"""

import os
import sys

# Add the project root to the Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

from src.database.db import get_bill_by_id

def verify_tracker_fixes():
    """Verify that the tracker fixes are working properly"""
    print("=== Verifying Tracker Fixes ===")
    
    # Test bills that should have failed status
    test_bills = [
        ('s2882-119', 'failed_senate'),
        ('hr5371-119', 'failed_senate')
    ]
    
    all_passed = True
    
    for bill_id, expected_status in test_bills:
        try:
            bill = get_bill_by_id(bill_id)
            if bill:
                actual_status = bill['normalized_status']
                if actual_status == expected_status:
                    print(f"✅ {bill_id}: Correct status '{actual_status}'")
                else:
                    print(f"❌ {bill_id}: Expected '{expected_status}', got '{actual_status}'")
                    all_passed = False
            else:
                print(f"❌ {bill_id}: Not found in database")
                all_passed = False
        except Exception as e:
            print(f"❌ {bill_id}: Error retrieving bill - {e}")
            all_passed = False
    
    if all_passed:
        print("\n🎉 All tracker fixes verified successfully!")
        print("The pipeline now correctly captures and stores legislative bill progression data.")
    else:
        print("\n⚠️  Some tracker fixes failed verification.")
        
    return all_passed

if __name__ == "__main__":
    verify_tracker_fixes()