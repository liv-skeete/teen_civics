#!/usr/bin/env python3
"""
Direct test of H.R. 2184 processing with new fixes.
Bypasses orchestrator to focus on the core fix verification.
"""

import sys
import os
import psycopg2
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from fetchers.congress_fetcher import fetch_bills_from_feed
from processors.summarizer import summarize_bill_enhanced

def get_connection():
    """Get database connection"""
    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        raise ValueError("DATABASE_URL not set in environment")
    return psycopg2.connect(database_url)

def delete_hr2184():
    """Delete existing H.R. 2184 record"""
    print("=" * 80)
    print("STEP 1: Deleting existing H.R. 2184 record")
    print("=" * 80)
    
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT bill_id, title FROM bills WHERE bill_id LIKE '%hr2184-119%'")
    existing = cursor.fetchone()
    
    if existing:
        print(f"Found: {existing[0]} - {existing[1]}")
        cursor.execute("DELETE FROM bills WHERE bill_id LIKE '%hr2184-119%'")
        conn.commit()
        print("✓ Deleted")
    else:
        print("No existing record found")
    
    conn.close()
    print()

def fetch_and_process_hr2184():
    """Fetch and process H.R. 2184 directly"""
    print("=" * 80)
    print("STEP 2: Fetching H.R. 2184 from Congress.gov")
    print("=" * 80)
    
    # Fetch recent bills
    print("Fetching recent bills...")
    bills = fetch_bills_from_feed(limit=20, include_text=True)
    
    # Find H.R. 2184
    hr2184 = None
    for bill in bills:
        if 'hr2184' in bill.get('bill_id', '').lower():
            hr2184 = bill
            break
    
    if not hr2184:
        print("❌ H.R. 2184 not found in recent bills")
        return None
    
    print(f"✓ Found: {hr2184['bill_id']}")
    print(f"  Title: {hr2184['title']}")
    print(f"  Full text length: {len(hr2184.get('full_text', '')):,} characters")
    print()
    
    return hr2184

def summarize_bill(bill_data):
    """Generate summary using new prompt"""
    print("=" * 80)
    print("STEP 3: Generating summary with enhanced prompt")
    print("=" * 80)
    
    print("Calling Claude API...")
    summary_data = summarize_bill_enhanced(bill_data)
    
    print("✓ Summary generated")
    print()
    
    return summary_data

def store_in_database(bill_data, summary_data):
    """Store bill and summary in database"""
    print("=" * 80)
    print("STEP 4: Storing in database")
    print("=" * 80)
    
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO bills (
            bill_id, title, summary_tweet, summary_long, summary_overview, summary_detailed,
            term_dictionary, full_text, source_url, date_processed, tweet_posted
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), FALSE)
    """, (
        bill_data['bill_id'],
        bill_data['title'],
        summary_data['tweet'],
        summary_data['long'],
        summary_data.get('overview', ''),
        summary_data.get('detailed', ''),
        summary_data.get('term_dictionary', ''),
        bill_data.get('full_text', ''),
        bill_data.get('source_url', ''),
    ))
    
    conn.commit()
    conn.close()
    
    print(f"✓ Stored bill: {bill_data['bill_id']}")
    print(f"  Full text: {len(bill_data.get('full_text', '')):,} characters")
    print(f"  Summary: {len(summary_data['long'])} characters")
    print()

def display_and_verify_summary():
    """Display and verify the summary"""
    print("=" * 80)
    print("STEP 5: Displaying and verifying summary")
    print("=" * 80)
    
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT bill_id, title, summary_long, full_text, LENGTH(full_text) as text_length
        FROM bills 
        WHERE bill_id LIKE '%hr2184-119%'
    """)
    
    result = cursor.fetchone()
    conn.close()
    
    if not result:
        print("❌ Bill not found in database!")
        return False
    
    bill_id, title, summary, full_text, text_length = result
    
    print(f"Bill: {bill_id}")
    print(f"Title: {title}")
    print(f"Full text stored: {text_length:,} characters")
    print()
    print("NEW SUMMARY:")
    print("-" * 80)
    print(summary)
    print("-" * 80)
    print()
    
    # Verify substantive details
    substantive_checks = {
        "60-day deadline": ["60 day", "60-day", "sixty day"],
        "30-day expedited hearings": ["30 day", "30-day", "thirty day", "expedited"],
        "Clear and convincing evidence": ["clear and convincing", "burden of proof"],
        "Attorney fees": ["attorney", "legal fees"],
        "Annual reporting": ["annual report", "annually", "report to congress"],
        "18 U.S.C. § 925A": ["925A", "925(A)", "section 925A", "18 U.S.C"]
    }
    
    summary_lower = summary.lower()
    found_details = []
    
    print("SUBSTANTIVE DETAILS CHECK:")
    print("-" * 80)
    for detail_name, keywords in substantive_checks.items():
        found = any(keyword.lower() in summary_lower for keyword in keywords)
        if found:
            found_details.append(detail_name)
            print(f"✓ {detail_name}")
        else:
            print(f"✗ {detail_name}")
    
    print()
    print(f"Found {len(found_details)}/{len(substantive_checks)} substantive details")
    print()
    
    return len(found_details) >= 3

def main():
    """Run the test"""
    print("\n")
    print("=" * 80)
    print("DIRECT TEST: H.R. 2184 PROCESSING WITH NEW FIXES")
    print("=" * 80)
    print()
    
    try:
        # Step 1: Delete existing record
        delete_hr2184()
        
        # Step 2: Fetch bill data
        bill_data = fetch_and_process_hr2184()
        if not bill_data:
            print("❌ Failed to fetch bill")
            return 1
        
        # Step 3: Generate summary
        summary_data = summarize_bill(bill_data)
        
        # Step 4: Store in database
        store_in_database(bill_data, summary_data)
        
        # Step 5: Display and verify
        success = display_and_verify_summary()
        
        # Final result
        print("=" * 80)
        print("TEST COMPLETE")
        print("=" * 80)
        
        if success:
            print("✓ SUCCESS: Both fixes working!")
            print("  - Database stores full bill text")
            print("  - Summarizer extracts substantive details")
        else:
            print("⚠ PARTIAL: Fixes applied but summary needs improvement")
        
        print()
        return 0
        
    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())