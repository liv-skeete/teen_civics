"""
Threads publisher for posting bill updates via Meta Graph API.
Implements the BasePublisher interface for multi-platform support.
"""

import os
import re
import time
import requests
import logging
from typing import Dict, Tuple, Optional

from dotenv import load_dotenv

from src.publishers.base_publisher import BasePublisher

# Configure logging
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Threads credentials
THREADS_USER_ID = os.getenv('THREADS_USER_ID')
THREADS_ACCESS_TOKEN = os.getenv('THREADS_ACCESS_TOKEN')


class ThreadsPublisher(BasePublisher):
    """
    Publisher for Threads (Meta).
    
    Uses the Threads Graph API to publish posts.
    Requires a two-step process:
    1. Create a media container
    2. Publish the media container
    
    Character limit: 500 characters
    Link handling: Links are automatically parsed (no facets needed)
    """
    
    BASE_URL = "https://graph.threads.net/v1.0"
    
    def __init__(self):
        # Read credentials at instantiation time (not module import time)
        # This ensures env vars set by GitHub Actions are picked up
        self._user_id = os.getenv('THREADS_USER_ID')
        self._access_token = os.getenv('THREADS_ACCESS_TOKEN')
    
    @property
    def platform_name(self) -> str:
        return "threads"
    
    @property
    def max_length(self) -> int:
        return 500
    
    def is_configured(self) -> bool:
        """Check if Threads credentials are present."""
        # Re-read from environment in case they were set after __init__
        user_id = self._user_id or os.getenv('THREADS_USER_ID')
        access_token = self._access_token or os.getenv('THREADS_ACCESS_TOKEN')
        
        # Update instance variables if found
        if user_id:
            self._user_id = user_id
        if access_token:
            self._access_token = access_token
        
        # Detailed logging for debugging
        has_user_id = bool(self._user_id)
        has_token = bool(self._access_token)
        
        if not has_user_id and not has_token:
            logger.warning("Threads: Both THREADS_USER_ID and THREADS_ACCESS_TOKEN are missing")
            return False
        elif not has_user_id:
            logger.warning("Threads: THREADS_USER_ID is missing (token is present)")
            return False
        elif not has_token:
            logger.warning("Threads: THREADS_ACCESS_TOKEN is missing (user_id is present)")
            return False
        
        logger.info(f"Threads: Credentials configured (user_id={self._user_id[:8]}...)")
        return True
    
    def format_post(self, bill: Dict) -> str:
        """
        Format a bill for Threads posting.
        
        Mirrors the Twitter/Bluesky formatting logic with Threads' 500-char limit.
        Threads auto-parses links, so no special handling needed.
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
        # Threads has 500 chars, more room than Twitter/Bluesky
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
            if char in '.!?' and (i + 1 >= len(text) or text[i + 1] in ' \n'):
                sentence_end = i
        
        if sentence_end > target // 2:  # Only use if reasonable
            return text[:sentence_end + 1]
        
        # Fall back to word boundary
        space_pos = text.rfind(' ', 0, target)
        if space_pos > target // 2:
            return text[:space_pos] + "..."
        
        # Last resort: hard truncate
        return text[:target] + "..."
    
    def post(self, text: str) -> Tuple[bool, Optional[str]]:
        """
        Publish content to Threads.
        
        Threads API requires a two-step process:
        1. Create a media container (POST /threads)
        2. Publish the container (POST /threads_publish)
        
        Returns:
            Tuple of (success: bool, post_url: Optional[str])
        """
        if not self.is_configured():
            logger.error("Cannot post to Threads: Credentials missing.")
            return False, None

        try:
            # Step 1: Create Media Container
            container_id = self._create_media_container(text)
            if not container_id:
                return False, None
            
            # Step 2: Wait for container to be ready (Meta requires processing time)
            if not self._wait_for_container(container_id):
                logger.error("Threads: Container never became ready for publishing")
                return False, None
                
            # Step 3: Publish Container
            return self._publish_container(container_id)
            
        except Exception as e:
            logger.exception(f"Error posting to Threads: {e}")
            return False, None

    def _create_media_container(self, text: str) -> Optional[str]:
        """Creates a media container for text threads."""
        url = f"{self.BASE_URL}/{self._user_id}/threads"
        params = {
            "media_type": "TEXT",
            "text": text,
            "access_token": self._access_token
        }
        
        try:
            response = requests.post(url, params=params)
            response.raise_for_status()
            data = response.json()
            container_id = data.get("id")
            if container_id:
                logger.info(f"Threads: Created media container {container_id}")
            return container_id
        except requests.exceptions.RequestException as e:
            logger.error(f"Threads: Failed to create media container - {e}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Threads: Response content: {e.response.text}")
            return None

    def _wait_for_container(self, container_id: str, max_wait: int = 30, poll_interval: int = 3) -> bool:
        """
        Poll the container status until it's ready for publishing.
        
        The Threads API requires processing time between creating a media
        container and publishing it. This method polls the status endpoint
        to confirm the container is in FINISHED state before proceeding.
        
        Args:
            container_id: The media container ID to check
            max_wait: Maximum seconds to wait (default: 30)
            poll_interval: Seconds between status checks (default: 3)
            
        Returns:
            True if container is ready, False if timed out or errored
        """
        url = f"{self.BASE_URL}/{container_id}"
        params = {
            "fields": "status",
            "access_token": self._access_token
        }
        
        elapsed = 0
        while elapsed < max_wait:
            try:
                response = requests.get(url, params=params)
                response.raise_for_status()
                data = response.json()
                status = data.get("status", "UNKNOWN")
                
                logger.info(f"Threads: Container {container_id} status: {status} (waited {elapsed}s)")
                
                if status == "FINISHED":
                    return True
                elif status == "ERROR":
                    logger.error(f"Threads: Container {container_id} entered ERROR state")
                    return False
                elif status in ("IN_PROGRESS", "PUBLISHED"):
                    # IN_PROGRESS: still processing, keep waiting
                    # PUBLISHED: shouldn't happen here but treat as ready
                    if status == "PUBLISHED":
                        return True
                else:
                    logger.warning(f"Threads: Unknown container status '{status}', will retry")
                    
            except requests.exceptions.RequestException as e:
                logger.warning(f"Threads: Error checking container status: {e}")
            
            time.sleep(poll_interval)
            elapsed += poll_interval
        
        logger.error(f"Threads: Container {container_id} not ready after {max_wait}s")
        return False

    def _publish_container(self, container_id: str) -> Tuple[bool, Optional[str]]:
        """Publishes a created media container."""
        url = f"{self.BASE_URL}/{self._user_id}/threads_publish"
        params = {
            "creation_id": container_id,
            "access_token": self._access_token
        }
        
        try:
            response = requests.post(url, params=params)
            response.raise_for_status()
            data = response.json()
            
            # If successful, we get an ID back
            post_id = data.get("id")
            if post_id:
                # Construct the Threads post URL
                # Threads URLs are: https://threads.net/@username/post/POST_ID
                # Since we don't store username, use a generic format
                post_url = f"https://threads.net/t/{post_id}"
                logger.info(f"Threads: Successfully published - {post_url}")
                return True, post_url
            
            logger.error("Threads: Publish response missing post ID")
            return False, None
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Threads: Failed to publish container - {e}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Threads: Response content: {e.response.text}")
            return False, None


# Convenience function for direct posting (matches Bluesky pattern)
def post_to_threads(bill: Dict) -> Tuple[bool, Optional[str]]:
    """
    Convenience function to post a bill to Threads.
    
    Args:
        bill: Dictionary containing bill data
        
    Returns:
        Tuple of (success: bool, post_url: Optional[str])
    """
    publisher = ThreadsPublisher()
    return publisher.publish_bill(bill)


if __name__ == "__main__":
    # Test the Threads publisher
    import logging
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    publisher = ThreadsPublisher()
    
    print(f"\n📱 Platform: {publisher.platform_name}")
    print(f"📏 Max Length: {publisher.max_length}")
    print(f"✅ Configured: {publisher.is_configured()}")
    
    # Test formatting with sample bill
    test_bill = {
        "summary_tweet": "A bipartisan bill was introduced to expand computer science education in public schools, providing funding for teacher training and curriculum development.",
        "website_slug": "hr-1234-119",
        "title": "Computer Science Education Act",
        "normalized_status": "introduced"
    }
    
    formatted = publisher.format_post(test_bill)
    print(f"\n📝 Formatted Post ({len(formatted)} chars):")
    print("-" * 40)
    print(formatted)
    print("-" * 40)
