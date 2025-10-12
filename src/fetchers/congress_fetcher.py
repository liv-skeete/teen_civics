"""
Congress.gov API and RSS fetcher for retrieving recent bills.
This module provides functionality to fetch bills from the Congress.gov API and RSS feeds.
"""

import os
import logging
from typing import List, Dict, Optional, Any
import re
import requests
from dotenv import load_dotenv
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
import fitz  # PyMuPDF
from datetime import datetime

# Import headers from feed_parser to avoid 403 errors
from .feed_parser import HEADERS, USER_AGENTS, get_random_user_agent, scrape_bill_tracker
import time
import random

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

CONGRESS_API_KEY = os.getenv('CONGRESS_API_KEY')
BASE_URL = "https://api.congress.gov/v3/"
BILL_TEXTS_FEED_URL = "https://www.congress.gov/bill-texts-received-today"

# Create a session for persistent connections
session = requests.Session()
session.headers.update(HEADERS)

def update_session_headers():
    """Update session headers with a random user agent"""
    session.headers.update({
        'User-Agent': get_random_user_agent()
    })


def fetch_bill_details_from_api(congress: str, bill_type: str, bill_number: str, api_key: str) -> Dict[str, Any]:
    """
    Fetch bill details including actions from the Congress.gov API.
    
    Args:
        congress: Congress number (e.g., '119')
        bill_type: Bill type (e.g., 'sjres')
        bill_number: Bill number (e.g., '83')
        api_key: Congress.gov API key
    
    Returns:
        Dictionary with bill details, including 'actions' and 'latest_action'
    """
    try:
        base_url = f'https://api.congress.gov/v3/bill/{congress}/{bill_type}/{bill_number}?format=json'
        if api_key:
            base_url += f'&api_key={api_key}'
        
        logger.info(f"Fetching bill details from API: {base_url}")
        response = requests.get(base_url, timeout=30)
        response.raise_for_status()
        data = response.json().get('bill', {})
        
        # Fetch actions separately if needed
        actions_url = f'https://api.congress.gov/v3/bill/{congress}/{bill_type}/{bill_number}/actions?format=json'
        if api_key:
            actions_url += f'&api_key={api_key}'
        actions_response = requests.get(actions_url, timeout=30)
        actions_response.raise_for_status()
        data['actions'] = actions_response.json().get('actions', [])
        
        return data
    except Exception as e:
        logger.error(f"Error fetching bill details from API: {e}")
        return {}

