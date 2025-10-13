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

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning("Playwright not available. Browser-based fetching will be disabled.")

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Feed URL
BILL_TEXTS_FEED_URL = "https://www.congress.gov/bill-texts-received-today"

# Enhanced headers to avoid 403 errors - more realistic browser headers
# Rotating user agents to avoid detection
USER_AGENTS = [
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/126.0'
]

HEADERS = {
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'none',
    'Sec-Fetch-User': '?1',
    'Cache-Control': 'max-age=0',
    'sec-ch-ua': '"Not/A)Brand";v="8", "Chromium";v="126", "Google Chrome";v="126"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"macOS"',
    'DNT': '1',
    'Referer': 'https://www.congress.gov/'
}

# Create a session for persistent connections
session = requests.Session()
session.headers.update(HEADERS)

def get_random_user_agent():
    """Return a random user agent from the list"""
    import random
    return random.choice(USER_AGENTS)

def update_session_headers():
    """Update session headers with a random user agent"""
    session.headers.update({
        'User-Agent': get_random_user_agent()
    })

def running_in_ci() -> bool:
    """
    Check if the code is running in a CI environment.
    
    Returns:
        True if running in CI, False otherwise
    """
    import os
    return bool(os.getenv('CI')) or bool(os.getenv('GITHUB_ACTIONS')) or os.getenv('CONGRESS_FETCH_MODE') == 'api_only'

def fetch_feed_with_browser(url: str, timeout: int = 30000) -> Optional[str]:
    """
    Fetch feed using Playwright browser to bypass 403 errors.
    
    Args:
        url: The feed URL to fetch
        timeout: Timeout in milliseconds (default: 30000)
        
    Returns:
        HTML content or None if failed
    """
    if not PLAYWRIGHT_AVAILABLE:
        logger.warning("Playwright not available, cannot use browser fetch")
        return None
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            
            # Set realistic user agent
            page.set_extra_http_headers({
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
            })
            
            logger.info(f"🌐 Fetching feed with browser: {url}")
            response = page.goto(url, timeout=timeout, wait_until='networkidle')
            
            if response and response.status == 200:
                content = page.content()
                browser.close()
                logger.info(f"✅ Successfully fetched feed with browser ({len(content)} chars)")
                return content
            else:
                status = response.status if response else 'unknown'
                logger.warning(f"⚠️ Browser fetch returned status {status}")
                browser.close()
                return None
                
    except Exception as e:
        logger.error(f"❌ Browser fetch failed: {e}")
        return None


def scrape_bill_tracker(source_url: str, browser_context=None) -> Optional[List[Dict[str, any]]]:
    """
    Scrape the full bill progress tracker from a Congress.gov bill page using Playwright.
    Returns list of {"name": str, "selected": bool}
    or None if scraping fails
    
    Args:
        source_url: The URL of the bill page
        browser_context: An existing Playwright browser context to reuse (optional)
    """
    # Check if running in CI and skip HTML tracker scraping
    if running_in_ci():
        logger.debug("Skipping HTML tracker scraping in CI mode")
        return None
    if not PLAYWRIGHT_AVAILABLE:
        logger.warning("Playwright not available, cannot scrape tracker")
        return None
    
    # If a browser context is provided, use it; otherwise create a new one
    should_close_browser = browser_context is None
    try:
        if browser_context is None:
            from playwright.sync_api import sync_playwright
            p = sync_playwright().start()
            browser = p.chromium.launch(headless=True)
            browser_context = browser.new_context()
        
        page = browser_context.new_page()
        # Set realistic user agent and headers
        page.set_extra_http_headers({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0',
            'sec-ch-ua': '"Not/A)Brand";v="8", "Chromium";v="126", "Google Chrome";v="126"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"macOS"',
            'DNT': '1',
            'Referer': 'https://www.congress.gov/'
        })
        logger.debug(f"🌐 Fetching bill page for tracker: {source_url}")
        # Add a small delay to help with anti-bot measures
        import time
        time.sleep(1)
        response = page.goto(source_url, timeout=15000, wait_until='networkidle')
        if not response or response.status != 200:
            logger.warning(f"⚠️ Failed to load page: {source_url} (status: {response.status if response else 'unknown'})")
            if should_close_browser:
                browser_context.close()
                if 'p' in locals():
                    p.stop()
            return None
        content = page.content()
        soup = BeautifulSoup(content, 'html.parser')
        tracker = soup.find('ol', class_='bill_progress')
        if not tracker:
            logger.warning(f"⚠️ Could not find bill_progress tracker on page: {source_url}")
            if should_close_browser:
                browser_context.close()
                if 'p' in locals():
                    p.stop()
            return None
        steps = []
        for li in tracker.find_all('li'):
            # Get only the direct text content, not including nested elements
            name = li.find(text=True, recursive=False)
            if name:
                name = name.strip()
            else:
                # Fallback to get_text if direct text fails
                name = li.get_text(strip=True)
            selected = 'selected' in li.get('class', [])
            steps.append({"name": name, "selected": selected})
        logger.info(f"✅ Scraped {len(steps)} tracker steps from {source_url}")
        if should_close_browser:
            browser_context.close()
            if 'p' in locals():
                p.stop()
        return steps
    except Exception as e:
        logger.warning(f"⚠️ Failed to scrape tracker from {source_url}: {e}")
        if should_close_browser and 'browser_context' in locals():
            browser_context.close()
            if 'p' in locals():
                p.stop()
        return None

