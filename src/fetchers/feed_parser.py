#!/usr/bin/env python3
"""
Fetches recent bills from the Congress.gov API and enriches them with tracker data.
"""

import logging
import re
import time
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import os
import requests
from bs4 import BeautifulSoup

# Configure logging first
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
    logger.info("✅ Playwright successfully imported and available")
except ImportError as e:
    PLAYWRIGHT_AVAILABLE = False
    logger.warning(f"⚠️ Playwright not available: {e}")

def running_in_ci() -> bool:
    """Check if the code is running in a CI environment."""
    return bool(os.getenv('CI')) or bool(os.getenv('GITHUB_ACTIONS'))

def scrape_bill_tracker(source_url: str, force_scrape=False, max_retries: int = 3, base_timeout: int = 30000) -> Optional[List[Dict[str, any]]]:
    """
    Scrapes the bill progress tracker from a Congress.gov bill page.
    Tries multiple selector variants and an accessibility fallback.
    Includes retry logic and increased timeout to prevent failures.
    """
    if running_in_ci() and not force_scrape:
        logger.debug("Skipping HTML tracker scraping in CI mode")
        return None
    if not PLAYWRIGHT_AVAILABLE:
        logger.warning("Playwright not available, cannot scrape tracker")
        return None

    for attempt in range(max_retries):
        try:
            # Increase timeout with each retry (exponential backoff)
            timeout = base_timeout * (2 ** attempt)
            logger.info(f"Attempt {attempt + 1}/{max_retries} with timeout {timeout}ms for {source_url}")
            
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                try:
                    context = browser.new_context(
                        user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                                   'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
                    )
                    page = context.new_page()
                    time.sleep(1)  # Small delay
                    response = page.goto(source_url, timeout=timeout, wait_until='networkidle')

                    if not response or response.status != 200:
                        logger.warning(f"⚠️ Failed to load page: {source_url} (status: {response.status if response else 'unknown'})")
                        if attempt < max_retries - 1:
                            logger.info(f"Retrying in 2 seconds...")
                            time.sleep(2)
                            continue
                        return None

                    # Best-effort wait for either tracker list or the hidden status paragraph
                    try:
                        page.wait_for_selector("ol.bill_progress, ol.bill-progress, p.hide_fromsighted", timeout=min(timeout, 10000))
                    except Exception:
                        pass

                    content = page.content()
                    soup = BeautifulSoup(content, 'html.parser')

                    # 1) Primary: ordered list tracker (support old/new class names)
                    tracker = soup.find('ol', class_=['bill_progress', 'bill-progress'])
                    steps: List[Dict[str, Any]] = []

                    if tracker:
                        for li in tracker.find_all('li'):
                            # Get only the direct text from the li element, excluding hidden div content
                            text_parts = []
                            for content in li.contents:
                                # Skip hidden divs with class 'sol-step-info'
                                if hasattr(content, 'name') and content.name == 'div' and 'sol-step-info' in (content.get('class', [])):
                                    continue
                                # Extract text from text nodes and direct strings
                                elif hasattr(content, 'string') and content.string:
                                    text_parts.append(content.string)
                                elif isinstance(content, str):
                                    text_parts.append(content)
                            
                            name = ''.join(text_parts).strip()
                            classes = (li.get('class') or [])
                            selected = ('selected' in classes) or ('current' in classes)
                            if name:
                                steps.append({"name": name, "selected": selected})

                        if steps:
                            logger.info(f"✅ Scraped {len(steps)} tracker steps from {source_url}")
                            return steps

                    # 2) Fallback: A11y paragraph explicitly states status
                    status_text = None
                    try:
                        for p_tag in soup.find_all('p', class_='hide_fromsighted'):
                            text = p_tag.get_text(" ", strip=True)
                            m = re.search(r'This bill has the status\s*(.+)$', text, re.IGNORECASE)
                            if m:
                                status_text = m.group(1).strip()
                                break
                    except Exception:
                        status_text = None

                    if status_text:
                        logger.info(f"✅ Parsed status from hidden paragraph for {source_url}: {status_text}")
                        # Return a minimal steps list with the current status selected
                        return [{"name": status_text, "selected": True}]

                    logger.warning(f"⚠️ Could not find bill tracker or status on page: {source_url}")
                finally:
                    try:
                        if 'context' in locals():
                            context.close()
                    except Exception as e:
                        logger.debug(f"Error closing context: {e}")
                    try:
                        browser.close()
                    except Exception as e:
                        logger.debug(f"Error closing browser: {e}")
                if attempt < max_retries - 1:
                    logger.info(f"Retrying in 2 seconds...")
                    time.sleep(2)
                    continue
                return None
        except Exception as e:
            logger.warning(f"⚠️ Attempt {attempt + 1} failed to scrape tracker from {source_url}: {e}")
            if attempt < max_retries - 1:
                logger.info(f"Retrying in 2 seconds...")
                time.sleep(2)
                continue
            return None

