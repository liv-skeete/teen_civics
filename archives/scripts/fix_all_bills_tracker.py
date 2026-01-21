#!/usr/bin/env python3
"""
Script to fix tracker data for all bills in the database.
This script will:
1. Reconstruct correct Congress.gov URLs for all bills
2. Scrape trackers from Congress.gov
3. Update database with correct information
"""

import sys
import os
import json

# Add project root to path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

from src.fetchers.feed_parser import scrape_bill_tracker, construct_bill_url
from src.database.connection import postgres_connect

def normalize_status_from_tracker(tracker_data):
    """Derive normalized status from tracker data, mapping to valid enum values."""
    normalized_status = "unknown"
    if tracker_data:
        if isinstance(tracker_data, list):
            # List of steps with selected flag
            for step in tracker_data:
                if step.get("selected", False):
                    status_name = step["name"].lower().replace(" ", "_")
                    # Map to valid enum values
                    if "agreed" in status_name and "senate" in status_name:
                        normalized_status = "passed_senate"
                    elif "agreed" in status_name and "house" in status_name:
                        normalized_status = "passed_house"
                    elif "agreed" in status_name:  # General "Agreed to" case
                        if "house" in status_name or "hres" in status_name or "hr" in status_name:
                            normalized_status = "passed_house"
                        else:
                            normalized_status = "passed_senate"
                    elif "became" in status_name and "law" in status_name:
                        normalized_status = "became_law"
                    elif "passed" in status_name and "senate" in status_name:
                        normalized_status = "passed_senate"
                    elif "passed" in status_name and "house" in status_name:
                        normalized_status = "passed_house"
                    elif "to" in status_name and "president" in status_name:
                        normalized_status = "to_president"
                    elif "introduced" in status_name:
                        normalized_status = "introduced"
                    elif "vetoed" in status_name:
                        normalized_status = "vetoed"
                    elif "failed" in status_name:
                        if "senate" in status_name:
                            normalized_status = "failed_senate"
                        elif "house" in status_name:
                            normalized_status = "failed_house"
                        else:
                            normalized_status = "failed"
                    else:
                        # Default to introduced as fallback
                        normalized_status = "introduced"
                    break
    return normalized_status

def reconstruct_bill_url(bill_id):
    """Reconstruct the Congress.gov URL for a bill."""
    parts = bill_id.split('-')
    if len(parts) != 2:
        return None
        
    full_type = parts[0]
    congress = parts[1]
    bill_type = ''.join([c for c in full_type if not c.isdigit()])
    bill_number = ''.join([c for c in full_type if c.isdigit()])
    
    return construct_bill_url(congress, bill_type, bill_number)

def fix_bill_tracker(bill_id):
    """Fix tracker information for a single bill."""
    try:
        # Reconstruct correct Congress.gov URL
        source_url = reconstruct_bill_url(bill_id)
        if not source_url:
            print(f"Failed to reconstruct URL for {bill_id}")
            return False
            
        # Scrape tracker from HTML
        print(f"Scraping tracker for {bill_id}...")
        tracker_data = scrape_bill_tracker(source_url, force_scrape=True)
        
        if not tracker_data:
            print(f"Failed to scrape tracker for {bill_id}")
            return False
            
        # Normalize status
        normalized_status = normalize_status_from_tracker(tracker_data)
        
        # Update database
        with postgres_connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                UPDATE bills
                SET source_url = %s,
                    tracker_raw = %s,
                    normalized_status = %s
                WHERE bill_id = %s
                """, (source_url, json.dumps(tracker_data) if tracker_data else None, normalized_status, bill_id))
            conn.commit()
        
        print(f"Updated {bill_id}: status={normalized_status}")
        return True
        
    except Exception as e:
        print(f"Error updating {bill_id}: {e}")
        return False

def main():
    """Main function to fix all bill trackers."""
    print("Starting to fix all bill trackers...")
    
    # Get all bills from database
    with postgres_connect() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
            SELECT bill_id
            FROM bills
            ORDER BY date_processed DESC
            """)
            bills = cursor.fetchall()
    
    print(f"Found {len(bills)} bills to process...")
    
    success_count = 0
    error_count = 0
    
    for bill in bills:
        bill_id = bill[0]
        
        if fix_bill_tracker(bill_id):
            success_count += 1
        else:
            error_count += 1
            
        # Print progress every 10 bills
        if (success_count + error_count) % 10 == 0:
            print(f"Progress: {success_count + error_count}/{len(bills)} bills processed")
    
    print(f"Finished! Success: {success_count}, Errors: {error_count}")

if __name__ == "__main__":
    main()