def scrape_multiple_bill_trackers(source_urls: List[str]) -> Dict[str, Optional[List[Dict[str, any]]]]:
    """
    Scrape multiple bill progress trackers from Congress.gov bill pages using a single browser session.
    
    Args:
        source_urls: List of URLs to bill pages
        
    Returns:
        Dictionary mapping source_url to tracker data (list of steps)
    """
    # Check if running in CI and skip HTML tracker scraping
    if running_in_ci():
        logger.debug("Skipping HTML tracker scraping in CI mode")
        return {url: None for url in source_urls}
    if not PLAYWRIGHT_AVAILABLE:
        logger.warning("Playwright not available, cannot scrape trackers")
        return {url: None for url in source_urls}
    
    results = {}
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            
            # Set realistic user agent and headers for the context
            context.set_extra_http_headers({
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none',
                'Sec-Fetch-User': '?1',
                'Cache-Control': 'max-age=0',
                'sec-ch-ua': '"Not/A)Brand";v="8", "Chromium";v="126", "Google Chrome";v="126"',
                'sec-ch-ua-mobile': '?0',
                'sec-ch-ua-platform': '"macOS"',
                'DNT': '1',
                'Referer': 'https://www.congress.gov/'
            })
            
            for url in source_urls:
                try:
                    # Reuse the same browser context for all requests
                    results[url] = scrape_bill_tracker(url, context)
                except Exception as e:
                    logger.warning(f"⚠️ Failed to scrape tracker from {url}: {e}")
                    results[url] = None
            
            browser.close()
            
    except Exception as e:
        logger.error(f"❌ Failed to create browser context for scraping: {e}")
        # Fallback to individual scraping if context creation fails
        for url in source_urls:
            try:
                results[url] = scrape_bill_tracker(url)
            except Exception as e2:
                logger.warning(f"⚠️ Failed to scrape tracker from {url} (fallback): {e2}")
                results[url] = None
    
    return results


def scrape_tracker_status(source_url: str) -> Optional[str]:
    """
    Scrape the bill tracker status from a Congress.gov bill page.
    
    Args:
        source_url: URL to the bill page
        
    Returns:
        The name of the last step marked as selected in the tracker, or None if scraping fails
    """
    # Call the existing scrape_bill_tracker function to get tracker steps
    steps = scrape_bill_tracker(source_url)
    
    # If scraping failed or no steps found, return None
    if not steps:
        return None
    
    # Find the last step where selected is True
    status = None
    for step in steps:
        if step.get("selected", False):
            status = step.get("name")
    
    return status


