#!/usr/bin/env python3
"""
Script to backfill correct metadata and status for bill hr2316-119 in the database.
This script uses the fixed feed_parser to correctly scrape the tracker and update the bill's information.
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
from src.database.db import get_bill_by_id
from src.database.connection import postgres_connect

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

def update_bill_in_db(bill_id, source_url, tracker_data):
    """Update the bill in the database with corrected information."""
    normalized_status = normalize_status_from_tracker(tracker_data)
    
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

def main():
    bill_id = "hr2316-119"
    print(f"Backfilling correct metadata and status for bill {bill_id}...")
    
    try:
        # Reconstruct correct Congress.gov URL
        source_url = reconstruct_bill_url(bill_id)
        print(f"Using source URL: {source_url}")
        
        if not source_url:
            print(f"Failed to reconstruct URL for {bill_id}")
            sys.exit(1)
            
        # Scrape tracker from HTML
        print(f"Scraping tracker for {bill_id}...")
        tracker_data = scrape_bill_tracker(source_url, force_scrape=True)
        
        if not tracker_data:
            print(f"Failed to scrape tracker for {bill_id}")
            sys.exit(1)
            
        print(f"Scraped tracker data: {tracker_data}")
        
        # Update database
        update_bill_in_db(bill_id, source_url, tracker_data)
        print(f"Successfully backfilled data for {bill_id}")
        
    except Exception as e:
        print(f"Error backfilling data for {bill_id}: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()