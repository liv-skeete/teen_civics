#!/usr/bin/env python3
"""
Feed parser for Congress.gov "Bill Texts Received Today" feed.
Parses the HTML feed to extract bills with full text available.
"""

import logging
import re
import time
from typing import List, Dict, Any, Optional
from datetime import datetime

import requests
from bs4 import BeautifulSoup

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Feed URL
BILL_TEXTS_FEED_URL = "https://www.congress.gov/bill-texts-received-today"

# Enhanced headers to avoid 403 errors
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'none',
    'Cache-Control': 'max-age=0'
}

def parse_bill_texts_feed(limit: int = 50) -> List[Dict[str, Any]]:
    """
    Parse the "Bill Texts Received Today" HTML feed from Congress.gov.
    
    Args:
        limit: Maximum number of bills to return (default: 50)
    
    Returns:
        List of bill dictionaries with the following structure:
        {
            'bill_id': str,           # e.g., 'hr1234-119'
            'title': str,             # Bill title
            'text_url': str,          # URL to bill text (PDF/TXT)
            'text_version': str,      # e.g., 'Introduced', 'Engrossed'
            'text_received_date': str # ISO format date
        }
    
    Raises:
        requests.RequestException: If feed cannot be fetched
        ValueError: If feed format is invalid
    """
    logger.info(f"Fetching bill texts feed from: {BILL_TEXTS_FEED_URL}")
    
    # Try to fetch the feed with retry logic
    bills = []
    feed_success = False
    
    for attempt in range(3):
        try:
            logger.info(f"Attempt {attempt + 1}/3 to fetch feed")
            
            # Add delay between retries
            if attempt > 0:
                delay = 2 ** attempt  # Exponential backoff: 2, 4 seconds
                logger.info(f"Waiting {delay} seconds before retry...")
                time.sleep(delay)
            
            # Fetch the feed with timeout and enhanced headers
            response = requests.get(BILL_TEXTS_FEED_URL, headers=HEADERS, timeout=30)
            response.raise_for_status()
            logger.info(f"Feed fetched successfully (status: {response.status_code})")
            feed_success = True
            break
            
        except requests.HTTPError as e:
            if e.response.status_code == 403:
                logger.warning(f"403 Forbidden error on attempt {attempt + 1}/3")
                if attempt == 2:  # Last attempt
                    logger.error("All feed fetch attempts failed with 403. Will fall back to API.")
            else:
                logger.error(f"HTTP error on attempt {attempt + 1}/3: {e}")
        except requests.RequestException as e:
            logger.error(f"Request error on attempt {attempt + 1}/3: {e}")
    
    # If feed fetch failed, fall back to API
    if not feed_success:
        logger.warning("Feed fetch failed after all retries. Falling back to Congress.gov API...")
        return _fetch_bills_from_api(limit)
    
    # Parse HTML with lxml parser
    try:
        soup = BeautifulSoup(response.content, 'lxml')
        logger.info("HTML parsed successfully with lxml parser")
    except Exception as e:
        logger.warning(f"lxml parser failed, falling back to html.parser: {e}")
        soup = BeautifulSoup(response.content, 'html.parser')
    
    # Extract bills from the feed
    bills = []
    
    # Find the main content area - the feed uses a table or list structure
    # Look for bill entries in the page
    bill_items = soup.find_all('li', class_='expanded')
    
    if not bill_items:
        # Try alternative selectors
        bill_items = soup.find_all('div', class_='item-wrapper')
    
    if not bill_items:
        logger.warning("No bill items found in feed using standard selectors")
        # Try to find any links that look like bill links
        all_links = soup.find_all('a', href=re.compile(r'/bill/\d+/(hr|s|hjres|sjres|hconres|sconres|hres|sres)-\d+'))
        if all_links:
            logger.info(f"Found {len(all_links)} bill links using fallback method")
            bill_items = [link.parent for link in all_links[:limit]]
        else:
            logger.error("No bills found in feed")
            return []
    
    logger.info(f"Found {len(bill_items)} bill items in feed")
    
    for item in bill_items[:limit]:
        try:
            bill_data = _extract_bill_data(item)
            if bill_data:
                bills.append(bill_data)
                logger.debug(f"Extracted bill: {bill_data['bill_id']}")
        except Exception as e:
            logger.warning(f"Failed to extract bill data from item: {e}")
            continue
    
    logger.info(f"Successfully parsed {len(bills)} bills from feed")
    return bills


