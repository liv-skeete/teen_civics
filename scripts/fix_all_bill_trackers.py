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
                            norm