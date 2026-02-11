#!/usr/bin/env python3
"""CLI script to sync rep contact form URLs."""

import os
import sys
import logging

from dotenv import load_dotenv

# Load environment variables first
load_dotenv()

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.fetchers.contact_form_sync import sync_contact_forms

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    skip_crawl = "--skip-crawl" in sys.argv
    skip_validate = "--skip-validate" in sys.argv

    logger.info("=" * 60)
    logger.info("Rep Contact Form Sync")
    logger.info("=" * 60)

    result = sync_contact_forms(
        crawl_missing=not skip_crawl,
        validate_existing=not skip_validate,
    )

    logger.info(
        "✅ Synced %s reps (%s with contact forms). Crawled=%s Validated=%s",
        result.get("total", 0),
        result.get("with_contact_form", 0),
        result.get("crawled", 0),
        result.get("validated", 0),
    )

    changes = result.get("changes_detected", 0)
    if changes > 0:
        logger.info("⚠️ %d contact form URL(s) changed during sync", changes)
    else:
        logger.info("✅ No contact form URL changes detected")


if __name__ == "__main__":
    main()