def normalize_status(action_text: str, source_url: Optional[str] = None) -> str:
    """
    Normalize the bill status by scraping the tracker or using keyword matching.
    """
    if source_url:
        try:
            steps = scrape_bill_tracker(source_url, force_scrape=True)
            if steps:
                for step in steps:
                    if step.get("selected"):
                        status = step.get("name", "").strip()
                        if status:
                            logger.info(f"✅ Extracted bill status from tracker: '{status}' for {source_url}")
                            return status
        except Exception as e:
            logger.debug(f"Tracker scrape failed for {source_url}: {e}")
    
    action_text_lower = (action_text or "").lower()
    if "became public law" in action_text_lower or "signed by president" in action_text_lower:
        return "Became Law"
    if "passed house" in action_text_lower or "agreed to in house" in action_text_lower:
        return "Passed House"
    if "passed senate" in action_text_lower or "agreed to in senate" in action_text_lower:
        return "Passed Senate"
    if "reported" in action_text_lower or "placed on the union calendar" in action_text_lower:
        return "Reported by Committee"
    if "introduced" in action_text_lower:
        return "Introduced"
    return "Introduced" # Default to Introduced

def construct_bill_url(congress: str, bill_type: str, bill_number: str) -> str:
    """
    Constructs the user-facing URL for a bill on Congress.gov.
    """
    bill_type_map = {
        "hr": "house-bill",
        "s": "senate-bill",
        "hres": "house-resolution",
        "sres": "senate-resolution",
        "hjres": "house-joint-resolution",
        "sjres": "senate-joint-resolution",
        "hconres": "house-concurrent-resolution",
        "sconres": "senate-concurrent-resolution",
    }
    bill_type_slug = bill_type_map.get(bill_type.lower())
    if not bill_type_slug:
        return f"https://www.congress.gov/search?q={bill_type}{bill_number}"
    return f"https://www.congress.gov/bill/{congress}th-congress/{bill_type_slug}/{bill_number}"

