#!/usr/bin/env python3
"""
Script to fix tracker timeout issues for specific bills by increasing timeout and adding retry logic.
"""

import sys
import os
import json
import time
import logging

# Add project root to path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

from src.fetchers.feed_parser import scrape_bill_tracker, construct_bill_url
from src.database.connection import postgres_connect
from src.database.db import get_bill_by_id

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def increase_timeout_scrape_bill_tracker(source_url: str, max_retries: int = 3, base_timeout: int = 30000) -> list:
    """
    Scrape bill tracker with increased timeout and retry logic.
    
    Args:
        source_url: URL to scrape
        max_retries: Maximum number of retry attempts
        base_timeout: Base timeout in milliseconds (default 30000ms = 30s)
    
    Returns:
        Tracker data or None if failed
    """
    import requests
    from bs4 import BeautifulSoup
    
    try:
        from playwright.sync_api import sync_playwright
        PLAYWRIGHT_AVAILABLE = True
    except ImportError:
        PLAYWRIGHT_AVAILABLE = False
        logger.warning("Playwright not available, using requests fallback")
    
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
                context = browser.new_context(
                    user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                               'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
                )
                page = context.new_page()
                time.sleep(1)  # Small delay
                
                # Navigate with increased timeout
                response = page.goto(source_url, timeout=timeout, wait_until='networkidle')
                
                if not response or response.status != 200:
                    logger.warning(f"Failed to load page: {source_url} (status: {response.status if response else 'unknown'})")
                    if attempt < max_retries - 1:
                        logger.info(f"Retrying in 2 seconds...")
                        time.sleep(2)
                        continue
                    return None
                
                # Wait for either tracker list or the hidden status paragraph
                try:
                    page.wait_for_selector("ol.bill_progress, ol.bill-progress, p.hide_fromsighted", timeout=min(timeout, 10000))
                except Exception as e:
                    logger.warning(f"Timeout waiting for selectors: {e}")
                
                content = page.content()
                soup = BeautifulSoup(content, 'html.parser')
                
                # Primary: ordered list tracker (support old/new class names)
                tracker = soup.find('ol', class_=['bill_progress', 'bill-progress'])
                steps = []
                
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
                
                # Fallback: A11y paragraph explicitly states status
                status_text = None
                try:
                    for p_tag in soup.find_all('p', class_='hide_fromsighted'):
                        text = p_tag.get_text(" ", strip=True)
                        import re
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
                if attempt < max_retries - 1:
                    logger.info(f"Retrying in 2 seconds...")
                    time.sleep(2)
                    continue
                return None
                
        except Exception as e:
            logger.warning(f"Attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                logger.info(f"Retrying in 2 seconds...")
                time.sleep(2)
                continue
            return None
        finally:
            try:
                if 'browser' in locals():
                    browser.close()
            except Exception as e:
                logger.warning(f"Error closing browser: {e}")

def fix_bill_tracker_timeout(bill_id):
    """Fix tracker timeout information for a single bill."""
    try:
        # Get bill from database
        logger.info(f"Retrieving bill {bill_id} from database...")
        bill = get_bill_by_id(bill_id)
        if not bill:
            logger.error(f"Bill {bill_id} not found in database")
            return False
            
        source_url = bill.get('source_url')
        if not source_url:
            logger.error(f"No source_url for bill {bill_id}")
            return False
            
        # Scrape tracker with increased timeout and retry logic
        logger.info(f"Scraping tracker for {bill_id} with increased timeout...")
        tracker_data = increase_timeout_scrape_bill_tracker(source_url)
        
        if not tracker_data:
            logger.error(f"Failed to scrape tracker for {bill_id} even with increased timeout")
            return False
            
        # Update database with new tracker data
        logger.info(f"Updating tracker data for {bill_id}...")
        with postgres_connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                UPDATE bills
                SET tracker_raw = %s
                WHERE bill_id = %s
                """, (json.dumps(tracker_data) if tracker_data else None, bill_id))
            conn.commit()
        
        logger.info(f"✅ Successfully updated tracker for {bill_id}")
        return True
        
    except Exception as e:
        logger.error(f"Error updating {bill_id}: {e}")
        return False

def main(bill_id=None):
    """Main function to fix tracker timeouts."""
    logger.info("Starting to fix bill tracker timeouts...")
    
    if bill_id:
        # Process specific bill
        logger.info(f"Processing specific bill: {bill_id}")
        if fix_bill_tracker_timeout(bill_id):
            logger.info(f"✅ Successfully processed {bill_id}")
            return True
        else:
            logger.error(f"❌ Failed to process {bill_id}")
            return False
    else:
        # List of bills known to have timeout issues
        problematic_bills = [
            's284-119',  # Explicitly mentioned in the task
            # Add other bills that might have timeout issues
        ]
        
        success_count = 0
        error_count = 0
        
        for bill_id in problematic_bills:
            logger.info(f"Processing {bill_id}...")
            if fix_bill_tracker_timeout(bill_id):
                success_count += 1
            else:
                error_count += 1
        
        logger.info(f"Finished! Success: {success_count}, Errors: {error_count}")
        return success_count > 0

if __name__ == "__main__":
    if len(sys.argv) > 1:
        bill_id = sys.argv[1]
        main(bill_id)
    else:
        main()