def derive_tracker_from_actions(actions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Derive tracker progression from bill actions.
    
    Args:
        actions: List of action dictionaries from API
        
    Returns:
        List of {"name": str, "selected": bool}
    """
    steps = [
        {"name": "Introduced", "selected": False},
        {"name": "Passed Senate", "selected": False},
        {"name": "Passed House", "selected": False},
        {"name": "To President", "selected": False},
        {"name": "Became Law", "selected": False}
    ]
    
    if not actions:
        steps[0]['selected'] = True
        return steps
    
    # Sort actions by date descending
    sorted_actions = sorted(actions, key=lambda x: x.get('actionDate', ''), reverse=True)
    latest_action = sorted_actions[0].get('text', '').lower()
    
    if "became public law" in latest_action or "signed by president" in latest_action:
        steps[4]['selected'] = True
    elif "passed house" in latest_action or "agreed to in house" in latest_action:
        steps[2]['selected'] = True
    elif "passed senate" in latest_action or "agreed to in senate" in latest_action:
        steps[1]['selected'] = True
    elif "to president" in latest_action:
        steps[3]['selected'] = True
    else:
        steps[0]['selected'] = True
    
    # Mark all previous steps as completed (selected True for previous)
    for i in range(len(steps)):
        if steps[i]['selected']:
            for j in range(i):
                steps[j]['selected'] = True
            break
    
    return steps

def get_recent_bills(limit: int = 10, include_text: bool = False, text_chars: int = 15000) -> List[Dict[str, str]]:
    """
    Fetch the most recent bills from the "Bill Texts Received Today" feed.
    This is the main entry point for fetching bills with full text available.
    """
    logger.info("Fetching recent bills from 'Bill Texts Received Today' feed")
    bills = fetch_bills_from_feed(limit=limit, include_text=include_text, text_chars=text_chars)
    return bills


def fetch_bills_from_feed(limit: int = 10, include_text: bool = True, text_chars: int = 15000) -> List[Dict[str, any]]:
    """
    Fetches bills from the "Bill Texts Received Today" feed using the dedicated feed parser.
    This is the new workflow entry point that ensures bills have full text before processing.
    
    Uses a three-tier approach:
    1. Browser-based scraping (bypasses 403 errors)
    2. Traditional requests library (fallback)
    3. API with text filtering (when feed is empty or fails)
    
    Args:
        limit: Maximum number of bills to fetch
        include_text: Whether to download and include full bill text
        text_chars: Maximum characters of text to include (for truncation)
    
    Returns:
        List of bill dictionaries with full metadata and text
    """
    logger.info(f"🎯 Fetching bills from feed (limit={limit}, include_text={include_text})")
    
    try:
        # Use the dedicated feed parser
        from .feed_parser import parse_bill_texts_feed
        
        feed_bills = parse_bill_texts_feed(limit=limit)
        
        if not feed_bills:
            # Empty feed is normal for the ephemeral "bill-texts-received-today" page
            logger.info("ℹ️ Feed returned no bills. This is normal if no bills received text today.")
            logger.info("ℹ️ The feed parser has already fallen back to API with text filtering.")
            return []
        
        logger.info(f"✅ Feed parser returned {len(feed_bills)} bills")
        
        # Enrich bills with full text if requested
        enriched_bills = []
        bills_with_text = 0
        bills_without_text = 0
        
        for bill in feed_bills:
            try:
                # Fetch additional details from API
                congress = bill.get('congress')
                bill_type = bill.get('bill_type')
                bill_number = bill.get('bill_number')
                if congress and bill_type and bill_number and CONGRESS_API_KEY:
                    details = fetch_bill_details_from_api(congress, bill_type, bill_number, CONGRESS_API_KEY)
                    bill['latest_action'] = details.get('latestAction', {})
                    actions = details.get('actions', [])
                    bill['tracker'] = derive_tracker_from_actions(actions)
                
                # Override tracker with scraped version if available
                if bill.get('source_url'):
                    scraped_tracker = scrape_bill_tracker(bill['source_url'])
                    if scraped_tracker:
                        bill['tracker'] = scraped_tracker
                
                if include_text:
                    full_text = ""
                    text_source = 'none'
                    
                    # First, try to fetch text using the API text endpoint (most reliable)
                    congress = bill.get('congress')
                    bill_type = bill.get('bill_type')
                    bill_number = bill.get('bill_number')
                    
                    if congress and bill_type and bill_number and CONGRESS_API_KEY:
                        logger.info(f"📥 Fetching text for {bill['bill_id']} using API text endpoint")
                        full_text, format_type = fetch_bill_text_from_api(
                            congress, bill_type, bill_number, CONGRESS_API_KEY
                        )
                        if full_text:
                            text_source = f'api-{format_type}'
                            logger.info(f"✅ Got text from API ({format_type})")
                    
                    # If API text fetch failed, try direct text_url if available
                    if (not full_text or len(full_text.strip()) <= 100) and bill.get('text_url'):
                        text_url = bill.get('text_url')
                        if text_url and text_url.startswith('http'):  # Validate it's a real URL
                            logger.info(f"📥 Trying direct text URL for {bill['bill_id']}: {text_url}")
                            full_text = _download_direct_text(text_url, bill['bill_id'])
                            if full_text and len(full_text.strip()) > 100:
                                text_source = 'direct-url'
                                logger.info(f"✅ Got text from direct URL")
                        else:
                            logger.warning(f"⚠️ Invalid or missing text_url for {bill['bill_id']}: {text_url}")
                    
                    # If both API and direct URL failed, fall back to scraping (last resort)
                    if (not full_text or len(full_text.strip()) <= 100) and bill.get('source_url'):
                        source_url = bill.get('source_url')
                        logger.info(f"📥 Falling back to scraping text for {bill['bill_id']} from {source_url}")
                        full_text, status = download_bill_text(source_url, bill['bill_id'])
                        if status:
                            bill['status'] = status.lower() # Standardize to lowercase
                            logger.info(f"✅ Updated bill status to '{status}' from scraping")
                        if full_text and len(full_text.strip()) > 100:
                            text_source = 'scraped'
                            logger.info(f"✅ Got text from scraping")
                    
                    # Validate and store text
                    if full_text and len(full_text.strip()) > 100:
                        bill['full_text'] = full_text[:text_chars] if text_chars else full_text
                        bill['text_source'] = text_source
                        bills_with_text += 1
                        
                        # Log first 100 words to prove we're reading actual content
                        words = full_text.split()[:100]
                        preview = ' '.join(words)
                        logger.info(f"📄 First 100 words of {bill['bill_id']}: {preview}")
                        logger.info(f"✅ Successfully fetched {len(full_text)} chars for {bill['bill_id']} from {text_source}")
                    else:
                        logger.warning(f"⚠️ No valid text found for {bill['bill_id']}")
                        bill['full_text'] = ""
                        bill['text_source'] = 'none'
                        bills_without_text += 1
                else:
                    bill['full_text'] = ""
                    bill['text_source'] = 'not-requested'
                
                # Add default status if not present
                if 'status' not in bill:
                    bill['status'] = 'introduced'
                
                # Ensure all required fields are present
                bill.setdefault('short_title', '')
                bill.setdefault('source_url', bill.get('text_url', ''))
                bill.setdefault('introduced_date', bill.get('text_received_date', ''))
                
                enriched_bills.append(bill)
                
            except Exception as e:
                logger.error(f"Error enriching bill {bill.get('bill_id', 'unknown')}: {e}")
                continue
        
        logger.info(f"📊 Text Enrichment Results:")
        logger.info(f"   - Bills processed: {len(feed_bills)}")
        logger.info(f"   - Bills WITH text: {bills_with_text}")
        logger.info(f"   - Bills WITHOUT text: {bills_without_text}")
        logger.info(f"   - Bills returned: {len(enriched_bills)}")
        
        return enriched_bills
        
    except ImportError as e:
        logger.error(f"Failed to import feed_parser: {e}")
        logger.info("Falling back to legacy feed parsing")
        return fetch_bill_texts_from_feed(limit=limit)
    except Exception as e:
        logger.error(f"Error in fetch_bills_from_feed: {e}")
        return []


def download_bill_text(source_url: str, bill_id: Optional[str] = None) -> tuple[str, Optional[str]]:
    """
    Downloads bill text and parses status by scraping the bill's main page on Congress.gov.
    It finds the link to the text versions page, then finds the PDF or TXT download link.
    It also parses the bill's current status from the progress bar.
    
    Args:
        source_url: URL to the main bill page on Congress.gov.
        bill_id: Optional bill ID for logging.
        
    Returns:
        A tuple containing:
        - Extracted text content (or empty string on failure).
        - Parsed bill status (or None on failure).
    """
    if not source_url:
        return "", None
        
    try:
        # Add small random delay to appear more human-like
        delay = random.uniform(1.0, 3.0)
        logger.info(f"Waiting {delay:.2f} seconds before fetching bill page for {bill_id or 'unknown'}")
        time.sleep(delay)
        
        # Update headers with random user agent
        update_session_headers()
        
        logger.info(f"Fetching bill page for {bill_id or 'unknown'} at {source_url}")
        main_page_response = session.get(source_url, timeout=30)
        main_page_response.raise_for_status()
        
        soup = BeautifulSoup(main_page_response.content, 'html.parser')

        # Parse bill status from the progress bar
        status = None
        try:
            # Method 1: Find the hide_fromsighted paragraph that contains the status
            # This is the most reliable method as it's explicitly labeled
            status_paragraphs = soup.find_all('p', class_='hide_fromsighted')
            for para in status_paragraphs:
                if para and 'This bill has the status' in para.text:
                    # Extract status from text like "This bill has the status Passed House"
                    status = para.text.replace('This bill has the status', '').strip()
                    logger.info(f"✅ Parsed bill status from hidden paragraph for {bill_id or 'unknown'}: {status}")
                    break
            
            # Method 2 (Fallback): Parse from the bill_progress list
            if not status:
                bill_progress_list = soup.find('ol', class_='bill_progress')
                if bill_progress_list:
                    selected_item = bill_progress_list.find('li', class_='selected')
                    if selected_item:
                        status_text = selected_item.text.strip()
                        # Clean up status text, e.g., "Introduced\nHouse" -> "Introduced"
                        status = status_text.split('\n')[0]
                        logger.info(f"✅ Parsed bill status from selected li (fallback) for {bill_id or 'unknown'}: {status}")
        except Exception as e:
            logger.warning(f"Could not parse bill status for {bill_id or 'unknown'}: {e}")
        
        # Find link to the "Text" tab. It usually has '/text' at the end of the href.
        text_tab_link = soup.find('a', string="Text", href=re.compile(r'/text$'))

        if not text_tab_link:
            # Fallback: find any link containing '/text'
            all_links = soup.find_all('a', href=True)
            for link in all_links:
                if '/text' in link['href'] and 'all-actions' not in link['href']:
                    text_tab_link = link
                    break

        if not text_tab_link or not text_tab_link.has_attr('href'):
            logger.error(f"Could not find 'Text' tab link on {source_url}")
            return "", status
            
        text_page_url = text_tab_link['href']
        if not text_page_url.startswith('http'):
            text_page_url = f"https://www.congress.gov{text_page_url}"
            
        # Add small delay before next request
        delay = random.uniform(0.5, 2.0)
        logger.info(f"Waiting {delay:.2f} seconds before fetching text versions page")
        time.sleep(delay)
        
        # Update headers with random user agent
        update_session_headers()
            
        logger.info(f"Fetching text versions page: {text_page_url}")
        text_page_response = session.get(text_page_url, timeout=30)
        text_page_response.raise_for_status()
        
        text_soup = BeautifulSoup(text_page_response.content, 'html.parser')
        
        # Find download links. Look for both PDF and TXT formats
        download_url = None
        
        # Look for PDF links first - check for various patterns
        pdf_links = text_soup.find_all('a', href=lambda href: href and href.endswith('.pdf'))
        if pdf_links:
            # Prioritize links that look like official bill text downloads
            for link in pdf_links:
                href = link['href']
                # Look for patterns like BILLS-119sres428ats.pdf
                if re.search(r'BILLS-\d+[a-z]+\d+[a-z]+\.pdf$', href):
                    download_url = href
                    break
                # Look for patterns with congress/bills in the path
                elif re.search(r'/\d+/bills/[a-z]+\d+/BILLS-', href):
                    download_url = href
                    break
            
            # If no specific pattern found, take the first PDF link
            if not download_url and pdf_links:
                download_url = pdf_links[0]['href']
        
        # If no PDF found, look for TXT links
        if not download_url:
            txt_links = text_soup.find_all('a', href=lambda href: href and href.endswith('.txt'))
            if txt_links:
                # Look for official-looking TXT links
                for link in txt_links:
                    href = link['href']
                    if re.search(r'BILLS-\d+[a-z]+\d+[a-z]+\.txt$', href) or '/text/' in href:
                        download_url = href
                        break
                
                # If no specific pattern found, take the first TXT link
                if not download_url and txt_links:
                    download_url = txt_links[0]['href']

        if not download_url:
            logger.error(f"Could not find PDF or TXT download link on {text_page_url}")
            return "", status
            
        # Ensure URL is absolute
        if not download_url.startswith('http'):
            if download_url.startswith('/'):
                download_url = f"https://www.congress.gov{download_url}"
            else:
                # Handle relative URLs that might be relative to current page
                base_url = text_page_url.rsplit('/', 1)[0]
                download_url = f"{base_url}/{download_url}"

        # Add small delay before downloading text
        delay = random.uniform(0.5, 1.5)
        logger.info(f"Waiting {delay:.2f} seconds before downloading bill text")
        time.sleep(delay)
        
        # Update headers with random user agent
        update_session_headers()
        
        logger.info(f"Downloading bill text from: {download_url}")
        
        response = session.get(download_url, timeout=30)
        response.raise_for_status()
        
        text = ""
        if download_url.endswith('.pdf'):
            text = _extract_text_from_pdf(response.content)
        elif download_url.endswith('.txt'):
            text = response.text
        else:
            content_type = response.headers.get('content-type', '').lower()
            if 'pdf' in content_type:
                text = _extract_text_from_pdf(response.content)
            elif 'text' in content_type:
                text = response.text
        
        if text and len(text.strip()) > 100:
            logger.info(f"Successfully downloaded text for {bill_id or 'unknown'} from {download_url}")
            return text, status
        else:
            logger.warning(f"Downloaded text for {bill_id or 'unknown'} from {download_url} is too short or empty")
            return "", status

    except requests.HTTPError as e:
        logger.error(f"HTTP error while fetching bill text for {bill_id or 'unknown'}: {e}")
        return "", None
    except Exception as e:
        logger.error(f"Failed to download bill text for {bill_id or 'unknown'}: {e}")
        return "", None


def _extract_text_from_pdf(pdf_content: bytes) -> str:
    """
    Extract text from PDF content using PyMuPDF.
    
    Args:
        pdf_content: Raw PDF file content as bytes
    
    Returns:
        Extracted text or empty string on failure
    """
    try:
        with fitz.open(stream=pdf_content, filetype="pdf") as doc:
            text = ""
            for page in doc:
                text += page.get_text()
            return text
    except Exception as e:
        logger.error(f"Failed to extract text from PDF: {e}")
        return ""

def _download_direct_text(url: str, bill_id: Optional[str] = None) -> str:
    """
    Download text directly from a given URL (PDF, TXT, or HTML/XML).
    Handles various content types and extracts text appropriately.
    
    Args:
        url: Direct URL to text content
        bill_id: Optional bill ID for logging
    
    Returns:
        Extracted text content or empty string on failure
    """
    if not url:
        return ""
    
    try:
        # Add small delay to appear more human-like
        delay = random.uniform(0.5, 2.0)
        logger.info(f"Waiting {delay:.2f} seconds before downloading direct text")
        time.sleep(delay)
        
        logger.info(f"Downloading direct text for {bill_id or 'unknown'} from {url}")
        response = session.get(url, timeout=30)
        response.raise_for_status()
        
        content_type = response.headers.get('content-type', '').lower()
        
        # Handle PDF files
        if url.endswith('.pdf') or 'pdf' in content_type:
            text = _extract_text_from_pdf(response.content)
            if text and len(text.strip()) > 100:
                logger.info(f"Successfully extracted PDF text from {url}")
                return text
        
        # Handle TXT files or plain text
        elif url.endswith('.txt') or 'text/plain' in content_type:
            text = response.text
            if text and len(text.strip()) > 100:
                logger.info(f"Successfully downloaded TXT text from {url}")
                return text
        
        # Handle HTML/XML content - extract text from markup
        elif url.endswith(('.html', '.xml')) or 'html' in content_type or 'xml' in content_type:
            soup = BeautifulSoup(response.content, 'html.parser')
            text = soup.get_text()
            if text and len(text.strip()) > 100:
                logger.info(f"Successfully extracted text from HTML/XML at {url}")
                return text
        
        # Fallback: try to extract text from any content
        text = response.text
        if text and len(text.strip()) > 100:
            logger.info(f"Successfully downloaded text from {url}")
            return text
        else:
            logger.warning(f"Downloaded text from {url} is too short or empty")
            return ""
            
    except requests.HTTPError as e:
        logger.error(f"HTTP error downloading direct text for {bill_id or 'unknown'}: {e}")
        return ""
    except Exception as e:
        logger.error(f"Failed to download direct text for {bill_id or 'unknown'}: {e}")
        return ""

def fetch_bill_texts_from_feed(limit: int = 10) -> List[Dict[str, any]]:
    """
    Fetches and parses the "Bill Texts Received Today" feed from Congress.gov.
    """
    logger.info(f"Fetching bill texts from feed: {BILL_TEXTS_FEED_URL}")
    try:
        response = requests.get(BILL_TEXTS_FEED_URL, headers=HEADERS, timeout=30)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        bills = []
        table = soup.find('table', {'class': 'table'})
        if not table:
            logger.warning("Could not find the bill texts table on the page.")
            return []
            
        rows = table.find('tbody').find_all('tr')
        for row in rows[:limit]:
            cols = row.find_all('td')
            if len(cols) < 4:
                continue

            bill_link = cols[0].find('a')
            if not bill_link:
                continue

            bill_id_text = bill_link.text.strip()
            bill_url = bill_link['href']
            title = cols[1].text.strip()
            date_str = cols[3].text.strip()

            # Extract bill details from the URL
            match = re.search(r'/(\d+)/bills/([a-z]+)(\d+)/BILLS-(\d+)([a-z]+)(\d+)([a-z]+)\.pdf', bill_url)
            if not match:
                continue

            congress, bill_type, bill_number, _, _, _, _ = match.groups()
            bill_id = f"{bill_type.lower()}{bill_number}-{congress}"

            # Download and extract text from PDF
            text_content = _download_and_extract_pdf_text(bill_url)

            bills.append({
                "bill_id": bill_id,
                "title": title,
                "introduced_date": date_str,
                "congress": congress,
                "bill_type": bill_type.lower(),
                "bill_number": bill_number,
                "full_text": text_content,
                "source_url": bill_url,
                "status": "introduced"  # Default status for new bills
            })
            
        logger.info(f"Successfully fetched and parsed {len(bills)} bills from the feed.")
        return bills

    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to fetch bill texts feed: {e}")
        return []
    except Exception as e:
        logger.error(f"An error occurred while parsing the bill texts feed: {e}")
        return []

def _download_and_extract_pdf_text(pdf_url: str) -> str:
    """
    Downloads a PDF from a URL and extracts its text content.
    """
    try:
        response = requests.get(pdf_url, headers=HEADERS, timeout=30)
        response.raise_for_status()
        
        with fitz.open(stream=response.content, filetype="pdf") as doc:
            text = ""
            for page in doc:
                text += page.get_text()
        return text
    except Exception as e:
        logger.error(f"Failed to download or extract text from PDF {pdf_url}: {e}")
        return ""

def _enrich_bill_with_text(bill: dict, text_chars: int) -> dict:
    """
    Enriches a bill dictionary with its full text, truncated to a specified number of characters.
    """
    if "full_text" in bill:
        bill["full_text"] = bill["full_text"][:text_chars]
    return bill