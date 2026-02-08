"""
Facebook publisher for posting bill updates via Meta Graph API.
Implements the BasePublisher interface for multi-platform support.
"""

import logging
import os
import re
from typing import Dict, Optional, Tuple

import requests
from dotenv import load_dotenv

from src.publishers.base_publisher import BasePublisher

# Configure logging
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Facebook credentials
FACEBOOK_PAGE_ID = os.getenv("FACEBOOK_PAGE_ID")
FACEBOOK_PAGE_TOKEN = os.getenv("FACEBOOK_PAGE_TOKEN")


class FacebookPublisher(BasePublisher):
    """
    Publisher for Facebook (Meta).

    Uses the Graph API to publish posts to a page feed.

    Character limit: 500 characters
    Link handling: Links are automatically parsed (no facets needed)
    """

    def __init__(self) -> None:
        # Read credentials at instantiation time (not module import time)
        # This ensures env vars set by GitHub Actions are picked up
        self._page_id = os.getenv("FACEBOOK_PAGE_ID")
        self._access_token = os.getenv("FACEBOOK_PAGE_TOKEN")

    @property
    def platform_name(self) -> str:
        return "facebook"

    @property
    def max_length(self) -> int:
        return 500

    def is_configured(self) -> bool:
        """Check if Facebook credentials are present."""
        # Re-read from environment in case they were set after __init__
        page_id = self._page_id or os.getenv("FACEBOOK_PAGE_ID")
        access_token = self._access_token or os.getenv("FACEBOOK_PAGE_TOKEN")

        # Update instance variables if found
        if page_id:
            self._page_id = page_id
        if access_token:
            self._access_token = access_token

        # Detailed logging for debugging
        has_page_id = bool(self._page_id)
        has_token = bool(self._access_token)

        if not has_page_id and not has_token:
            logger.warning("Facebook: Both FACEBOOK_PAGE_ID and FACEBOOK_PAGE_TOKEN are missing")
            return False
        if not has_page_id:
            logger.warning("Facebook: FACEBOOK_PAGE_ID is missing (token is present)")
            return False
        if not has_token:
            logger.warning("Facebook: FACEBOOK_PAGE_TOKEN is missing (page_id is present)")
            return False

        logger.info(f"Facebook: Credentials configured (page_id={self._page_id[:8]}...)")
        return True

    def format_post(self, bill: Dict) -> str:
        """
        Format a bill for Facebook posting.

        Mirrors the Twitter/Bluesky formatting logic with Facebook's 500-char limit.
        Facebook auto-parses links, so no special handling needed.
        """
        if not bill:
            bill = {}

        # Choose best available short summary; never emit placeholder text
        summary_text = (
            bill.get("summary_tweet")
            or bill.get("summary_overview")
            or bill.get("summary_short")
            or bill.get("title")
        )

        # Check if summary contains placeholder text
        if summary_text and "no summary available" in summary_text.lower():
            summary_text = None

        # Fallback: synthesize from available fields
        if not summary_text:
            status_raw = (bill.get("normalized_status") or bill.get("status") or "").strip()
            status_disp = status_raw.replace("_", " ").title() if status_raw else "Introduced"
            title = (bill.get("title") or bill.get("short_title") or bill.get("bill_id") or "").strip()
            base = title if title else (bill.get("bill_id") or "This bill")
            summary_text = f"{base}. Status: {status_disp}."

        # Normalize whitespace and strip
        summary_text = (summary_text or "").replace("\n", " ").replace("\r", " ").strip()

        # Defensive cleanup
        summary_text = re.sub(r"\s#[\w_]+", "", summary_text)
        summary_text = re.sub(r"^[^\w]+", "", summary_text).strip()
        summary_text = re.sub(r"\s{2,}", " ", summary_text)

        # Build header (same format as Twitter/Bluesky)
        header = "🏛️ Today in Congress\n\n"

        # Build footer with link
        website_slug = bill.get("website_slug")
        bill_id = bill.get("bill_id", "")

        # Build link
        if website_slug:
            link = f"https://teencivics.org/bill/{website_slug}"
        elif bill_id:
            link = f"https://teencivics.org/bill/{bill_id}"
        else:
            link = "https://teencivics.org"

        footer_text = "\n\n👉 See how this affects you: "

        # Calculate available space for summary
        base_length = len(header) + len(footer_text) + len(link)
        available_for_summary = self.max_length - base_length

        # Trim summary if needed (sentence-aware)
        if len(summary_text) > available_for_summary:
            summary_text = self._trim_to_sentence(summary_text, available_for_summary)

        return f"{header}{summary_text}{footer_text}{link}"

    def _trim_to_sentence(self, text: str, max_chars: int) -> str:
        """
        Trim text to fit within max_chars, preferring sentence boundaries.
        """
        if len(text) <= max_chars:
            return text

        # Reserve space for ellipsis
        target = max_chars - 3

        # Find last sentence boundary before target
        sentence_end = -1
        for i, char in enumerate(text[:target]):
            if char in ".!?" and (i + 1 >= len(text) or text[i + 1] in " \n"):
                sentence_end = i

        if sentence_end > target // 2:  # Only use if reasonable
            return text[: sentence_end + 1]

        # Fall back to word boundary
        space_pos = text.rfind(" ", 0, target)
        if space_pos > target // 2:
            return text[:space_pos] + "..."

        # Last resort: hard truncate
        return text[:target] + "..."

    def post(self, text: str) -> Tuple[bool, Optional[str]]:
        """
        Publish content to Facebook.

        Returns:
            Tuple of (success: bool, post_url: Optional[str])
        """
        if not self.is_configured():
            logger.error("Cannot post to Facebook: Credentials missing.")
            return False, None

        url = f"https://graph.facebook.com/{self._page_id}/feed"
        params = {
            "message": text,
            "access_token": self._access_token,
        }

        try:
            response = requests.post(url, params=params)
            response.raise_for_status()
            data = response.json()

            post_id = data.get("id")
            if post_id:
                post_url = f"https://facebook.com/{self._page_id}/posts/{post_id}"
                logger.info(f"Facebook: Successfully published - {post_url}")
                return True, post_url

            logger.error("Facebook: Publish response missing post ID")
            return False, None
        except requests.exceptions.RequestException as e:
            logger.error(f"Facebook: Failed to publish post - {e}")
            if hasattr(e, "response") and e.response is not None:
                logger.error(f"Facebook: Response content: {e.response.text}")
            return False, None


# Convenience function for direct posting (matches Bluesky pattern)
def post_to_facebook(bill: Dict) -> Tuple[bool, Optional[str]]:
    """
    Convenience function to post a bill to Facebook.

    Args:
        bill: Dictionary containing bill data

    Returns:
        Tuple of (success: bool, post_url: Optional[str])
    """
    publisher = FacebookPublisher()
    return publisher.publish_bill(bill)


if __name__ == "__main__":
    # Test the Facebook publisher
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

    publisher = FacebookPublisher()

    print(f"\n📱 Platform: {publisher.platform_name}")
    print(f"📏 Max Length: {publisher.max_length}")
    print(f"✅ Configured: {publisher.is_configured()}")

    # Test formatting with sample bill
    test_bill = {
        "summary_tweet": "A bipartisan bill was introduced to expand computer science education in public schools, providing funding for teacher training and curriculum development.",
        "website_slug": "hr-1234-119",
        "title": "Computer Science Education Act",
        "normalized_status": "introduced",
    }

    formatted = publisher.format_post(test_bill)
    print(f"\n📝 Formatted Post ({len(formatted)} chars):")
    print("-" * 40)
    print(formatted)
    print("-" * 40)
