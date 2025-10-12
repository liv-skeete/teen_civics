#!/usr/bin/env python3
"""
Script to fix all bill trackers in the database.
This script will reprocess all bills and update their tracker information.
"""

import sys
import os
import json
import re
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from dotenv import load_dotenv
load_dotenv()

from src.fetchers.feed_parser import scrape_bill_tracker
from src.fetchers.congress_fetcher import fetch_bill_details_from_api, derive_tracker_from_actions
from src.database.connection import postgres_connect
import os

CONGRESS_API_KEY = os.getenv('CONGRESS_API_KEY')

def reconstruct_bill_url(bill_id):
    """Reconstruct the Congress.gov URL for a bill."""
    parts = bill_id.split('-')
    if len(parts) != 2:
        return None
        
    full_type = parts[0]
    congress = parts[1]
    bill_type = ''.join([c for c in full_type if not c.isdigit()])
    bill_number = ''.join([c for c in full_type if c.isdigit()])
    
    # Map bill types to URL paths
    type_map = {
        'hr': 'house-bill',
        's': 'senate-bill',
        'hjres': 'house-joint-resolution',
        'sjres': 'senate-joint-resolution',
        'hconres': 'house-concurrent-resolution',
        'sconres': 'senate-concurrent-resolution',
        'hres': 'house-resolution',
        'sres': 'senate-resolution'
    }
    
    bill_type_full = type_map.get(bill_type)
    if not bill_type_full:
        return None
        
    return f'https://www.congress.gov/bill/{congress}th-congress/{bill_type_full}/{bill_number}'

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
        elif isinstance(tracker_data, dict):
            # Dict with steps in 'steps' key
            steps = tracker_data.get("steps", [])
            for step in steps:
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

def fix_bill_tracker(bill_id, congress, bill_type, bill_number, source_url):
    """Fix tracker information for a single bill."""
    try:
        # Fetch latest action from API
        latest_action_text = None
        tracker_data = None
        
        if congress and bill_type and bill_number and CONGRESS_API_KEY:
            print(f"Fetching API details for {bill_id}...")
            details = fetch_bill_details_from_api(congress, bill_type, bill_number, CONGRESS_API_KEY)
            if details:
                latest_action = details.get('latestAction', {})
                latest_action_text = latest_action.get('text') if isinstance(latest_action, dict) else str(latest_action)
                actions = details.get('actions', [])
                tracker_data = derive_tracker_from_actions(actions)
        
        # Reconstruct URL if missing
        url_to_use = source_url
        if not url_to_use:
            url_to_use = reconstruct_bill_url(bill_id)
            print(f"Reconstructed URL for {bill_id}: {url_to_use}")
        
        # Override with scraped tracker if available
        if url_to_use:
            print(f"Scraping tracker for {bill_id}...")
            scraped_tracker = scrape_bill_tracker(url_to_use)
            if scraped_tracker:
                tracker_data = scraped_tracker
                print(f"Using scraped tracker: {scraped_tracker}")
            else:
                print(f"Failed to scrape tracker for {bill_id}")
        
        # Derive normalized status
        normalized_status = normalize_status_from_tracker(tracker_data)
        print(f"Derived normalized status: {normalized_status}")
        
        # Update database
        with postgres_connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                UPDATE bills
                SET raw_latest_action = %s,
                    tracker_raw = %s,
                    normalized_status = %s
                WHERE bill_id = %s
                """, (latest_action_text, json.dumps(tracker_data) if tracker_data else None, normalized_status, bill_id))
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
            SELECT bill_id, congress_session, source_url
            FROM bills
            ORDER BY date_processed DESC
            """)
            bills = cursor.fetchall()
    
    print(f"Found {len(bills)} bills to process...")
    
    success_count = 0
    error_count = 0
    
    for bill in bills:
        bill_id, congress, source_url = bill
        
        # Parse bill components
        # bill_id is like 'hr2462-119'
        parts = bill_id.split('-')
        if len(parts) != 2:
            print(f"Skipping {bill_id}: invalid format")
            error_count += 1
            continue
            
        full_type = parts[0]
        congress = parts[1]
        bill_type = ''.join([c for c in full_type if not c.isdigit()])
        bill_number = ''.join([c for c in full_type if c.isdigit()])
        
        if fix_bill_tracker(bill_id, congress, bill_type, bill_number, source_url):
            success_count += 1
        else:
            error_count += 1
            
        # Print progress every 10 bills
        if (success_count + error_count) % 10 == 0:
            print(f"Progress: {success_count + error_count}/{len(bills)} bills processed")
    
    print(f"Finished! Success: {success_count}, Errors: {error_count}")

if __name__ == "__main__":
    main()