def normalize_status(action_text: str, source_url: Optional[str] = None) -> str:
    """
    Normalize the bill status. Attempts to scrape the tracker status from Congress.gov
    if source_url is provided, otherwise falls back to keyword matching on action_text.

    Args:
        action_text: The full text of the latest action.
        source_url: Optional URL to the bill page for scraping tracker status.

    Returns:
        A standardized status string.
    """
    # First, try to scrape the tracker status if we have a source URL
    if source_url:
        try:
            # Inline tracker scraping to avoid NameError on scrape_tracker_status
            steps = scrape_bill_tracker(source_url)
            if steps:
                status = None
                for step in steps:
                    if step.get("selected", False):
                        status = step.get("name")
                if status:
                    return status
        except Exception as e:
            logger.debug(f"normalize_status: tracker scrape failed for {source_url}: {e}")
    
    # Fallback to keyword matching on action text
    if not action_text:
        return None
        
    action_text_lower = action_text.lower()
    
    if "became public law" in action_text_lower or "signed by president" in action_text_lower:
        return "Became Law"
    if "passed house" in action_text_lower or "agreed to in house" in action_text_lower:
        return "Passed House"
    if "passed senate" in action_text_lower or "agreed to in senate" in action_text_lower:
        return "Passed Senate"
    if "reported" in action_text_lower or "placed on the union calendar" in action_text_lower:
        return "Reported by Committee"
    if "placed on senate legislative calendar" in action_text_lower or "placed on calendar" in action_text_lower:
        return "Introduced"
    if "introduced" in action_text_lower:
        return "Introduced"
        
    return action_text


