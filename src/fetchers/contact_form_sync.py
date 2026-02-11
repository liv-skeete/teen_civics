"""
Sync representative contact form URLs from the unitedstates/congress-legislators dataset.
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from src.database.connection import postgres_connect

logger = logging.getLogger(__name__)

LEGISLATORS_URL = "https://raw.githubusercontent.com/unitedstates/congress-legislators/gh-pages/legislators-current.json"
SYNC_TIMEOUT = 30
CRAWL_TIMEOUT = 5
VALIDATE_TIMEOUT = 5

CONTACT_TEXT_KEYWORDS = [
    "contact",
    "email",
    "write",
    "share your opinion",
    "get in touch",
]


def fetch_legislators_json() -> List[Dict]:
    """
    Fetch the current legislators JSON from the unitedstates project.
    Returns list of legislator dicts or empty list on failure.
    """
    try:
        response = requests.get(LEGISLATORS_URL, timeout=SYNC_TIMEOUT)
        response.raise_for_status()
        data = response.json()
        if isinstance(data, list):
            return data
        logger.error("Unexpected legislators JSON format; expected list")
        return []
    except requests.RequestException as e:
        logger.error(f"Failed to fetch legislators JSON: {e}")
        return []
    except ValueError as e:
        logger.error(f"Failed to parse legislators JSON: {e}")
        return []


def parse_contact_forms(legislators_json: List[Dict]) -> List[Dict]:
    """
    Extract contact form data from raw legislators JSON.

    Returns list of dicts ready for database upsert.
    """
    records: List[Dict] = []

    for legislator in legislators_json:
        try:
            terms = legislator.get("terms") or []
            if not terms:
                logger.warning("Skipping legislator missing terms")
                continue

            last_term = terms[-1]
            if last_term.get("type") != "rep":
                continue

            bioguide_id = (legislator.get("id") or {}).get("bioguide")
            if not bioguide_id:
                logger.warning("Skipping legislator missing bioguide id")
                continue

            name_data = legislator.get("name") or {}
            name = name_data.get("official_full")
            if not name:
                first = name_data.get("first", "")
                last = name_data.get("last", "")
                name = f"{first} {last}".strip() or None

            contact_form_url = last_term.get("contact_form")
            record = {
                "bioguide_id": bioguide_id,
                "name": name,
                "state": last_term.get("state"),
                "district": last_term.get("district"),
                "official_website": last_term.get("url"),
                "contact_form_url": contact_form_url,
                "contact_url_source": "dataset" if contact_form_url else None,
                "contact_url_verified_at": None,
            }
            records.append(record)
        except Exception as e:
            logger.warning(f"Failed to parse legislator entry: {e}")
            continue

    return records


def crawl_contact_url(official_website: Optional[str]) -> Optional[str]:
    """
    Crawl a representative's official website and attempt to find a contact page URL.
    """
    if not official_website:
        return None

    try:
        response = requests.get(official_website, timeout=CRAWL_TIMEOUT)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        anchors = soup.find_all("a", href=True)
        for anchor in anchors:
            text = (anchor.get_text() or "").strip().lower()
            if not text:
                continue
            if any(keyword in text for keyword in CONTACT_TEXT_KEYWORDS):
                href = anchor.get("href")
                if not href:
                    continue
                return urljoin(official_website, href)
        return None
    except Exception as e:
        logger.info(f"Crawl failed for {official_website}: {e}")
        return None


def _is_homepage_root(url: str) -> bool:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return False
    if parsed.path in ("", "/") and not parsed.query and not parsed.fragment:
        return True
    return False


def validate_contact_url(url: Optional[str]) -> bool:
    """
    Validate a contact form URL via HEAD request.
    Returns True if status is 200-399 and does not resolve to homepage root.
    """
    if not url:
        return False

    try:
        response = requests.head(url, timeout=VALIDATE_TIMEOUT, allow_redirects=True)
        status = response.status_code
        final_url = response.url or url

        if status == 404:
            return False
        if status < 200 or status >= 400:
            return False
        if _is_homepage_root(final_url):
            return False
        return True
    except Exception:
        return False


def sync_contact_forms(crawl_missing: bool = True, validate_existing: bool = True) -> Dict:
    """
    Fetch → Parse → Upsert contact form URLs into the database.

    Returns summary dict:
    {"total": N, "with_contact_form": N, "crawled": N, "validated": N, "changes_detected": N}
    """
    logger.info("Starting rep contact form sync")
    legislators = fetch_legislators_json()
    if not legislators:
        logger.warning("No legislators data available; aborting sync")
        return {"total": 0, "with_contact_form": 0, "crawled": 0, "validated": 0, "changes_detected": 0}

    records = parse_contact_forms(legislators)
    total = len(records)
    crawled = 0
    validated = 0

    for record in records:
        if not record.get("contact_form_url") and crawl_missing:
            crawled_url = crawl_contact_url(record.get("official_website"))
            if crawled_url:
                record["contact_form_url"] = crawled_url
                record["contact_url_source"] = "crawl"
                crawled += 1

        if record.get("contact_form_url") and validate_existing:
            if validate_contact_url(record.get("contact_form_url")):
                record["contact_url_verified_at"] = datetime.utcnow()
                validated += 1
            else:
                record["contact_form_url"] = None
                record["contact_url_source"] = None
                record["contact_url_verified_at"] = None

    with_contact_form = sum(1 for record in records if record.get("contact_form_url"))

    # Query to check existing contact_form_url before upserting
    check_sql = """
        SELECT contact_form_url FROM rep_contact_forms WHERE bioguide_id = %s
    """

    upsert_sql = """
        INSERT INTO rep_contact_forms (
            bioguide_id,
            name,
            state,
            district,
            official_website,
            contact_form_url,
            contact_url_source,
            contact_url_verified_at,
            last_synced_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
        ON CONFLICT (bioguide_id) DO UPDATE SET
            name = EXCLUDED.name,
            state = EXCLUDED.state,
            district = EXCLUDED.district,
            official_website = EXCLUDED.official_website,
            contact_form_url = EXCLUDED.contact_form_url,
            contact_url_source = EXCLUDED.contact_url_source,
            contact_url_verified_at = EXCLUDED.contact_url_verified_at,
            last_synced_at = NOW();
    """

    changes_detected = 0

    try:
        with postgres_connect() as conn:
            with conn.cursor() as cursor:
                for record in records:
                    # Check existing URL to detect changes
                    new_url = record.get("contact_form_url")
                    cursor.execute(check_sql, (record.get("bioguide_id"),))
                    row = cursor.fetchone()
                    old_url = row[0] if row else None

                    if old_url != new_url:
                        # A real change: URL differs or new URL found where none existed
                        if old_url is not None or new_url is not None:
                            changes_detected += 1
                            logger.info(
                                "Contact form URL changed for %s: %s → %s",
                                record.get("name") or record.get("bioguide_id"),
                                old_url or "(none)",
                                new_url or "(none)",
                            )

                    # Always upsert to update last_synced_at
                    cursor.execute(
                        upsert_sql,
                        (
                            record.get("bioguide_id"),
                            record.get("name"),
                            record.get("state"),
                            record.get("district"),
                            record.get("official_website"),
                            new_url,
                            record.get("contact_url_source"),
                            record.get("contact_url_verified_at"),
                        ),
                    )
            conn.commit()

        if changes_detected == 0:
            logger.info("Daily sync complete: no contact form changes detected")
        else:
            logger.info("Rep contact form sync completed with %d change(s) detected", changes_detected)
    except Exception as e:
        logger.error(f"Rep contact form sync failed: {e}")
        raise

    return {
        "total": total,
        "with_contact_form": with_contact_form,
        "crawled": crawled,
        "validated": validated,
        "changes_detected": changes_detected,
    }


def get_contact_form_url(bioguide_id: str) -> Optional[str]:
    """
    Look up the contact form URL for a given bioguide ID.
    Returns the URL string or None if not found.
    """
    if not bioguide_id:
        return None

    try:
        with postgres_connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT contact_form_url FROM rep_contact_forms WHERE bioguide_id = %s",
                    (bioguide_id,),
                )
                row = cursor.fetchone()
                if row and row[0]:
                    return row[0]
        return None
    except Exception as e:
        logger.error(f"Contact form lookup failed for {bioguide_id}: {e}")
        return None
