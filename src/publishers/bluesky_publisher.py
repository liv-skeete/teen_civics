"""
Bluesky publisher for posting bill updates via AT Protocol.
Uses the atproto library for authentication and posting.
"""

import os
import re
import logging
from typing import Dict, Tuple, Optional
from datetime import datetime, timezone

from dotenv import load_dotenv

from src.publishers.base_publisher import BasePublisher

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Bluesky credentials
BLUESKY_HANDLE = os.getenv('BLUESKY_HANDLE')
BLUESKY_APP_PASSWORD = os.getenv('BLUESKY_APP_PASSWORD')


class BlueskyPublisher(BasePublisher):
    """
    Publisher for Bluesky (AT Protocol / bsky.app).
    
    Bluesky uses graphemes for character counting, which can differ from
    Python's len() for certain unicode characters. For most ASCII/common
    emoji content, they're equivalent.
    
    Character limit: 300 graphemes
    Link handling: Requires "facets" to make URLs clickable
    """
    
    def __init__(self):
        self._client = None
        self._handle = BLUESKY_HANDLE
        self._app_password = BLUESKY_APP_PASSWORD
    
    @property
    def platform_name(self) -> str:
        return "bluesky"
    
    @property
    def max_length(self) -> int:
        # Bluesky uses 300 graphemes, which for ASCII/common content equals characters
        return 300
    
    def is_configured(self) -> bool:
        """Check if Bluesky credentials are present."""
        if not self._handle or not self._app_password:
            logger.warning("Bluesky: Missing BLUESKY_HANDLE or BLUESKY_APP_PASSWORD")
            return False
        return True
    
    def _get_client(self):
        """
        Get or create an authenticated Bluesky client.
        Lazy initialization to avoid import errors when atproto isn't installed.
        """
        if self._client is not None:
            return self._client
        
        try:
            from atproto import Client
            
            self._client = Client()
            self._client.login(self._handle, self._app_password)
            logger.info(f"Bluesky: Authenticated as {self._handle}")
            return self._client
            
        except ImportError:
            logger.error("Bluesky: atproto package not installed. Run: pip install atproto")
            raise
        except Exception as e:
            logger.error(f"Bluesky: Failed to authenticate - {e}")
            raise
    
    def _extract_link_positions(self, text: str) -> list:
        """
        Find all URLs in text and return their positions for facets.
        
        Returns list of dicts with:
            - start: byte start position
            - end: byte end position  
            - url: the URL string
        """
        url_pattern = r'https?://[^\s)>\]]*'
        links = []
        
        for match in re.finditer(url_pattern, text):
            url = match.group()
            # Bluesky uses byte positions, not character positions
            text_before = text[:match.start()]
            byte_start = len(text_before.encode('utf-8'))
            byte_end = byte_start + len(url.encode('utf-8'))
            
            links.append({
                'start': byte_start,
                'end': byte_end,
                'url': url
            })
        
        return links
    
    def _build_facets(self, text: str) -> list:
        """
        Build facets array for Bluesky post.
        Facets are required to make links clickable in Bluesky.
        """
        links = self._extract_link_positions(text)
        
        if not links:
            return []
        
        facets = []
        for link in links:
            facets.append({
                'index': {
                    'byteStart': link['start'],
                    'byteEnd': link['end']
                },
                'features': [{
                    '$type': 'app.bsky.richtext.facet#link',
                    'uri': link['url']
                }]
            })
        
        return facets
    
    def format_post(self, bill: Dict) -> str:
        """
        Format a bill for Bluesky posting.
        
        Mirrors the Twitter formatting logic exactly, with adjustments for:
        - Bluesky's 300-char limit (vs Twitter's 280 effective with t.co)
        - Bluesky doesn't shorten URLs, so we use bill_id format when needed
        
        Uses same sentence-aware trimming as Twitter to avoid awkward cutoffs.
        """
        if not bill:
            bill = {}

        # Choose best available short summary; never emit placeholder text
        # (Same logic as Twitter)
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

        # Normalize whitespace and strip (same as Twitter)
        summary_text = (summary_text or "").replace("\n", " ").replace("\r", " ").strip()
        
        # Defensive cleanup (same as Twitter)
        summary_text = re.sub(r"\s#[\w_]+", "", summary_text)
        summary_text = re.sub(r"^[^\w]+", "", summary_text).strip()
        summary_text = re.sub(r"\s{2,}", " ", summary_text)

        # Build header (same format as Twitter)
        header = "🏛️ Today in Congress\n"
        
        # Build footer with link
        website_slug = bill.get("website_slug")
        bill_id = bill.get("bill_id", "")
        
        # Try full slug URL first (matches Twitter exactly)
        if website_slug:
            full_link = f"https://teencivics.org/bill/{website_slug}"
            footer_text = "\n👉 See how this affects you: "
            test_post = f"{header}{summary_text}{footer_text}{full_link}"
            
            if len(test_post) <= self.max_length:
                logger.info(f"Bluesky: Matches Twitter format ({len(test_post)} chars)")
                return test_post
        
        # Fall back to shorter URL format
        if bill_id:
            link = f"https://teencivics.org/bill/{bill_id}"
        elif website_slug:
            link = f"https://teencivics.org/bill/{website_slug}"
        else:
            link = "https://teencivics.org"
        
        footer_text = "\n👉 "
        footer = f"{footer_text}{link}"
        
        # Calculate available space for summary
        header_length = len(header)
        footer_length = len(footer)
        available_space = self.max_length - header_length - footer_length
        
        # If specific link leaves too little space, fallback to generic archive link
        if available_space < 50:
            logger.warning(f"Bluesky: Link too long, switching to archive link to save space.")
            link = "https://teencivics.org/archive"
            footer = f"{footer_text}{link}"
            footer_length = len(footer)
            available_space = self.max_length - header_length - footer_length
            
        # Ensure we have a sane minimum even after fallback
        if available_space < 20:
             available_space = 20
        
        # Trim summary if needed (same logic as Twitter)
        if len(summary_text) > available_space:
            logger.info(f"Bluesky: Trimming summary from {len(summary_text)} to {available_space} chars")
            
            # Sentence-aware trimming
            cut = summary_text[:available_space].rstrip()
            
            # Prefer cutting at sentence boundary if reasonably far into text
            found_boundary = False
            for punct in [".", "!", "?"]:
                idx = cut.rfind(punct)
                if idx != -1 and idx >= 40:
                    summary_text = cut[:idx + 1]
                    found_boundary = True
                    break
            
            if not found_boundary:
                # Cut at last space and add ellipsis
                sp = cut.rfind(" ")
                if sp >= 40:
                    cut = cut[:sp].rstrip()
                if not cut.endswith((".", "!", "?")):
                    cut += "..."
                summary_text = cut[:available_space]
        
        # Construct the post
        formatted_post = f"{header}{summary_text}{footer}"
        
        # Final safety check (same as Twitter's emergency trim)
        final_length = len(formatted_post)
        
        if final_length > self.max_length:
            logger.warning(f"Bluesky: Post still too long ({final_length} chars). Emergency trim required.")
            overflow = final_length - self.max_length + 5  # Add safety margin
            
            # Recalculate based on fixed components (header/footer) to ensure link preservation
            # We truncate from summary_text, NOT the end of the string
            max_summary_len = self.max_length - len(header) - len(footer) - 3 # -3 for ellipsis
            
            if max_summary_len < 10:
                # Extreme case: even short summary won't fit with full link.
                # Switch to archive link which is shorter/safer.
                link = "https://teencivics.org/archive"
                footer = f"\n👉 {link}"
                max_summary_len = self.max_length - len(header) - len(footer) - 3
                
            # Perform safe truncation on summary text
            summary_text = summary_text[:max_summary_len].rstrip()
            
            # Ensure clean word break
            if " " in summary_text:
                summary_text = summary_text.rsplit(' ', 1)[0].rstrip()
            
            if not summary_text.endswith((".", "!", "?")):
                summary_text += "..."
            
            formatted_post = f"{header}{summary_text}{footer}"
            logger.info(f"Bluesky: After emergency trim: {len(formatted_post)} chars")
        
        logger.info(f"Bluesky: Final post length: {len(formatted_post)} chars")
        return formatted_post
    
    def post(self, text: str) -> Tuple[bool, Optional[str]]:
        """
        Post content to Bluesky.
        
        Args:
            text: The formatted post content
            
        Returns:
            Tuple of (success: bool, post_url: Optional[str])
        """
        if not self.is_configured():
            return False, None
        
        # Validate length
        if len(text) > self.max_length:
            logger.error(f"Bluesky: Post exceeds {self.max_length} chars ({len(text)} chars)")
            return False, None
        
        try:
            client = self._get_client()
            
            # Build facets for clickable links
            facets = self._build_facets(text)
            
            logger.info(f"Bluesky: Posting with {len(facets)} link facet(s)...")
            
            # Create the post
            response = client.send_post(
                text=text,
                facets=facets if facets else None
            )
            
            if response and hasattr(response, 'uri'):
                # Convert AT URI to web URL
                # AT URI format: at://did:plc:xxxx/app.bsky.feed.post/xxxx
                # Web URL format: https://bsky.app/profile/handle/post/xxxx
                uri = response.uri
                
                # Extract the rkey (post ID) from the AT URI
                rkey = uri.split('/')[-1] if '/' in uri else None
                
                if rkey and self._handle:
                    post_url = f"https://bsky.app/profile/{self._handle}/post/{rkey}"
                else:
                    post_url = f"https://bsky.app/profile/{self._handle}"
                
                logger.info(f"Bluesky: Posted successfully - {post_url}")
                return True, post_url
            else:
                logger.error("Bluesky: Response missing URI")
                return False, None
                
        except Exception as e:
            error_msg = str(e).lower()
            
            # Check for duplicate content error
            if "duplicate" in error_msg:
                logger.error(f"Bluesky: Duplicate content detected - {e}")
                return False, "DUPLICATE_CONTENT"
            
            logger.error(f"Bluesky: Failed to post - {e}", exc_info=True)
            return False, None