def fetch_bill_ids_from_texts_received_today() -> List[str]:
    """
    Scrapes the 'Bill Texts Received Today' page to find bills that have new texts.
    Uses Playwright for reliable scraping (works in both local and CI environments).
    Falls back to requests with hardened headers if Playwright is unavailable.
    """
    url = "https://www.congress.gov/bill-texts-received-today"
    logger.info(f"Scraping for bill IDs from {url}")
    logger.info(f"Playwright available: {PLAYWRIGHT_AVAILABLE}")

    # 1) Try Playwright first (works in both local and CI environments)
    # Note: CI check removed - Playwright is installed in CI and should be used
    # to avoid Cloudflare 403 blocks that occur with requests-based fallback
    if PLAYWRIGHT_AVAILABLE:
        logger.info("Attempting to use Playwright for scraping...")
        max_retries = 2
        base_timeout = 30000  # ms
        for attempt in range(max_retries):
            try:
                timeout = base_timeout * (attempt + 1)
                logger.info(f"Playwright attempt {attempt + 1}/{max_retries} with timeout {timeout}ms")
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=True)
                    try:
                        ua = USER_AGENTS[attempt % len(USER_AGENTS)] if 'USER_AGENTS' in globals() and USER_AGENTS else HEADERS.get('User-Agent')
                        context = browser.new_context(
                            user_agent=ua,
                            locale='en-US'
                        )
                        page = context.new_page()
                        time.sleep(1)  # small delay
                        page.goto(url, timeout=timeout, wait_until='networkidle')

                        # Best-effort wait for table presence
                        try:
                            page.wait_for_selector("table.item_table", timeout=min(timeout, 10000))
                        except Exception:
                            pass

                        html = page.content()
                        soup = BeautifulSoup(html, 'html.parser')

                        bill_ids: List[str] = []
                        table = soup.find('table', class_='item_table')
                        if not table:
                            logger.info("No bill texts table found on page (may be empty today).")
                            return []

                        tbody = table.find('tbody')
                        if not tbody:
                            logger.info("No table body found in bill texts page.")
                            return []

                        for row in tbody.find_all('tr'):
                            strong_tag = row.find('strong')
                            if strong_tag:
                                # Text is like: S.2392 [119th]
                                match = re.search(r'([a-zA-Z\.]+)(\d+)\s*\[(\d+)th\]', strong_tag.text)
                                if match:
                                    bill_type, bill_number, congress = match.groups()
                                    bill_type = bill_type.replace('.', '').lower()
                                    bill_id = f"{bill_type}{bill_number}-{congress}"
                                    bill_ids.append(bill_id)

                        logger.info(f"Found {len(bill_ids)} bills on 'Texts Received Today' page: {bill_ids}")
                        return bill_ids
                    finally:
                        try:
                            context.close()
                        except Exception:
                            pass
                        try:
                            browser.close()
                        except Exception:
                            pass
            except Exception as e:
                logger.warning(f"Playwright scrape failed (attempt {attempt + 1}/{max_retries}) for '{url}': {e}")
                if attempt < max_retries - 1:
                    logger.info("Retrying in 2 seconds...")
                    time.sleep(2)
                    continue
                logger.warning("Playwright retries exhausted, falling back to requests method")
                # Fall through to requests fallback
    else:
        logger.warning("Playwright not available, using requests fallback")

    # 2) Fall back to requests with hardened headers and short retry
    logger.info("Using requests-based scraping as fallback...")
    max_retries = 2
    for attempt in range(max_retries):
        try:
            # Build headers with optional UA rotation and referer
            headers = dict(HEADERS)
            headers.setdefault('Referer', 'https://www.congress.gov/')
            if attempt > 0 and 'USER_AGENTS' in globals() and USER_AGENTS:
                headers['User-Agent'] = USER_AGENTS[attempt % len(USER_AGENTS)]

            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')

            bill_ids: List[str] = []
            table = soup.find('table', class_='item_table')
            if not table:
                logger.info("No bill texts table found on page (may be empty today).")
                return []

            tbody = table.find('tbody')
            if not tbody:
                logger.info("No table body found in bill texts page.")
                return []

            for row in tbody.find_all('tr'):
                strong_tag = row.find('strong')
                if strong_tag:
                    # Text is like: S.2392 [119th]
                    match = re.search(r'([a-zA-Z\.]+)(\d+)\s*\[(\d+)th\]', strong_tag.text)
                    if match:
                        bill_type, bill_number, congress = match.groups()
                        bill_type = bill_type.replace('.', '').lower()
                        bill_id = f"{bill_type}{bill_number}-{congress}"
                        bill_ids.append(bill_id)

            logger.info(f"Found {len(bill_ids)} bills on 'Texts Received Today' page: {bill_ids}")
            return bill_ids

        except requests.RequestException as e:
            logger.warning(f"403/Request failure scraping '{url}' (attempt {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                logger.info("Retrying in 2 seconds...")
                time.sleep(2)
                continue
            return []

def fetch_and_enrich_bills(limit: int = 5) -> List[Dict[str, Any]]:
    """
    Fetches recent bills from the API and enriches them with tracker data.
    It first tries to get bills from the 'Bill Texts Received Today' page,
    and falls back to the general API if that fails.
    """
    # Local import to avoid circular dependency with congress_fetcher
    from .congress_fetcher import fetch_bill_text_from_api, download_bill_text
    logger.info(f"🎯 Fetching and enriching bills (limit={limit})")
    api_key = os.getenv('CONGRESS_API_KEY')
    if not api_key:
        raise ValueError("CONGRESS_API_KEY environment variable not set")

    bills_from_api = []
    
    # First, try scraping the "texts received today" page
    scraped_bill_ids = fetch_bill_ids_from_texts_received_today()

    if scraped_bill_ids:
        logger.info("Fetching details for bills found on 'Texts Received Today' page.")
        for bill_id in scraped_bill_ids:
            # Deconstruct bill_id to call API
            match = re.match(r'([a-z]+)(\d+)-(\d+)', bill_id)
            if match:
                bill_type, bill_number, congress = match.groups()
                detail_url = f"https://api.congress.gov/v3/bill/{congress}/{bill_type}/{bill_number}?api_key={api_key}"
                try:
                    detail_resp = requests.get(detail_url, headers={"Accept": "application/json"}, timeout=30)
                    if detail_resp.status_code == 200:
                        bill_data = detail_resp.json().get('bill')
                        if bill_data:
                            bills_from_api.append(bill_data)
                            # Log metadata to verify API is returning it
                            logger.debug(f"✅ API data for {bill_id}: congress={bill_data.get('congress')}, introducedDate={bill_data.get('introducedDate')}")
                        else:
                            logger.warning(f"⚠️ No bill data in API response for {bill_id}")
                    else:
                        logger.warning(f"⚠️ API returned status {detail_resp.status_code} for {bill_id}")
                except requests.RequestException as e:
                    logger.warning(f"❌ API call failed for {bill_id}: {e}")
    
    # Fallback to original method if scraping found nothing
    if not bills_from_api:
        logger.warning("Scraper found no bills, or failed. Falling back to general API query.")
        # Use 119th Congress endpoint with introducedDate-desc sort to get recently
        # introduced bills, not old bills with recent metadata updates
        url = f"https://api.congress.gov/v3/bill/119?sort=introducedDate-desc&limit={limit}&api_key={api_key}"
        try:
            response = requests.get(url, headers={"Accept": "application/json"})
            response.raise_for_status()
            data = response.json()
            bills_from_api = data.get('bills', [])
        except requests.RequestException as e:
            logger.error(f"❌ API request failed: {e}")
            return []

    logger.info(f"📋 Processing {len(bills_from_api)} bills, checking for text and enriching with tracker data...")

    enriched_bills = []
    checked_bills = 0
    for bill_data in bills_from_api:
        checked_bills += 1
        bill_type = bill_data.get('type', '').lower()
        bill_number = bill_data.get('number')
        congress = bill_data.get('congress')

        if not all([bill_type, bill_number, congress]):
            continue

        text_versions_url = f"https://api.congress.gov/v3/bill/{congress}/{bill_type}/{bill_number}/text"
        
        source_url = construct_bill_url(congress, bill_type, bill_number)
        tracker_data = None
        if source_url:
            tracker_data = scrape_bill_tracker(source_url, force_scrape=True)

        # Fetch full text via API; fallback to scrape if needed
        full_text = ""
        text_source = "none"
        try:
            ft, fmt = fetch_bill_text_from_api(str(congress), str(bill_type), str(bill_number), api_key, timeout=30)
        except Exception:
            ft, fmt = ("", None)
        if ft and len(ft.strip()) > 100:
            full_text = ft
            text_source = f"api-{fmt or 'unknown'}"
            logger.info(f"✅ Successfully fetched {len(ft)} chars for {bill_type}{bill_number}-{congress} from {text_source}")
        elif source_url and not running_in_ci():
            ft2, status = download_bill_text(source_url, f"{bill_type}{bill_number}-{congress}")
            if ft2 and len(ft2.strip()) > 100:
                full_text = ft2
                text_source = "scraped"
                if status:
                    logger.info(f"✅ Updated bill status to '{status}' from scraping")
                logger.info(f"✅ Successfully fetched {len(ft2)} chars for {bill_type}{bill_number}-{congress} from {text_source}")
            else:
                logger.warning(f"⚠️ No valid text found for {bill_type}{bill_number}-{congress} via scrape fallback")

        # Extract metadata with logging for debugging
        introduced_date = bill_data.get('introducedDate')

        # Fallback 1: Try to get introducedDate from latestAction if it's an introduction
        if not introduced_date:
            latest_action = bill_data.get('latestAction', {})
            action_text = (latest_action.get('text') or '').lower()
            if 'introduced' in action_text:
                introduced_date = latest_action.get('actionDate')
                if introduced_date:
                    logger.info(
                        f"ℹ️ Derived introducedDate from latestAction for {bill_type}{bill_number}-{congress}: {introduced_date}"
                    )

        # Fallback 2: Scan full actions history for an Introduced event
        if not introduced_date:
            actions = bill_data.get('actions') or []
            introduced_action_date = None
            for action in actions:
                text = (action.get('text') or '').lower()
                if 'introduced' in text:
                    introduced_action_date = action.get('actionDate')
                    if introduced_action_date:
                        break

            if introduced_action_date:
                introduced_date = introduced_action_date
                logger.info(
                    f"ℹ️ Derived introducedDate from actions history for {bill_type}{bill_number}-{congress}: {introduced_date}"
                )

        # Fallback 3: If still missing, call the bill detail endpoint once
        if not introduced_date:
            try:
                detail_url = f"https://api.congress.gov/v3/bill/{congress}/{bill_type}/{bill_number}?api_key={api_key}"
                logger.info(
                    f"🔍 Fetching bill detail for introducedDate fallback: {bill_type}{bill_number}-{congress}"
                )
                detail_resp = requests.get(detail_url, headers={"Accept": "application/json"}, timeout=30)
                if detail_resp.status_code == 200:
                    detail_bill = detail_resp.json().get("bill") or {}
                    introduced_date = detail_bill.get("introducedDate")

                    # Reuse latestAction/actions fallbacks on the richer payload if needed
                    if not introduced_date:
                        latest_action = detail_bill.get("latestAction", {})
                        action_text = (latest_action.get("text") or "").lower()
                        if "introduced" in action_text:
                            introduced_date = latest_action.get("actionDate")

                    if not introduced_date:
                        actions = detail_bill.get("actions") or []
                        introduced_action_date = None
                        for action in actions:
                            text = (action.get("text") or "").lower()
                            if "introduced" in text:
                                introduced_action_date = action.get("actionDate")
                                if introduced_action_date:
                                    break
                        if introduced_action_date:
                            introduced_date = introduced_action_date

                    if introduced_date:
                        logger.info(
                            f"ℹ️ Derived introducedDate from detail endpoint for {bill_type}{bill_number}-{congress}: {introduced_date}"
                        )
                else:
                    logger.warning(
                        f"⚠️ Detail endpoint returned status {detail_resp.status_code} for {bill_type}{bill_number}-{congress}"
                    )
            except requests.RequestException as e:
                logger.warning(
                    f"⚠️ Failed to fetch bill detail for introducedDate fallback on {bill_type}{bill_number}-{congress}: {e}"
                )

        if not introduced_date:
            logger.warning(f"⚠️ No introducedDate in API response for {bill_type}{bill_number}-{congress}")
            logger.debug(f"Available keys in bill_data: {list(bill_data.keys())}")
        
        enriched_bills.append({
            'bill_id': f"{bill_type}{bill_number}-{congress}",
            'title': bill_data.get('title'),
            'text_url': text_versions_url,
            'source_url': source_url,
            'date_introduced': introduced_date,
            'congress': congress,
            'latest_action': (bill_data.get('latestAction') or {}).get('text'),
            'latest_action_date': (bill_data.get('latestAction') or {}).get('actionDate'),
            'tracker': tracker_data,
            'full_text': full_text,
            'text_source': text_source
        })
        if len(enriched_bills) >= limit:
            break
    
    logger.info(f"📊 Enrichment Results:\n   - Bills checked: {checked_bills}\n   - Bills enriched: {len(enriched_bills)}\n   - Bills returned: {len(enriched_bills)}")
    return enriched_bills

# HTTP headers to avoid 403 errors
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
    'Accept-Encoding': 'gzip, deflate',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
    'Referer': 'https://www.congress.gov/',
}

