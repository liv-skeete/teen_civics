#!/usr/bin/env python3
"""
Script to fix double emoji issue in bill summary headers.
Updates all existing bills to use single, standardized emojis.
"""

import sys
import re
from pathlib import Path

# Load environment variables
sys.path.insert(0, 'src')
from load_env import load_env

# Load .env file
load_env()

from database.connection import postgres_connect

def fix_double_emojis(text):
    """
    Remove duplicate emojis from headers in bill summaries.
    Handles cases where both old and new emojis appear together.
    """
    if not text:
        return text, False
    
    original = text
    fixed = text
    
    # Fix double emoji patterns (old emoji + new emoji or vice versa)
    # Pattern: 🔎 🔍 Overview -> 🔎 Overview
    fixed = re.sub(r'🔎\s*🔍\s*Overview', '🔎 Overview', fixed)
    fixed = re.sub(r'🔍\s*🔎\s*Overview', '🔎 Overview', fixed)
    
    # Pattern: 🛠️ 🔧 Policy Changes -> 🛠️ Policy Changes
    fixed = re.sub(r'🛠️\s*🔧\s*Policy Changes', '🛠️ Policy Changes', fixed)
    fixed = re.sub(r'🔧\s*🛠️\s*Policy Changes', '🛠️ Policy Changes', fixed)
    
    # Pattern: 📌 📋 Procedural/Administrative Notes -> 📌 Procedural/Administrative Notes
    fixed = re.sub(r'📌\s*📋\s*Procedural/Administrative Notes', '📌 Procedural/Administrative Notes', fixed)
    fixed = re.sub(r'📋\s*📌\s*Procedural/Administrative Notes', '📌 Procedural/Administrative Notes', fixed)
    
    # Also fix any standalone old emojis to new ones
    fixed = re.sub(r'🔍\s*Overview', '🔎 Overview', fixed)
    fixed = re.sub(r'🔧\s*Policy Changes', '🛠️ Policy Changes', fixed)
    fixed = re.sub(r'📋\s*Procedural/Administrative Notes', '📌 Procedural/Administrative Notes', fixed)
    
    return fixed, (fixed != original)

def main():
    print("=" * 80)
    print("Fix Double Emoji Headers in Bill Summaries")
    print("=" * 80)
    print()
    
    # Connect to database
    print("Connecting to database...")
    
    # Get all bills with summaries
    print("Fetching all bills with summaries...")
    with postgres_connect() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT bill_id, title, summary_detailed
                FROM bills
                WHERE summary_detailed IS NOT NULL
                ORDER BY bill_id
            """)
            bills = cursor.fetchall()
    
    print(f"Found {len(bills)} bills with summaries\n")
    
    # Analyze and fix
    print("Analyzing and fixing double emoji issues...")
    print("-" * 80)
    
    bills_fixed = []
    
    for bill in bills:
        bill_id, title, summary_detailed = bill
        
        fixed_summary, was_changed = fix_double_emojis(summary_detailed)
        
        if was_changed:
            bills_fixed.append({
                'bill_id': bill_id,
                'title': title,
                'original': summary_detailed,
                'fixed': fixed_summary
            })
            print(f"✅ Fixed: {bill_id} - {title[:60]}...")
    
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Total bills checked: {len(bills)}")
    print(f"Bills with double emoji issues: {len(bills_fixed)}")
    print(f"Bills already correct: {len(bills) - len(bills_fixed)}")
    
    # Apply fixes to database
    if bills_fixed:
        print("\n" + "=" * 80)
        response = input(f"\nDo you want to update {len(bills_fixed)} bills in the database? (yes/no): ").strip().lower()
        
        if response in ['yes', 'y']:
            print("\nUpdating database...")
            updated_count = 0
            
            with postgres_connect() as conn:
                with conn.cursor() as cursor:
                    for bill_info in bills_fixed:
                        bill_id = bill_info['bill_id']
                        fixed_summary = bill_info['fixed']
                        
                        cursor.execute("""
                            UPDATE bills
                            SET summary_detailed = %s
                            WHERE bill_id = %s
                        """, (fixed_summary, bill_id))
                        updated_count += 1
            
            print(f"\n✅ Successfully updated {updated_count} bills!")
        else:
            print("\nNo changes made to database.")
    else:
        print("\n✅ All bills already have correct single emoji headers!")
    
    print("\nDone!")

if __name__ == "__main__":
    main()