# Module-level instance for direct usage
_publisher = None


def get_publisher() -> BlueskyPublisher:
    """Get or create a BlueskyPublisher instance."""
    global _publisher
    if _publisher is None:
        _publisher = BlueskyPublisher()
    return _publisher


def post_to_bluesky(text: str) -> Tuple[bool, Optional[str]]:
    """
    Convenience function to post to Bluesky.
    
    Args:
        text: The post content
        
    Returns:
        Tuple of (success, post_url)
    """
    return get_publisher().post(text)


def format_bill_for_bluesky(bill: Dict) -> str:
    """
    Convenience function to format a bill for Bluesky.
    
    Args:
        bill: Bill dictionary
        
    Returns:
        Formatted post text
    """
    return get_publisher().format_post(bill)


if __name__ == "__main__":
    # Test the publisher
    logger.info("Testing Bluesky publisher...")
    
    publisher = BlueskyPublisher()
    
    if not publisher.is_configured():
        logger.error("Bluesky credentials not configured. Set BLUESKY_HANDLE and BLUESKY_APP_PASSWORD")
        exit(1)
    
    # Test with a sample bill
    test_bill = {
        "summary_tweet": "A new bipartisan bill aims to expand computer science education in public schools, providing funding for teacher training and curriculum development.",
        "website_slug": "hr-1234-119",
        "title": "Computer Science Education Act",
        "normalized_status": "introduced"
    }
    
    formatted = publisher.format_post(test_bill)
    print(f"\n📝 Formatted post ({len(formatted)} chars):\n")
    print(formatted)
    print("\n" + "="*50)
    
    # Validate
    is_valid, reason = publisher.validate_post(formatted)
    print(f"Validation: {'✅ Valid' if is_valid else '❌ Invalid'} - {reason}")
    
    # Prompt before actually posting
    response = input("\nPost this to Bluesky? (y/n): ")
    if response.lower() == 'y':
        success, url = publisher.post(formatted)
        if success:
            print(f"✅ Posted: {url}")
        else:
            print(f"❌ Failed to post")
    else:
        print("Skipped posting.")
