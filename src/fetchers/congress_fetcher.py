"""
Congress.gov API fetcher for retrieving recent bills.
This module provides functionality to fetch the 5 most recent bills from the Congress.gov API.
"""

import os
import logging
from typing import List, Dict, Optional

import requests
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

CONGRESS_GOV_API_KEY = os.getenv('CONGRESS_GOV_API_KEY')
BASE_URL = "https://api.congress.gov/v3/"


def get_recent_bills(limit: int = 5) -> List[Dict[str, str]]:
    """
    Fetch the most recent bills from the Congress.gov API.
    
    Args:
        limit: Number of bills to retrieve (default: 5)
        
    Returns:
        List of dictionaries containing bill information with keys:
        - bill_id: The bill identifier (e.g., "hr1234")
        - title: The bill title
        - introduced_date: Date the bill was introduced
        - sponsor: The bill sponsor's name
        - latest_action: The latest action taken on the bill
        
    Raises:
        ValueError: If API key is not configured
        Exception: For any API request or processing errors
    """
    if not CONGRESS_GOV_API_KEY:
        error_msg = "CONGRESS_GOV_API_KEY not found in environment variables"
        logger.error(error_msg)
        raise ValueError(error_msg)
    
    bills_endpoint = f"{BASE_URL}bill"
    headers = {
        "X-API-Key": CONGRESS_GOV_API_KEY
    }
    
    params = {
        "format": "json",
        "limit": limit,
        "sort": "updateDate+desc"  # Sort by most recent update
    }
    
    try:
        logger.info(f"Fetching {limit} most recent bills from Congress.gov API")
        response = requests.get(bills_endpoint, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        bills = data.get('bills', [])
        
        if not bills:
            logger.warning("No bills found in API response")
            return []
        
        processed_bills = []
        for bill in bills:
            try:
                bill_data = _process_bill_data(bill)
                if bill_data:
                    processed_bills.append(bill_data)
            except Exception as e:
                logger.error(f"Error processing bill data: {e}")
                continue
        
        logger.info(f"Successfully processed {len(processed_bills)} bills")
        return processed_bills
        
    except requests.exceptions.RequestException as e:
        logger.error(f"API request failed: {e}")
        raise Exception(f"Failed to fetch bills from Congress.gov API: {e}")
    except ValueError as e:
        logger.error(f"JSON parsing error: {e}")
        raise Exception(f"Failed to parse API response: {e}")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise Exception(f"Unexpected error occurred: {e}")


def _process_bill_data(bill: Dict) -> Optional[Dict[str, str]]:
    """
    Process raw bill data from API into standardized format.
    
    Args:
        bill: Raw bill data from API response
        
    Returns:
        Processed bill dictionary or None if processing fails
    """
    try:
        bill_id = bill.get('number', '')
        congress = bill.get('congress', '')
        bill_type = bill.get('type', '').lower()
        
        # Construct full bill ID (e.g., "hr1234-118")
        full_bill_id = f"{bill_type}{bill_id}"
        if congress:
            full_bill_id = f"{full_bill_id}-{congress}"
        
        title = bill.get('title', 'No title available')
        
        # Get introduced date
        introduced_date = bill.get('introducedDate', '')
        if not introduced_date:
            introduced_date = bill.get('updateDate', '')
        
        # Get sponsor information
        sponsors = bill.get('sponsors', [])
        sponsor_name = 'Unknown sponsor'
        if sponsors:
            sponsor = sponsors[0]
            sponsor_name = sponsor.get('fullName', 'Unknown sponsor')
            if sponsor.get('isByRequest', False):
                sponsor_name = f"{sponsor_name} (by request)"
        
        # Get latest action
        latest_action = 'No action recorded'
        actions = bill.get('actions', [])
        if actions:
            latest_action_obj = actions[0]  # Most recent action is first
            latest_action = latest_action_obj.get('text', 'No action recorded')
        
        return {
            "bill_id": full_bill_id,
            "title": title,
            "introduced_date": introduced_date,
            "sponsor": sponsor_name,
            "latest_action": latest_action
        }
        
    except Exception as e:
        logger.error(f"Error processing individual bill: {e}")
        return None


if __name__ == "__main__":
    # Example usage when run directly
    try:
        recent_bills = get_recent_bills()
        print("Recent bills:")
        for bill in recent_bills:
            print(f"- {bill['bill_id']}: {bill['title']}")
            print(f"  Introduced: {bill['introduced_date']}")
            print(f"  Sponsor: {bill['sponsor']}")
            print(f"  Latest Action: {bill['latest_action']}")
            print()
    except Exception as e:
        print(f"Error: {e}")