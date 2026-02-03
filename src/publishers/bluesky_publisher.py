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
        
        Bluesky allows 300 chars, slightly more than Twitter's 280.
        We use a similar format but can include a bit more detail.
        """
        if not bill:
            bill = {}
        
        # Get summary text (prioritize tweet-length summary)
        summary_text = (
            bill.get("summary_tweet")
            or bill.get("summary_overview")
            or bill.get("summary_short")
            or bill.get("title")
        )
        
        # Handle placeholder text
        if summary_text and "no summary available" in summary_text.lower():
            summary_text = None
        
        # Fallback to constructed summary
        if not summary_text:
            status_raw = (bill.get("normalized_status") or bill.get("status") or "").strip()
            status_disp = status_raw.replace("_", " ").title() if status_raw else "Introduced"
            title = (bill.get("title") or bill.get("short_title") or bill.get("bill_id") or "").strip()
            base = title if title else (bill.get("bill_id") or "This bill")
            summary_text = f"{base}. Status: {status_disp}."
        
        # Normalize whitespace
        summary_text = (summary_text or "").replace("\n", " ").replace("\r", " ").strip()
        
        # Clean up hashtags and decorative characters
        summary_text = re.sub(r"\s#[\w_]+", "", summary_text)
        summary_text = re.sub(r"^[^\w]+", "", summary_text).strip()
        summary_text = re.sub(r"\s{2,}", " ", summary_text)
        
        # Build post structure
        header = "🏛️ Today in Congress\n"
        
        # Get bill link - use short bill_id format to save characters
        # Unlike Twitter, Bluesky doesn't shorten URLs via t.co
        # So we use the compact bill_id format instead of the full slug
        bill_id = bill.get("bill_id", "")
        website_slug = bill.get("website_slug")
        
        if bill_id:
            # Use short format: /bill/hr171-119 instead of full slug
            link = f"https://teencivics.org/bill/{bill_id}"
        elif website_slug:
            link = f"https://teencivics.org/bill/{website_slug}"
        else:
            link = "https://teencivics.org"
        
        footer = f"\n👉 {link}"
        
        # Calculate available space for summary
        # Unlike Twitter, Bluesky doesn't shorten URLs
        available_space = self.max_length - len(header) - len(footer)
        
        # Trim summary if needed
        if len(summary_text) > available_space:
            logger.info(f"Bluesky: Trimming summary from {len(summary_text)} to {available_space} chars")
            # Hard cut first, then find good break point
            cut = summary_text[:available_space - 3].rstrip()  # Reserve 3 chars for "..."
            
            # Try to cut at sentence boundary
            for punct in [".", "!", "?"]:
                idx = cut.rfind(punct)
                if idx != -1 and idx >= 40:
                    summary_text = cut[:idx + 1]
                    break
            else:
                # Cut at last space and add ellipsis
                sp = cut.rfind(" ")
                if sp >= 40:
                    cut = cut[:sp].rstrip()
                summary_text = cut + "..."
        
        formatted_post = f"{header}{summary_text}{footer}"
        
        # Final safety check - hard truncate if still over limit
        if len(formatted_post) > self.max_length:
            overflow = len(formatted_post) - self.max_length
            logger.warning(f"Bluesky: Post still {overflow} chars over limit, force-truncating")
            # Recalculate with smaller summary
            summary_text = summary_text[:len(summary_text) - overflow - 3].rstrip() + "..."
            formatted_post = f"{header}{summary_text}{footer}"
        
        logger.info(f"Bluesky: Formatted post length: {len(formatted_post)} chars")
        
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
