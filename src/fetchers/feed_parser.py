#!/usr/bin/env python3
"""
Feed parser for Congress.gov "Bill Texts Received Today" feed.
Parses the HTML feed to extract bills with full text available.
"""

import logging
import re
from typing import List, Dict, Any, Optional
from datetime import datetime

import requests
from bs4 import BeautifulSoup

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Feed URL
BILL_TEXTS_FEED_URL = "https://www.congress.gov/bill-texts-received-today"

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
    
    try:
        # Fetch the feed with timeout and proper headers
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(BILL_TEXTS_FEED_URL, headers=headers, timeout=30)
        response.raise_for_status()
        logger.info(f"Feed fetched successfully (status: {response.status_code})")
        
    except requests.RequestException as e:
        logger.error(f"Failed to fetch bill texts feed: {e}")
        raise
    
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