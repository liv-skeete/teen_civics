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
            context = browser.new_context(user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36')
            page = context.new_page()
            time.sleep(1) # Small delay
            response = page.goto(source_url, timeout=15000, wait_until='networkidle')
            
            if not response or response.status != 200:
                logger.warning(f"⚠️ Failed to load page: {source_url} (status: {response.status if response else 'unknown'})")
                return None
            
            content = page.content()
            soup = BeautifulSoup(content, 'html.parser')
            tracker = soup.find('ol', class_='bill_progress')
            
            if not tracker:
                logger.warning(f"⚠️ Could not find bill_progress tracker on page: {source_url}")
                return None
            
            steps = []
            for li in tracker.find_all('li'):
                name = li.find(text=True, recursive=False)
                name = name.strip() if name else li.get_text(strip=True)
                selected = 'selected' in li.get('class', [])
                steps.append({"name": name, "selected": selected})
            
            logger.info(f"✅ Scraped {len(steps)} tracker steps from {source_url}")
            return steps
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

                        enriched_bills.append({
                            'bill_id': f"{bill_type}{bill_number}-{congress}",
                            'title': bill_data.get('title'),
                            'text_url': text_versions_url,
                            'source_url': source_url,
                            'date_introduced': bill_data.get('introducedDate'),
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