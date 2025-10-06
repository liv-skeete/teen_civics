#!/usr/bin/env python3
"""
Script to standardize header formatting in all bill summaries.
Ensures all headers use proper emoji format with consistent spacing.
"""

import sys
import re
import os
from pathlib import Path

# Load environment variables
sys.path.insert(0, 'src')
from load_env import load_env

# Load .env file
load_env()

from database.connection import postgres_connect

# Define the standard header mappings
HEADER_MAPPINGS = {
    # Overview headers
    r'(?:🔍\s*)?Overview:?': '🔍 Overview',
    r'(?:🔍\s*)?OVERVIEW:?': '🔍 Overview',
    
    # Who does this affect headers
    r'(?:👥\s*)?Who does this affect\??:?': '👥 Who does this affect?',
    r'(?:👥\s*)?WHO DOES THIS AFFECT\??:?': '👥 Who does this affect?',
    r'👥Who does this affect\?': '👥 Who does this affect?',  # Missing space
    
    # Key Provisions headers
    r'(?:🔑\s*)?Key Provisions:?': '🔑 Key Provisions',
    r'(?:🔑\s*)?KEY PROVISIONS:?': '🔑 Key Provisions',
    
    # Policy Changes headers
    r'(?:🔧\s*)?Policy Changes:?': '🔧 Policy Changes',
    r'(?:🔧\s*)?POLICY CHANGES:?': '🔧 Policy Changes',
    
    # Policy Riders headers
    r'(?:⚖️\s*)?Policy Riders or Key Rules/Changes:?': '⚖️ Policy Riders or Key Rules/Changes',
    r'(?:⚖️\s*)?POLICY RIDERS OR KEY RULES/CHANGES:?': '⚖️ Policy Riders or Key Rules/Changes',
    
    # Procedural/Administrative Notes headers
    r'(?:📋\s*)?Procedural/Administrative Notes:?': '📋 Procedural/Administrative Notes',
    r'(?:📋\s*)?PROCEDURAL/ADMINISTRATIVE NOTES:?': '📋 Procedural/Administrative Notes',
    
    # Why should I care headers
    r'(?:💡\s*)?Why should I care\??:?': '💡 Why should I care?',
    r'(?:💡\s*)?WHY SHOULD I CARE\??:?': '💡 Why should I care?',
}

def analyze_bill_headers(summary_detailed):
    """Analyze a bill's summary for header formatting issues."""
    if not summary_detailed:
        return None, []
    
    issues = []
    
    # Check for headers without emojis or with wrong formatting
    for pattern, standard in HEADER_MAPPINGS.items():
        matches = re.finditer(pattern, summary_detailed, re.IGNORECASE)
        for match in matches:
            if match.group(0) != standard:
                issues.append({
                    'found': match.group(0),
                    'should_be': standard,
                    'position': match.start()
                })
    
    return summary_detailed, issues

def fix_bill_headers(summary_detailed):
    """Fix header formatting in a bill's summary."""
    if not summary_detailed:
        return summary_detailed, False
    
    original = summary_detailed
    fixed = summary_detailed
    
    # Apply all header fixes
    for pattern, standard in HEADER_MAPPINGS.items():
        fixed = re.sub(pattern, standard, fixed, flags=re.IGNORECASE)
    
    return fixed, (fixed != original)

def main():
    print("=" * 80)
    print("Bill Header Standardization Script")
    print("=" * 80)
    print()
    
    # Connect to database
    print("Connecting to database...")
    
    # Get all bills
    print("Fetching all bills...")
    with postgres_connect() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT bill_id, title, summary_detailed
                FROM bills
                ORDER BY bill_id
            """)
            bills = cursor.fetchall()
    
    print(f"Found {len(bills)} bills in database\n")
    
    # Analyze all bills
    print("Analyzing header formatting...")
    print("-" * 80)
    
    bills_with_issues = []
    bills_without_summaries = []
    
    for bill in bills:
        bill_id, title, summary_detailed = bill
        
        if not summary_detailed:
            bills_without_summaries.append(bill_id)
            continue
        
        _, issues = analyze_bill_headers(summary_detailed)
        
        if issues:
            bills_with_issues.append({
                'bill_id': bill_id,
                'title': title,
                'issues': issues
            })
            print(f"\n📋 {bill_id}: {title[:60]}...")
            for issue in issues:
                print(f"   ❌ Found: '{issue['found']}'")
                print(f"   ✅ Should be: '{issue['should_be']}'")
    
    print("\n" + "=" * 80)
    print("ANALYSIS SUMMARY")
    print("=" * 80)
    print(f"Total bills: {len(bills)}")
    print(f"Bills without summaries: {len(bills_without_summaries)}")
    print(f"Bills with header issues: {len(bills_with_issues)}")
    print(f"Bills with correct formatting: {len(bills) - len(bills_with_issues) - len(bills_without_summaries)}")
    
    if bills_without_summaries:
        print(f"\nBills without summaries: {', '.join(bills_without_summaries)}")
    
    # Ask user if they want to fix the issues
    if bills_with_issues:
        print("\n" + "=" * 80)
        response = input(f"\nDo you want to fix {len(bills_with_issues)} bills with header issues? (yes/no): ").strip().lower()
        
        if response in ['yes', 'y']:
            print("\nFixing header formatting...")
            fixed_count = 0
            
            with postgres_connect() as conn:
                with conn.cursor() as cursor:
                    for bill_info in bills_with_issues:
                        bill_id = bill_info['bill_id']
                        
                        # Get current summary
                        cursor.execute("SELECT summary_detailed FROM bills WHERE bill_id = %s", (bill_id,))
                        result = cursor.fetchone()
                        if not result:
                            continue
                        
                        summary_detailed = result[0]
                        fixed_summary, was_changed = fix_bill_headers(summary_detailed)
                        
                        if was_changed:
                            # Update the database
                            cursor.execute("""
                                UPDATE bills
                                SET summary_detailed = %s
                                WHERE bill_id = %s
                            """, (fixed_summary, bill_id))
                            fixed_count += 1
                            print(f"✅ Fixed: {bill_id}")
            
            print(f"\n✅ Successfully fixed {fixed_count} bills!")
        else:
            print("\nNo changes made.")
    else:
        print("\n✅ All bills have correct header formatting!")
    
    print("\nDone!")

if __name__ == "__main__":
    main()