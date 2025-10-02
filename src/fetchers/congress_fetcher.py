"""
Congress.gov API and RSS fetcher for retrieving recent bills.
This module provides functionality to fetch bills from the Congress.gov API and RSS feeds.
"""

import os
import logging
from typing import List, Dict, Optional
import re
import requests
from dotenv import load_dotenv
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
import fitz  # PyMuPDF
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

CONGRESS_API_KEY = os.getenv('CONGRESS_API_KEY')
BASE_URL = "https://api.congress.gov/v3/"
BILL_TEXTS_FEED_URL = "https://www.congress.gov/bill-texts-received-today"

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
    
    Args:
        limit: Maximum number of bills to fetch
        include_text: Whether to download and include full bill text
        text_chars: Maximum characters of text to include (for truncation)
    
    Returns:
        List of bill dictionaries with full metadata and text
    """
    logger.info(f"Fetching bills from feed (limit={limit}, include_text={include_text})")
    
    try:
        # Use the dedicated feed parser
        from .feed_parser import parse_bill_texts_feed
        
        feed_bills = parse_bill_texts_feed(limit=limit)
        logger.info(f"Feed parser returned {len(feed_bills)} bills")
        
        if not feed_bills:
            logger.warning("No bills found in feed")
            return []
        
        # Enrich bills with full text if requested
        enriched_bills = []
        for bill in feed_bills:
            try:
                if include_text:
                    # Download and extract bill text
                    text_url = bill.get('text_url')
                    if text_url:
                        logger.info(f"Downloading text for {bill['bill_id']} from {text_url}")
                        full_text = download_bill_text(text_url, bill['bill_id'])
                        
                        # Validate text was successfully downloaded
                        if full_text and len(full_text.strip()) > 100:
                            bill['full_text'] = full_text[:text_chars] if text_chars else full_text
                            bill['text_source'] = 'feed'
                            logger.info(f"Successfully downloaded {len(full_text)} chars for {bill['bill_id']}")
                        else:
                            logger.warning(f"Downloaded text for {bill['bill_id']} is too short or empty")
                            bill['full_text'] = ""
                            bill['text_source'] = 'feed'
                    else:
                        logger.warning(f"No text URL for {bill['bill_id']}")
                        bill['full_text'] = ""
                        bill['text_source'] = 'feed'
                else:
                    bill['full_text'] = ""
                    bill['text_source'] = 'feed'
                
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
        
        logger.info(f"Successfully enriched {len(enriched_bills)} bills with text")
        return enriched_bills
        
    except ImportError as e:
        logger.error(f"Failed to import feed_parser: {e}")
        logger.info("Falling back to legacy feed parsing")
        return fetch_bill_texts_from_feed(limit=limit)
    except Exception as e:
        logger.error(f"Error in fetch_bills_from_feed: {e}")
        return []


def download_bill_text(url: str, bill_id: Optional[str] = None) -> str:
    """
    Download bill text from a given URL (PDF or TXT format).
    Supports both direct URLs and Congress.gov URLs.
    If the URL fails, tries alternative patterns for the same bill.
    
    Args:
        url: URL to the bill text (PDF or TXT)
        bill_id: Optional bill ID for generating alternative URLs
    
    Returns:
        Extracted text content or empty string on failure
    """
    if not url:
        return ""
    
    urls_to_try = [url]
    
    # If we have a bill ID and the URL looks like a constructed pattern,
    # try alternative URL patterns
    if bill_id and 'BILLS-' in url:
        # Parse bill ID to extract components
        match = re.match(r'([a-z]+)(\d+)-(\d+)', bill_id)
        if match:
            bill_type, bill_number, congress = match.groups()
            
            # Generate alternative URL patterns
            patterns = [
                f"https://www.congress.gov/{congress}/bills/{bill_type}{bill_number}/BILLS-{congress}{bill_type}{bill_number}ih.pdf",  # Introduced in House
                f"https://www.congress.gov/{congress}/bills/{bill_type}{bill_number}/BILLS-{congress}{bill_type}{bill_number}is.pdf",  # Introduced in Senate
                f"https://www.congress.gov/{congress}/bills/{bill_type}{bill_number}/BILLS-{congress}{bill_type}{bill_number}enr.pdf", # Enrolled
                f"https://www.congress.gov/{congress}/bills/{bill_type}{bill_number}/BILLS-{congress}{bill_type}{bill_number}eh.pdf",   # Engrossed in House
                f"https://www.congress.gov/{congress}/bills/{bill_type}{bill_number}/BILLS-{congress}{bill_type}{bill_number}es.pdf",   # Engrossed in Senate
                f"https://www.congress.gov/{congress}/bills/{bill_type}{bill_number}/BILLS-{congress}{bill_type}{bill_number}rs.pdf",   # Received in Senate
                f"https://www.congress.gov/{congress}/bills/{bill_type}{bill_number}/BILLS-{congress}{bill_type}{bill_number}rh.pdf"    # Received in House
            ]
            
            # Remove duplicates and the original URL if it's in the list
            urls_to_try = [url] + [pattern for pattern in patterns if pattern != url]
    
    for attempt_url in urls_to_try:
        try:
            # Ensure URL is absolute
            if not attempt_url.startswith('http'):
                attempt_url = f"https://www.congress.gov{attempt_url}"
            
            logger.debug(f"Downloading bill text from: {attempt_url}")
            
            # Download with timeout
            response = requests.get(attempt_url, timeout=30)
            response.raise_for_status()
            
            # Handle PDF files
            if attempt_url.endswith('.pdf'):
                text = _extract_text_from_pdf(response.content)
                if text and len(text.strip()) > 100:  # Validate we got meaningful text
                    logger.info(f"Successfully downloaded text from {attempt_url}")
                    return text
            
            # Handle TXT files
            elif attempt_url.endswith('.txt'):
                text = response.text
                if text and len(text.strip()) > 100:  # Validate we got meaningful text
                    logger.info(f"Successfully downloaded text from {attempt_url}")
                    return text
            
            # Try to detect format from content-type
            content_type = response.headers.get('content-type', '').lower()
            if 'pdf' in content_type:
                text = _extract_text_from_pdf(response.content)
                if text and len(text.strip()) > 100:
                    logger.info(f"Successfully downloaded text from {attempt_url}")
                    return text
            elif 'text' in content_type:
                text = response.text
                if text and len(text.strip()) > 100:
                    logger.info(f"Successfully downloaded text from {attempt_url}")
                    return text
            
            # Default: try as text
            text = response.text
            if text and len(text.strip()) > 100:
                logger.info(f"Successfully downloaded text from {attempt_url}")
                return text
            else:
                logger.warning(f"Downloaded text from {attempt_url} is too short or empty")
                
        except requests.HTTPError as e:
            if e.response.status_code == 404:
                logger.debug(f"URL not found: {attempt_url}")
                continue  # Try next URL
            else:
                logger.error(f"HTTP error downloading from {attempt_url}: {e}")
        except Exception as e:
            logger.error(f"Failed to download bill text from {attempt_url}: {e}")
            continue  # Try next URL
    
    logger.error(f"All download attempts failed for bill {bill_id or 'unknown'}")
    return ""


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

def fetch_bill_texts_from_feed(limit: int = 10) -> List[Dict[str, any]]:
    """
    Fetches and parses the "Bill Texts Received Today" feed from Congress.gov.
    """
    logger.info(f"Fetching bill texts from feed: {BILL_TEXTS_FEED_URL}")
    try:
        response = requests.get(BILL_TEXTS_FEED_URL, timeout=30)
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
        response = requests.get(pdf_url, timeout=30)
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