def parse_bill_texts_feed(limit: int = 50) -> List[Dict[str, Any]]:
    """
    Parse the "Bill Texts Received Today" HTML feed from Congress.gov.
    Uses a three-tier approach:
    1. Browser-based fetch (bypasses 403 errors)
    2. Traditional requests library (fallback)
    3. API fallback (if feed is empty or fails)
    
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
    """
    # Check if running in CI and force API-only mode
    if running_in_ci():
        logger.info("⚙️ CI environment detected. Running in API-only mode.")
        return _fetch_bills_from_api(limit)
    
    logger.info(f"Fetching bill texts feed from: {BILL_TEXTS_FEED_URL}")
    
    html_content = None
    fetch_method = None
    
    # Tier 1: Try browser-based fetch first (bypasses 403)
    if PLAYWRIGHT_AVAILABLE:
        logger.info("🎯 Tier 1: Attempting browser-based fetch...")
        html_content = fetch_feed_with_browser(BILL_TEXTS_FEED_URL)
        if html_content:
            fetch_method = 'browser'
            logger.info("✅ Browser fetch succeeded")
    
    # Tier 2: Fall back to requests library if browser failed
    if not html_content:
        logger.info("🎯 Tier 2: Attempting requests library fetch...")
        feed_success = False
        
        for attempt in range(3):
            try:
                logger.info(f"Attempt {attempt + 1}/3 to fetch feed with requests")
                
                # Add delay between retries
                if attempt > 0:
                    delay = 2 ** attempt  # Exponential backoff: 2, 4 seconds
                    logger.info(f"Waiting {delay} seconds before retry...")
                    time.sleep(delay)
                
                # Update headers with random user agent for each attempt
                update_session_headers()
                
                # Fetch the feed with timeout and enhanced headers
                response = session.get(BILL_TEXTS_FEED_URL, timeout=30)
                response.raise_for_status()
                html_content = response.text
                fetch_method = 'requests'
                logger.info(f"✅ Feed fetched successfully with requests (status: {response.status_code})")
                feed_success = True
                break
                
            except requests.HTTPError as e:
                if e.response.status_code == 403:
                    logger.warning(f"⚠️ 403 Forbidden error on attempt {attempt + 1}/3")
                    if attempt == 2:  # Last attempt
                        logger.error("❌ All requests fetch attempts failed with 403")
                else:
                    logger.error(f"❌ HTTP error on attempt {attempt + 1}/3: {e}")
            except requests.RequestException as e:
                logger.error(f"❌ Request error on attempt {attempt + 1}/3: {e}")
    
    # Tier 3: If both browser and requests failed, fall back to API
    if not html_content:
        logger.warning("🎯 Tier 3: Both browser and requests failed. Falling back to Congress.gov API...")
        return _fetch_bills_from_api(limit)
    
    # Parse HTML with lxml parser
    try:
        soup = BeautifulSoup(html_content, 'lxml')
        logger.info(f"✅ HTML parsed successfully with lxml parser (fetched via {fetch_method})")
    except Exception as e:
        logger.warning(f"⚠️ lxml parser failed, falling back to html.parser: {e}")
        soup = BeautifulSoup(html_content, 'html.parser')
    
    # Extract bills from the feed
    bills = []
    
    # Find the main content area - the feed uses a table structure
    # Look for bill entries in the page
    bill_items = []
    
    # First try the standard table structure
    table = soup.find('table', {'class': 'table'})
    if table:
        logger.info("Found bill texts table")
        rows = table.find('tbody').find_all('tr')
        bill_items = rows[:limit]
    
    if not bill_items:
        # Try alternative selectors - list structure
        bill_items = soup.find_all('li', class_='expanded')
    
    if not bill_items:
        # Try alternative selectors - item wrappers
        bill_items = soup.find_all('div', class_='item-wrapper')
    
    if not bill_items:
        logger.warning("⚠️ No bill items found in feed using standard selectors")
        # Try to find any links that look like bill links
        all_links = soup.find_all('a', href=re.compile(r'/bill/\d+/(hr|s|hjres|sjres|hconres|sconres|hres|sres)-\d+'))
        if all_links:
            logger.info(f"Found {len(all_links)} bill links using fallback method")
            bill_items = [link.parent for link in all_links[:limit]]
        else:
            # Feed is empty (ephemeral nature) - this is not an error
            logger.info("ℹ️ Feed is empty (no bills received today). This is normal for the ephemeral feed.")
            logger.info("🎯 Tier 3: Falling back to API to find bills with recently available text...")
            return _fetch_bills_from_api(limit)
    
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
    
    if not bills:
        logger.info("ℹ️ No bills extracted from feed items. Feed may be empty today.")
        logger.info("🎯 Tier 3: Falling back to API to find bills with recently available text...")
        return _fetch_bills_from_api(limit)
    
    logger.info(f"✅ Successfully parsed {len(bills)} bills from feed (via {fetch_method})")
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
        
        # Find text URL (PDF or TXT) - look for actual text links in the item
        text_url = None
        
        # For table row structure (the actual feed format)
        if hasattr(item, 'find_all') and item.name == 'tr':
            cols = item.find_all('td')
            if len(cols) >= 2:  # We need at least 2 columns (bill info and text version)
                # The second column contains the text version links
                text_col = cols[1] if len(cols) >= 2 else None
                if text_col:
                    # Look for PDF link first (most reliable)
                    pdf_link = text_col.find('a', href=re.compile(r'\.pdf$'))
                    if pdf_link:
                        text_url = pdf_link.get('href')
                    else:
                        # Fallback to TXT link
                        txt_link = text_col.find('a', href=re.compile(r'format=txt'))
                        if txt_link:
                            text_url = txt_link.get('href')
        
        # If not a table row, try other structures
        if not text_url:
            # Look for direct text links
            text_links = item.find_all('a', href=re.compile(r'\.(pdf|txt)$|format=(txt|xml)'))
            if text_links:
                # Prefer PDF, fallback to TXT
                pdf_link = next((link for link in text_links if link.get('href', '').endswith('.pdf')), None)
                txt_link = next((link for link in text_links if 'format=txt' in link.get('href', '') or link.get('href', '').endswith('.txt')), None)
                
                if pdf_link:
                    text_url = pdf_link.get('href')
                elif txt_link:
                    text_url = txt_link.get('href')
        
        # Ensure URL is absolute
        if text_url and not text_url.startswith('http'):
            text_url = f"https://www.congress.gov{text_url}"
        
        # Use current date as received date
        text_received_date = datetime.now().isoformat()

        # Extract introduced date and latest action (status)
        introduced_date = None
        latest_action = None
        
        # These details are often in a list within the item
        if hasattr(item, 'find_all'):
            details_list = item.find('ul', class_='list-unstyled')
            if details_list:
                for li in details_list.find_all('li'):
                    text = li.get_text(strip=True)
                    if "Introduced in" in text:
                        date_match = re.search(r'(\d{2}/\d{2}/\d{4})', text)
                        if date_match:
                            introduced_date = date_match.group(1)
                    if "Latest Action:" in text:
                        latest_action = text.replace("Latest Action:", "").strip()

        # Construct source_url (bill page, not direct text)
        source_url = f"https://www.congress.gov/bill/{congress}th-congress/{bill_type_full}/{bill_number}"
        
        # Log whether we found a direct text_url or will need to construct/scrape
        if text_url:
            logger.info(f"✅ Extracted direct text_url from feed for {bill_id}: {text_url}")
        else:
            logger.warning(f"⚠️ No direct text_url found in feed for {bill_id}, will use constructed source_url: {source_url}")
        
        return {
            'bill_id': bill_id,
            'title': title,
            'source_url': source_url,
            'text_url': text_url,
            'text_version': text_version,
            'text_received_date': text_received_date,
            'congress': congress,
            'bill_type': bill_type,
            'bill_number': bill_number,
            'introduced_date': introduced_date,
            'latest_action': normalize_status(latest_action, source_url)
        }
        
    except Exception as e:
        logger.error(f"Error extracting bill data: {e}")
        return None