# User agents for rotation
USER_AGENTS = [
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
]

def get_random_user_agent():
    """Get a random user agent from the list."""
    import random
    return random.choice(USER_AGENTS)

def fetch_recent_bills(limit: int = 5, include_text: bool = True) -> List[Dict[str, Any]]:
    """
    Wrapper function to fetch and enrich bills.
    """
    return fetch_and_enrich_bills(limit=limit)

# ---- Feed parsing and HTML introduced-date extraction (added) ----

def _extract_introduced_date_from_bill_page(url: str, timeout: int = 30) -> Optional[str]:
    """
    Fetch a Congress.gov bill page and extract the 'Introduced' date from the Overview section.
    Returns an ISO date string (YYYY-MM-DD) or None if not found.

    Implementation notes:
    - Tries a real browser via Playwright first to bypass Cloudflare (works in both local and CI).
    - Falls back to requests-based fetch using HEADERS if Playwright is unavailable or fails.
    """
    try:
        html: Optional[str] = None

        # 1) Try browser-based fetch to avoid anti-bot challenges
        if PLAYWRIGHT_AVAILABLE:
            try:
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=True)
                    context = browser.new_context(
                        user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                                   'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
                    )
                    page = context.new_page()
                    time.sleep(0.5)
                    response = page.goto(url, timeout=20000, wait_until='networkidle')
                    if response and response.status == 200:
                        html = page.content()
                    context.close()
                    browser.close()
            except Exception as e:
                logger.debug(f"Playwright introduced-date fetch failed for {url}: {e}")

        # 2) Fallback to simple HTTP GET
        if html is None:
            resp = requests.get(url, headers=HEADERS, timeout=timeout)
            resp.raise_for_status()
            html = resp.content

        soup = BeautifulSoup(html, "html.parser")

        # Strategy 1: Look for a label 'Introduced' in tables or definition lists
        candidates = []
        for tag_name in ("th", "dt", "span", "div"):
            for tag in soup.find_all(tag_name):
                text = tag.get_text(strip=True).lower()
                if text == "introduced":
                    # Try cell/sibling next to the label
                    val = None
                    if tag_name in ("th", "dt") and tag.find_next_sibling():
                        val = tag.find_next_sibling().get_text(" ", strip=True)
                    elif tag.parent and tag.parent.find("td"):
                        val = tag.parent.find("td").get_text(" ", strip=True)
                    elif tag.next_sibling:
                        val = getattr(tag.next_sibling, "get_text", lambda *a, **k: str(tag.next_sibling))(" ", strip=True)
                    if val:
                        candidates.append(val)

        # Strategy 2: Fallback to global text search "Introduced: MM/DD/YYYY"
        if not candidates:
            text = soup.get_text(" ", strip=True)
            m = re.search(r"\bIntroduced\b[:\s]+(\d{2}/\d{2}/\d{4})", text, re.IGNORECASE)
            if m:
                candidates.append(m.group(1))

        # Parse the first candidate that looks like a date
        for c in candidates:
            m = re.search(r"(\d{2}/\d{2}/\d{4})", c)
            if m:
                try:
                    dt = datetime.strptime(m.group(1), "%m/%d/%Y").date()
                    return dt.isoformat()
                except Exception:
                    continue

        logger.debug(f"Introduced date not found on page: {url}")
        return None
    except Exception as e:
        logger.debug(f"Failed to extract introduced date from {url}: {e}")
        return None


