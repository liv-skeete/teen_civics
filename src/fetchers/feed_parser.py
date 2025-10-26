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

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def running_in_ci() -> bool:
    """Check if the code is running in a CI environment."""
    return bool(os.getenv('CI')) or bool(os.getenv('GITHUB_ACTIONS'))

def scrape_bill_tracker(source_url: str, force_scrape=False) -> Optional[List[Dict[str, any]]]:
    """
    Scrapes the bill progress tracker from a Congress.gov bill page.
    Tries multiple selector variants and an accessibility fallback.
    """
    if running_in_ci() and not force_scrape:
        logger.debug("Skipping HTML tracker scraping in CI mode")
        return None
    if not PLAYWRIGHT_AVAILABLE:
        logger.warning("Playwright not available, cannot scrape tracker")
        return None

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                           'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
            )
            page = context.new_page()
            time.sleep(1)  # Small delay
            response = page.goto(source_url, timeout=20000, wait_until='networkidle')

            if not response or response.status != 200:
                logger.warning(f"⚠️ Failed to load page: {source_url} (status: {response.status if response else 'unknown'})")
                return None

            # Best-effort wait for either tracker list or the hidden status paragraph
            try:
                page.wait_for_selector("ol.bill_progress, ol.bill-progress, p.hide_fromsighted", timeout=5000)
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
            return None
    except Exception as e:
        logger.warning(f"⚠️ Failed to scrape tracker from {source_url}: {e}")
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

def fetch_and_enrich_bills(limit: int = 5) -> List[Dict[str, Any]]:
    """
    Fetches recent bills from the API and enriches them with tracker data.
    """
    logger.info(f"🎯 Fetching and enriching bills from API (limit={limit})")
    api_key = os.getenv('CONGRESS_API_KEY')
    if not api_key:
        raise ValueError("CONGRESS_API_KEY environment variable not set")

    seven_days_ago = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%dT%H:%M:%SZ')
    url = f"https://api.congress.gov/v3/bill?fromDateTime={seven_days_ago}&sort=updateDate-desc&limit={limit * 3}"
    
    try:
        response = requests.get(url, headers={"X-Api-Key": api_key, "Accept": "application/json"})
        response.raise_for_status()
        data = response.json()
        bills_from_api = data.get('bills', [])
        logger.info(f"📋 API returned {len(bills_from_api)} bills, checking for text and enriching with tracker data...")

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
            if text_versions_url:
                try:
                    text_response = requests.get(text_versions_url, headers={"X-Api-Key": api_key, "Accept": "application/json"})
                    if text_response.status_code == 200 and text_response.json().get('textVersions'):
                        logger.info(f"✅ {bill_type}{bill_number}-{congress} has text available")
                        
                        source_url = construct_bill_url(congress, bill_type, bill_number)
                        tracker_data = None
                        if source_url:
                            tracker_data = scrape_bill_tracker(source_url, force_scrape=True)

                        # Ensure we have introduced date and robust latest action by calling the bill detail endpoint when needed
                        detail_title = bill_data.get('title')
                        detail_intro = bill_data.get('introducedDate')
                        la_node = (bill_data.get('latestAction') or {})
                        la_text = la_node.get('text')
                        la_date = la_node.get('actionDate')

                        if not (detail_intro and detail_title and la_text and la_date):
                            detail_url = f"https://api.congress.gov/v3/bill/{congress}/{bill_type}/{bill_number}"
                            try:
                                detail_resp = requests.get(detail_url, headers={"X-Api-Key": api_key, "Accept": "application/json"})
                                if detail_resp.status_code == 200:
                                    detail_json = detail_resp.json()
                                    node = detail_json.get('bill') or detail_json
                                    detail_intro = detail_intro or node.get('introducedDate')
                                    detail_title = detail_title or node.get('title')
                                    la_node2 = node.get('latestAction') or {}
                                    la_text = la_text or la_node2.get('text') or la_node2.get('displayText')
                                    la_date = la_date or la_node2.get('actionDate')
                            except requests.RequestException as e:
                                logger.debug(f"Detail fetch failed for {bill_type}{bill_number}-{congress}: {e}")

                        enriched_bills.append({
                            'bill_id': f"{bill_type}{bill_number}-{congress}",
                            'title': detail_title,
                            'text_url': text_versions_url,
                            'source_url': source_url,
                            'date_introduced': detail_intro,
                            'congress': congress,
                            'latest_action': la_text,
                            'latest_action_date': la_date,
                            'tracker': tracker_data
                        })
                        if len(enriched_bills) >= limit:
                            break
                except requests.RequestException:
                    continue
        
        logger.info(f"📊 Enrichment Results:\n   - Bills checked: {checked_bills}\n   - Bills enriched: {len(enriched_bills)}\n   - Bills returned: {len(enriched_bills)}")
        return enriched_bills

    except requests.RequestException as e:
        logger.error(f"❌ API request failed: {e}")
        return []

# HTTP headers to avoid 403 errors
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
    'Accept-Encoding': 'gzip, deflate',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
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
    - Tries a real browser via Playwright first to bypass Cloudflare, when available and not in CI.
    - Falls back to requests-based fetch using HEADERS if Playwright is unavailable or fails.
    """
    try:
        html: Optional[str] = None

        # 1) Try browser-based fetch to avoid anti-bot challenges
        if PLAYWRIGHT_AVAILABLE and not running_in_ci():
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
            data["introduced_date"] = introduced_iso  # Use true introduced date from HTML
        else:
            # Do not silently substitute text_received_date without logging
            fallback = data.get("text_received_date")
            if fallback:
                logger.debug(
                    f"Introduced date not found for {data.get('bill_id')}, "
                    f"falling back to text_received_date={fallback}"
                )
                # We don't set introduced_date here; fetch_bills_from_feed will setdefault as a last resort

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