def _extract_bill_data(item) -> Optional[Dict[str, Any]]:
    """
    Extract bill data from a single feed item.
    
    Args:
        item: BeautifulSoup element containing bill information
    
    Returns:
        Dictionary with bill data or None if extraction fails
    """
    try:
        # Find the bill link
        bill_link = item.find('a', href=re.compile(r'/bill/\d+/(hr|s|hjres|sjres|hconres|sconres|hres|sres)-\d+'))
        if not bill_link:
            return None
        
        # Extract bill ID from URL
        # URL format: /bill/119th-congress/house-bill/1234
        href = bill_link.get('href', '')
        bill_id_match = re.search(r'/bill/(\d+)th-congress/[^/]+/(\d+)', href)
        if not bill_id_match:
            logger.warning(f"Could not extract bill ID from URL: {href}")
            return None
        
        congress = bill_id_match.group(1)
        bill_number = bill_id_match.group(2)
        
        # Determine bill type from URL
        bill_type_match = re.search(r'/(house-bill|senate-bill|house-joint-resolution|senate-joint-resolution|house-concurrent-resolution|senate-concurrent-resolution|house-resolution|senate-resolution)/', href)
        if bill_type_match:
            bill_type_full = bill_type_match.group(1)
            # Convert to short form
            type_map = {
                'house-bill': 'hr',
                'senate-bill': 's',
                'house-joint-resolution': 'hjres',
                'senate-joint-resolution': 'sjres',
                'house-concurrent-resolution': 'hconres',
                'senate-concurrent-resolution': 'sconres',
                'house-resolution': 'hres',
                'senate-resolution': 'sres'
            }
            bill_type = type_map.get(bill_type_full, 'hr')
        else:
            bill_type = 'hr'  # Default
        
        # Construct normalized bill ID
        bill_id = f"{bill_type}{bill_number}-{congress}"
        
        # Extract title
        title = bill_link.get_text(strip=True)
        if not title:
            title = f"Bill {bill_id}"
        
        # Find text version information
        text_version = "Introduced"  # Default
        version_span = item.find('span', class_='result-item')
        if version_span:
            version_text = version_span.get_text(strip=True)
            if version_text:
                text_version = version_text
        
        # Find text URL (PDF or TXT)
        text_url = None
        text_links = item.find_all('a', href=re.compile(r'\.(pdf|txt)$'))
        if text_links:
            # Prefer PDF, fallback to TXT
            pdf_link = next((link for link in text_links if link.get('href', '').endswith('.pdf')), None)
            txt_link = next((link for link in text_links if link.get('href', '').endswith('.txt')), None)
            
            if pdf_link:
                text_url = pdf_link.get('href')
            elif txt_link:
                text_url = txt_link.get('href')
        
        # If no direct text link found, construct from bill ID
        if not text_url:
            # Congress.gov text URL pattern
            text_url = f"https://www.congress.gov/{congress}/bills/{bill_type}{bill_number}/BILLS-{congress}{bill_type}{bill_number}ih.pdf"
        
        # Ensure URL is absolute
        if text_url and not text_url.startswith('http'):
            text_url = f"https://www.congress.gov{text_url}"
        
        # Use current date as received date
        text_received_date = datetime.now().isoformat()
        
        return {
            'bill_id': bill_id,
            'title': title,
            'text_url': text_url,
            'text_version': text_version,
            'text_received_date': text_received_date,
            'congress': congress,
            'bill_type': bill_type,
            'bill_number': bill_number
        }
        
    except Exception as e:
        logger.error(f"Error extracting bill data: {e}")
        return None


def _fetch_bills_from_api(limit: int = 50) -> List[Dict[str, Any]]:
    """
    Fallback method to fetch bills using the Congress.gov API.
    This is used when the feed parser encounters 403 errors.
    
    Args:
        limit: Maximum number of bills to return
    
    Returns:
        List of bill dictionaries
    """
    import os
    from dotenv import load_dotenv
    
    load_dotenv()
    api_key = os.getenv('CONGRESS_API_KEY')
    
    if not api_key:
        logger.error("CONGRESS_API_KEY not found in environment. Cannot use API fallback.")
        return []
    
    logger.info(f"Fetching bills from Congress.gov API (limit={limit})")
    
    try:
        # Fetch recent bills from the API
        # Use the /bill endpoint with recent bills
        api_url = f"https://api.congress.gov/v3/bill"
        params = {
            'api_key': api_key,
            'format': 'json',
            'limit': limit,
            'sort': 'updateDate+desc'
        }
        
        response = requests.get(api_url, params=params, headers=HEADERS, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        bills = []
        
        if 'bills' in data:
            for bill_data in data['bills']:
                try:
                    # Extract bill information
                    bill_type = bill_data.get('type', '').lower()
                    bill_number = bill_data.get('number', '')
                    congress = bill_data.get('congress', '')
                    
                    if not all([bill_type, bill_number, congress]):
                        continue
                    
                    bill_id = f"{bill_type}{bill_number}-{congress}"
                    title = bill_data.get('title', f"Bill {bill_id}")
                    
                    # Get the latest action date as text_received_date
                    latest_action = bill_data.get('latestAction', {})
                    action_date = latest_action.get('actionDate', datetime.now().isoformat())
                    
                    # Construct text URL (may not have actual text yet)
                    text_url = f"https://www.congress.gov/{congress}/bills/{bill_type}{bill_number}/BILLS-{congress}{bill_type}{bill_number}ih.pdf"
                    
                    bills.append({
                        'bill_id': bill_id,
                        'title': title,
                        'text_url': text_url,
                        'text_version': 'Introduced',
                        'text_received_date': action_date,
                        'congress': str(congress),
                        'bill_type': bill_type,
                        'bill_number': str(bill_number)
                    })
                    
                except Exception as e:
                    logger.warning(f"Error processing API bill data: {e}")
                    continue
        
        logger.info(f"Successfully fetched {len(bills)} bills from API")
        return bills
        
    except requests.RequestException as e:
        logger.error(f"Failed to fetch bills from API: {e}")
        return []
    except Exception as e:
        logger.error(f"Error processing API response: {e}")
        return []


if __name__ == "__main__":
    """Test the feed parser"""
    logger.info("Testing bill texts feed parser...")
    
    try:
        bills = parse_bill_texts_feed(limit=5)
        
        if bills:
            logger.info(f"✅ Successfully parsed {len(bills)} bills")
            for bill in bills:
                logger.info(f"  - {bill['bill_id']}: {bill['title'][:60]}...")
                logger.info(f"    Version: {bill['text_version']}")
                logger.info(f"    Text URL: {bill['text_url']}")
        else:
            logger.warning("⚠️ No bills found in feed")
            
    except Exception as e:
        logger.error(f"❌ Feed parser test failed: {e}")
        raise