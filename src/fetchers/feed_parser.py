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
                    name = li.get_text(strip=True)
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

def fetch_recent_bills(limit: int = 5, include_text: bool = True) -> List[Dict[str, Any]]:
    """
    Wrapper function to fetch and enrich bills.
    """
    return fetch_and_enrich_bills(limit=limit)