def _normalize_bill_type_slug(slug: str) -> Optional[str]:
    """
    Map Congress.gov URL slug to short bill type code used internally.
    """
    mapping = {
        "house-bill": "hr",
        "senate-bill": "s",
        "house-joint-resolution": "hjres",
        "senate-joint-resolution": "sjres",
        "house-resolution": "hres",
        "senate-resolution": "sres",
        "house-concurrent-resolution": "hconres",
        "senate-concurrent-resolution": "sconres",
    }
    return mapping.get((slug or "").lower().strip())


def _extract_bill_data(item) -> Optional[Dict[str, Any]]:
    """
    Extract basic bill metadata from a feed list item element.
    Expected structure resembles:
      <li class="expanded">
        <a href="/bill/119th-congress/house-bill/1234">H.R. 1234</a>
        <span>Title text...</span>
        <a href="/119/bills/hr1234/BILLS-119hr1234ih.pdf">PDF</a>
      </li>
    Returns:
      dict with keys: bill_id, title, source_url, text_url, text_version,
                      congress, bill_type, bill_number, text_received_date, text_source
      or None if parsing fails.
    """
    try:
        link = item.find("a", href=True)
        if not link:
            return None

        href = link["href"]
        # Parse /bill/{congress}th-congress/{slug}/{number}
        m = re.search(r"/bill/(\d+)th-congress/([a-z-]+)/(\d+)", href, re.IGNORECASE)
        if not m:
            return None

        congress, slug, number = m.groups()
        bill_type = _normalize_bill_type_slug(slug)
        if not bill_type:
            return None

        # Compose IDs/URLs
        source_url = f"https://www.congress.gov{href}" if href.startswith("/") else href
        bill_id = f"{bill_type}{number}-{congress}"

        # Title: prefer explicit text near the anchor if available
        title_text = link.get_text(" ", strip=True) or ""
        # If there is another span with title, append it
        extra_span = item.find("span")
        if extra_span:
            extra_title = extra_span.get_text(" ", strip=True)
            # Avoid duplicating if same text
            if extra_title and extra_title not in title_text:
                title_text = f"{title_text} - {extra_title}" if title_text else extra_title

        # Text PDF link if present; otherwise default to bill page URL so consumers have a valid HTTP URL
        pdf_link = item.find("a", href=re.compile(r"\.pdf$", re.IGNORECASE))
        text_url = source_url
        text_version = None
        if pdf_link and pdf_link.get("href"):
            tu = pdf_link["href"]
            text_url = f"https://www.congress.gov{tu}" if tu.startswith("/") else tu
            mv = re.search(r"BILLS-\d+[a-z]+\d+([a-z]+)\.pdf", text_url, re.IGNORECASE)
            if mv:
                text_version = mv.group(1)

        # Approximate text_received_date as 'today' in ISO date (acceptable for tests; feed doesn't carry date per item)
        text_received_date = datetime.utcnow().date().isoformat()

        return {
            "bill_id": bill_id,
            "title": title_text,
            "source_url": source_url,
            "text_url": text_url,
            "text_version": text_version,
            "congress": congress,
            "bill_type": bill_type,
            "bill_number": number,
            "text_received_date": text_received_date,
            "text_source": "feed",
        }
    except Exception as e:
        logger.debug(f"Failed to extract bill data from feed item: {e}")
        return None


