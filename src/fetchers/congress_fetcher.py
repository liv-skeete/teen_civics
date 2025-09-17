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

CONGRESS_API_KEY = os.getenv('CONGRESS_API_KEY')

BASE_URL = "https://api.congress.gov/v3/"



def get_recent_bills(limit: int = 5, include_text: bool = False, text_chars: int = 15000) -> List[Dict[str, str]]:
    logger.info("get_recent_bills function called")
    """
    Fetch the most recent bills from the Congress.gov API.
    Args:
        limit (int): Number of bills to retrieve (default: 5)
        
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
    if not CONGRESS_API_KEY:
        logger.error("CONGRESS_API_KEY not found in environment variables")
        raise ValueError("CONGRESS_API_KEY not found in environment variables")

    bills_endpoint = f"{BASE_URL}bill"
    params = {
        "format": "json",
        "limit": limit,
        "sort": "updateDate+desc"  # Sort by most recent update
    }

    logger.info(f"API Endpoint: {bills_endpoint}, params={params}")

    headers = {
        "X-API-Key": CONGRESS_API_KEY
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
        logger.info(f"API Response Status Code: {response.status_code}")

        data = response.json()
        bills = data.get('bills', [])
        if not bills:
            logger.warning("No bills found in API response")
            return []
            
        processed_bills = []
        for bill in bills:
            logger.info(f"Processing bill: {bill.get('number')}")
            try:
                bill_data = _process_bill_data(bill)
                if bill_data:
                    if include_text:
                        try:
                            bill_data = _enrich_bill_with_text(bill_data, text_chars)
                        except Exception as e:
                            logger.error(f"Error enriching bill with text: {e}")
                            # Continue without text enrichment if it fails
                    processed_bills.append(bill_data)
            except Exception as e:
                logger.error(f"Error processing individual bill: {e}")
            logger.info(f"Finished processing bill: {bill.get('number')}")

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
    logger.info(f"Processing bill data: {bill}")
    """
    Process raw bill data from API into standardized format.
    Args:
        bill (dict): Raw bill data from API response
        
    Returns:
        Dictionary containing processed bill information or None if processing fails
    """
    try:
        bill_id = f"{bill['type'].lower()}{bill['number']}"
        full_bill_id = f"{bill_id}-{bill.get('congress', '')}"
        
        title = bill.get('title', 'No title available')
        introduced_date = bill.get('introducedDate', '')
        if not introduced_date:
            introduced_date = bill.get('updateDate', '')

        sponsor_name = 'Unknown sponsor'
        sponsors = bill.get('sponsors', [])
        sponsor_name = 'Unknown sponsor'
        #if sponsors:
        #    sponsor = sponsors[0]
        #    sponsor_name = sponsor.get('fullName', 'Unknown sponsor')
        #    if sponsor.get('isByRequest', False):
        #        sponsor_name = f"{sponsor_name} (by request)"

        latest_action = bill.get('latestAction', {}).get('text', 'No action recorded')

        return {
            "bill_id": full_bill_id,
            "title": title,
            "introduced_date": introduced_date,
            "sponsor": sponsor_name,
            "latest_action": latest_action,
            "congress": bill.get('congress'),
            "bill_type": bill.get('type', '').lower(),
            "bill_number": str(bill.get('number', ''))
        }
    except Exception as e:
        logger.error(f"Error processing individual bill: {e}")
        return None


def _fetch_text_metadata(congress: int, bill_type: str, bill_number: str) -> dict | None:
    """
    Fetch text metadata for a specific bill from Congress.gov API.
    
    Args:
        congress: Congress number
        bill_type: Bill type (e.g., 'hr', 's', 'sjres')
        bill_number: Bill number
        
    Returns:
        Dictionary containing text metadata or None if request fails
    """
    if not CONGRESS_API_KEY:
        logger.error("CONGRESS_API_KEY not configured for text metadata fetch")
        return None
        
    text_endpoint = f"{BASE_URL}bill/{congress}/{bill_type}/{bill_number}/text"
    headers = {"X-API-Key": CONGRESS_API_KEY}
    params = {"format": "json"}
    
    try:
        logger.info(f"Fetching text metadata from: {text_endpoint}")
        response = requests.get(text_endpoint, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        return data
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to fetch text metadata: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error fetching text metadata: {e}")
        return None


def _normalize_format_type(format_type: str) -> str:
    """
    Normalize format type to handle Congress.gov specific labels.
    Maps 'formatted text' to 'html' and 'formatted xml' to 'xml'.
    """
    format_map = {
        'formatted text': 'html',
        'formatted xml': 'xml',
        'html': 'html',
        'txt': 'txt',
        'xml': 'xml',
        'pdf': 'pdf'
    }
    return format_map.get(format_type.lower(), format_type)


def _select_best_text_url(text_meta: dict) -> tuple[str | None, str | None]:
    """
    Select the best available text URL from text metadata.
    
    Args:
        text_meta: Text metadata from Congress.gov API
        
    Returns:
        Tuple of (normalized_format_type, url) or (None, None) if no suitable text found
    """
    try:
        text_versions = text_meta.get('textVersions', [])
        if not text_versions:
            logger.warning("No text versions found in metadata")
            return None, None
            
        # Get the most recent text version (first in array)
        latest_version = text_versions[0]
        formats = latest_version.get('formats', [])
        
        if not formats:
            logger.warning("No text formats found in latest version")
            return None, None
            
        # Prefer HTML or TXT formats, fall back to PDF
        preferred_formats = ['html', 'txt', 'xml']
        fallback_formats = ['pdf']
        
        for fmt in formats:
            original_format_type = fmt.get('type', '').lower()
            normalized_format_type = _normalize_format_type(original_format_type)
            url = fmt.get('url')
            
            if normalized_format_type in preferred_formats and url:
                logger.info(f"Selected {original_format_type.upper()} format (normalized to {normalized_format_type}) for text: {url}")
                return normalized_format_type, url
                
        # If no preferred formats found, try fallback
        for fmt in formats:
            original_format_type = fmt.get('type', '').lower()
            normalized_format_type = _normalize_format_type(original_format_type)
            url = fmt.get('url')
            
            if normalized_format_type in fallback_formats and url:
                logger.info(f"Selected fallback {original_format_type.upper()} format (normalized to {normalized_format_type}) for text: {url}")
                return normalized_format_type, url
                
        logger.warning("No suitable text format found")
        return None, None
        
    except Exception as e:
        logger.error(f"Error selecting best text URL: {e}")
        return None, None


def _download_plain_text(url: str, fmt: str, limit: int) -> str | None:
    """
    Download and extract plain text from URL.

    Supports:
      - html (BeautifulSoup if available; fallback to regex)
      - txt
      - xml (BeautifulSoup xml parser if available; fallback to regex)
      - pdf (pdfminer.six)

    Returns truncated text to 'limit' characters.
    """
    try:
        logger.info(f"Downloading text from: {url}")
        response = requests.get(url, timeout=45)
        response.raise_for_status()

        content_type = response.headers.get('content-type', '').lower()
        logger.info(f"Content-Type: {content_type}, Format: {fmt}")

        plain_text: str | None = None

        if 'pdf' in content_type or fmt == 'pdf':
            # PDF extraction
            try:
                from io import BytesIO
                from pdfminer.high_level import extract_text as pdf_extract_text
                pdf_bytes = BytesIO(response.content)
                pdf_text = pdf_extract_text(pdf_bytes) or ""
                # Normalize whitespace but keep line breaks
                import re
                pdf_text = re.sub(r"[ \t]+", " ", pdf_text)
                pdf_text = re.sub(r"\n{3,}", "\n\n", pdf_text)
                plain_text = pdf_text.strip()
                logger.info(f"Processed as PDF, extracted {len(plain_text)} characters")
            except Exception as e:
                logger.error(f"PDF extraction failed: {e}")
                plain_text = None

        elif 'html' in content_type or fmt == 'html':
            # Prefer BeautifulSoup to preserve structure
            try:
                from bs4 import BeautifulSoup
                html_content = response.text
                soup = BeautifulSoup(html_content, "html.parser")
                # Remove scripts/styles
                for tag in soup(["script", "style", "noscript"]):
                    tag.decompose()
                text = soup.get_text(separator="\n")
                import re
                text = re.sub(r"[ \t]+", " ", text)
                text = re.sub(r"\n{3,}", "\n\n", text)
                plain_text = text.strip()
                logger.info(f"Processed as HTML via BeautifulSoup, extracted {len(plain_text)} characters")
            except Exception as e:
                logger.warning(f"BeautifulSoup unavailable or failed ({e}); falling back to regex")
                import re
                html_content = response.text
                text = re.sub(r"<[^>]+>", " ", html_content)
                text = re.sub(r"\s+", " ", text).strip()
                plain_text = text
                logger.info(f"Processed as HTML via regex, extracted {len(plain_text)} characters")

        elif 'text/plain' in content_type or fmt == 'txt':
            plain_text = response.text.strip()
            logger.info(f"Processed as plain text, extracted {len(plain_text)} characters")

        elif 'xml' in content_type or fmt == 'xml':
            try:
                from bs4 import BeautifulSoup
                xml_content = response.text
                soup = BeautifulSoup(xml_content, "xml")
                text = soup.get_text(separator="\n")
                import re
                text = re.sub(r"[ \t]+", " ", text)
                text = re.sub(r"\n{3,}", "\n\n", text)
                plain_text = text.strip()
                logger.info(f"Processed as XML via BeautifulSoup, extracted {len(plain_text)} characters")
            except Exception as e:
                logger.warning(f"BeautifulSoup XML parse failed ({e}); falling back to regex")
                import re
                xml_content = response.text
                text = re.sub(r"<[^>]+>", " ", xml_content)
                text = re.sub(r"\s+", " ", text).strip()
                plain_text = text
                logger.info(f"Processed as XML via regex, extracted {len(plain_text)} characters")
        else:
            logger.warning(f"Cannot extract plain text from format: {fmt} with content-type: {content_type}")
            return None

        if plain_text is None:
            return None

        # Truncate to safe limit
        if len(plain_text) > limit:
            original_len = len(plain_text)
            plain_text = plain_text[:limit]
            logger.info(f"Truncated text from {original_len} to {limit} characters")

        logger.info(f"Successfully downloaded {len(plain_text)} characters of plain text")
        return plain_text

    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to download text: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error downloading text: {e}")
        return None


def _enrich_bill_with_text(bill: dict, text_chars: int) -> dict:
    """
    Enrich bill data with full text content.

    Strategy:
      1) Fetch latest text metadata
      2) Try preferred formats in order: html → txt → xml → pdf
      3) If first attempt yields no text or very short text, iterate all available formats and
         pick the longest successful extraction.
    """
    congress = bill.get('congress')
    bill_type = bill.get('bill_type')
    bill_number = bill.get('bill_number')

    if not all([congress, bill_type, bill_number]):
        logger.warning("Missing required identifiers for text enrichment")
        return bill

    # Fetch text metadata
    text_meta = _fetch_text_metadata(congress, bill_type, bill_number)
    if not text_meta:
        logger.warning(f"No text metadata found for {bill_type}{bill_number}-{congress}")
        return bill

    # Gather all candidate formats/urls (keep order preference)
    candidates: list[tuple[str, str]] = []
    try:
        text_versions = text_meta.get("textVersions", [])
        latest = text_versions[0] if text_versions else {}
        fmts = latest.get("formats", [])
        # Normalize and prioritize
        # Preference order
        preferred = ["html", "txt", "xml", "pdf"]
        normalized = []
        for f in fmts:
            original = (f.get("type") or "").lower()
            normalized_type = _normalize_format_type(original)
            url = f.get("url")
            if url:
                normalized.append((normalized_type, url))
        # Sort by preference rank
        rank = {t: i for i, t in enumerate(preferred)}
        normalized.sort(key=lambda t: rank.get(t[0], 999))
        candidates = normalized
    except Exception as e:
        logger.warning(f"Failed to enumerate formats from metadata: {e}")
        # Fallback to selector
        fmt, url = _select_best_text_url(text_meta)
        if url:
            candidates = [(fmt, url)]

    best_text = None
    best_fmt = None
    best_url = None

    # Try candidates until we get a decent-sized text
    for fmt, url in candidates:
        text = None
        try:
            text = _download_plain_text(url, fmt, text_chars)
        except Exception as e:
            logger.warning(f"Extraction failed for {fmt} at {url}: {e}")
            continue

        if text:
            if best_text is None or len(text) > len(best_text):
                best_text, best_fmt, best_url = text, fmt, url
            # Early accept if reasonably large (heuristic)
            if len(text) >= 5000:
                break

    # Record results
    if best_url:
        bill['text_url'] = best_url
        bill['text_format'] = best_fmt

    if best_text:
        bill['full_text'] = best_text
        logger.info(f"Attached full text (fmt={best_fmt}) with {len(best_text)} chars to bill {bill.get('bill_id')}")
        snippet = best_text[:200] + "..." if len(best_text) > 200 else best_text
        logger.info(f"Text snippet: {snippet}")
    else:
        logger.info(f"Added text URL metadata but no extractable text for bill {bill.get('bill_id')}")

    return bill


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
            if 'text_url' in bill:
                print(f"  Text URL: {bill.get('text_url')}")
            if 'full_text' in bill:
                text_preview = bill['full_text'][:100] + "..." if len(bill['full_text']) > 100 else bill['full_text']
                print(f"  Text Preview: {text_preview}")
    except Exception as e:
        print(f"Error: {e}")