def _check_bill_has_text(congress: str, bill_type: str, bill_number: str, api_key: str) -> bool:
    """
    Check if a bill has text available via the API.
    
    Args:
        congress: Congress number
        bill_type: Bill type (e.g., 'hr', 's')
        bill_number: Bill number
        api_key: API key
        
    Returns:
        True if bill has text available, False otherwise
    """
    try:
        text_url = f"https://api.congress.gov/v3/bill/{congress}/{bill_type}/{bill_number}/text"
        params = {'api_key': api_key, 'format': 'json'}
        
        response = requests.get(text_url, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            text_versions = data.get('textVersions', [])
            return len(text_versions) > 0
        return False
    except Exception as e:
        logger.debug(f"Error checking text availability for {bill_type}{bill_number}-{congress}: {e}")
        return False


def _fetch_bills_from_api(limit: int = 50) -> List[Dict[str, Any]]:
    """
    Fallback method to fetch bills using the Congress.gov API.
    This is used when the feed is empty or encounters errors.
    
    IMPORTANT: This filters bills to only return those with text available,
    addressing the issue where sort=updateDate+desc returns recently updated
    bills that may not have text yet.
    
    Args:
        limit: Maximum number of bills to return
    
    Returns:
        List of bill dictionaries (only bills with text available)
    """
    import os
    from dotenv import load_dotenv
    
    load_dotenv()
    api_key = os.getenv('CONGRESS_API_KEY')
    
    if not api_key:
        logger.error("❌ CONGRESS_API_KEY not found in environment. Cannot use API fallback.")
        return []
    
    logger.info(f"📡 Fetching bills from Congress.gov API (requesting {limit * 3} to filter for text availability)")
    
    try:
        # Fetch MORE bills than needed since we'll filter for text availability
        # Request 3x the limit to account for bills without text
        api_url = f"https://api.congress.gov/v3/bill"
        params = {
            'api_key': api_key,
            'format': 'json',
            'limit': min(limit * 3, 250),  # Cap at API max
            'sort': 'updateDate+desc'
        }
        
        response = requests.get(api_url, params=params, headers=HEADERS, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        bills_with_text = []
        bills_checked = 0
        bills_with_text_count = 0
        bills_without_text_count = 0
        
        if 'bills' in data:
            logger.info(f"📋 API returned {len(data['bills'])} bills, checking for text availability...")
            
            for bill_data in data['bills']:
                try:
                    # Extract bill information
                    bill_type = bill_data.get('type', '').lower()
                    bill_number = bill_data.get('number', '')
                    congress = bill_data.get('congress', '')
                    
                    if not all([bill_type, bill_number, congress]):
                        continue
                    
                    bills_checked += 1
                    bill_id = f"{bill_type}{bill_number}-{congress}"
                    
                    # Check if this bill has text available
                    has_text = _check_bill_has_text(congress, bill_type, bill_number, api_key)
                    
                    if not has_text:
                        bills_without_text_count += 1
                        logger.debug(f"⏭️  Skipping {bill_id} - no text available")
                        continue
                    
                    bills_with_text_count += 1
                    logger.info(f"✅ {bill_id} has text available")
                    
                    title = bill_data.get('title', f"Bill {bill_id}")
                    
                    # Get the latest action date and text as text_received_date and latest_action
                    latest_action = bill_data.get('latestAction', {})
                    action_date = latest_action.get('actionDate', datetime.now().isoformat())
                    action_text = latest_action.get('text', '')
                    
                    # Fetch text version details
                    text_url = None
                    text_version_name = 'Introduced'
                    
                    try:
                        text_versions_url = f"https://api.congress.gov/v3/bill/{congress}/{bill_type}/{bill_number}/text"
                        text_params = {'api_key': api_key, 'format': 'json'}
                        text_response = requests.get(text_versions_url, params=text_params, timeout=10)
                        
                        if text_response.status_code == 200:
                            text_data = text_response.json()
                            text_versions = text_data.get('textVersions', [])
                            
                            if text_versions:
                                # Get the most recent text version
                                latest_version = text_versions[0]
                                text_version_name = latest_version.get('type', 'Introduced')
                                
                                # Get formats for this version
                                formats = latest_version.get('formats', [])
                                
                                # Prefer PDF, then TXT
                                pdf_format = next((fmt for fmt in formats if fmt.get('type') == 'PDF'), None)
                                txt_format = next((fmt for fmt in formats if fmt.get('type') == 'TXT'), None)
                                
                                if pdf_format and 'url' in pdf_format:
                                    text_url = pdf_format['url']
                                elif txt_format and 'url' in txt_format:
                                    text_url = txt_format['url']
                    except Exception as e:
                        logger.debug(f"Could not fetch text version details for {bill_id}: {e}")
                    
                    # Construct the source URL to the main bill page
                    # Convert short bill type to full form for URL
                    bill_type_url_map = {
                        'hr': 'house-bill',
                        's': 'senate-bill',
                        'hjres': 'house-joint-resolution',
                        'sjres': 'senate-joint-resolution',
                        'hconres': 'house-concurrent-resolution',
                        'sconres': 'senate-concurrent-resolution',
                        'hres': 'house-resolution',
                        'sres': 'senate-resolution'
                    }
                    bill_type_full = bill_type_url_map.get(bill_type, 'house-bill')
                    source_url = f"https://www.congress.gov/bill/{congress}th-congress/{bill_type_full}/{bill_number}"
                    
                    bills_with_text.append({
                        'bill_id': bill_id,
                        'title': title,
                        'source_url': source_url,
                        'text_url': text_url,
                        'text_version': text_version_name,
                        'text_received_date': action_date,
                        'congress': str(congress),
                        'bill_type': bill_type,
                        'bill_number': str(bill_number),
                        'latest_action': normalize_status(action_text, source_url),
                        'api_data': bill_data
                    })
                    
                    # Stop once we have enough bills with text
                    if len(bills_with_text) >= limit:
                        logger.info(f"✅ Reached target of {limit} bills with text")
                        break
                    
                except Exception as e:
                    logger.warning(f"⚠️ Error processing API bill data: {e}")
                    continue
        
        logger.info(f"📊 API Filtering Results:")
        logger.info(f"   - Bills checked: {bills_checked}")
        logger.info(f"   - Bills WITH text: {bills_with_text_count}")
        logger.info(f"   - Bills WITHOUT text (filtered): {bills_without_text_count}")
        logger.info(f"   - Bills returned: {len(bills_with_text)}")
        
        if not bills_with_text:
            logger.warning("⚠️ No bills with text found in API results")
        
        return bills_with_text
        
    except requests.RequestException as e:
        logger.error(f"❌ Failed to fetch bills from API: {e}")
        return []
    except Exception as e:
        logger.error(f"❌ Error processing API response: {e}")
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