def parse_bill_texts_feed(limit: int = 10) -> List[Dict[str, Any]]:
    """
    Parse the Congress.gov 'Bill Texts Received Today' page and return up to 'limit' bills.
    For each bill, also fetch the bill page to extract the true 'Introduced' date from HTML.
    Raises exceptions from requests on network failures/timeouts (tests rely on this behavior).
    """
    FEED_URL = "https://www.congress.gov/bill-texts-received-today"
    logger.info(f"Fetching bill texts feed: {FEED_URL}")
    response = requests.get(FEED_URL, headers=HEADERS, timeout=30)  # Allow exceptions to propagate
    response.raise_for_status()

    soup = BeautifulSoup(response.content, "html.parser")

    # Primary pattern used by tests and current site layout
    items = soup.select("li.expanded")
    bills: List[Dict[str, Any]] = []
    if not items:
        # Gracefully handle empty feed page variants
        logger.info("No bill items found in feed HTML")
        return bills

    for item in items[: max(0, int(limit))]:
        data = _extract_bill_data(item)
        if not data:
            continue

        # Extract introduced date from the bill's main page HTML
        introduced_iso = _extract_introduced_date_from_bill_page(data.get("source_url", ""))
        if introduced_iso:
            data["date_introduced"] = introduced_iso  # Use true introduced date from HTML
        else:
            # Do not silently substitute text_received_date without logging
            fallback = data.get("text_received_date")
            if fallback:
                logger.debug(
                    f"Introduced date not found for {data.get('bill_id')}, "
                    f"falling back to text_received_date={fallback}"
                )
                # We don't set date_introduced here; fetch_bills_from_feed will setdefault as a last resort

        bills.append(data)

    logger.info(f"Parsed {len(bills)} bills from feed")
    return bills


def scrape_multiple_bill_trackers(urls: List[str], force_scrape: bool = False) -> Dict[str, Optional[List[Dict[str, Any]]]]:
    """
    Convenience helper to scrape multiple bill trackers. Returns {url: steps or None}.
    Skips entirely in CI unless force_scrape=True.
    """
    results: Dict[str, Optional[List[Dict[str, Any]]]] = {}
    if running_in_ci() and not force_scrape:
        logger.debug("Skipping scrape_multiple_bill_trackers in CI mode")
        return {u: None for u in urls or []}

    for u in (urls or []):
        try:
            results[u] = scrape_bill_tracker(u, force_scrape=force_scrape)
        except Exception as e:
            logger.debug(f"Tracker scrape failed for {u}: {e}")
            results[u] = None
    return results
