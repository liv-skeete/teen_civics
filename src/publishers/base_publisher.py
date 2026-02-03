"""
Base publisher interface for multi-platform posting.
All platform-specific publishers inherit from this abstract base class.
"""

from abc import ABC, abstractmethod
from typing import Dict, Tuple, Optional
import logging

logger = logging.getLogger(__name__)


class BasePublisher(ABC):
    """
    Abstract base class for social media publishers.
    Each platform (Twitter, Bluesky, Threads) implements this interface.
    """
    
    @property
    @abstractmethod
    def platform_name(self) -> str:
        """Return the name of the platform (e.g., 'twitter', 'bluesky', 'threads')."""
        pass
    
    @property
    @abstractmethod
    def max_length(self) -> int:
        """Return the maximum post length for this platform."""
        pass
    
    @abstractmethod
    def is_configured(self) -> bool:
        """Check if all required credentials are present for this platform."""
        pass
    
    @abstractmethod
    def format_post(self, bill: Dict) -> str:
        """
        Format a bill into a platform-appropriate post.
        
        Args:
            bill: Dictionary containing bill data (summary_tweet, website_slug, etc.)
            
        Returns:
            Formatted post text ready for publishing
        """
        pass
    
    @abstractmethod
    def post(self, text: str) -> Tuple[bool, Optional[str]]:
        """
        Post content to the platform.
        
        Args:
            text: The formatted post content
            
        Returns:
            Tuple of (success: bool, post_url: Optional[str])
        """
        pass
    
    def validate_post(self, text: str) -> Tuple[bool, str]:
        """
        Validate post content before publishing.
        
        Args:
            text: The post content to validate
            
        Returns:
            Tuple of (is_valid: bool, reason: str)
        """
        if not text or len(text.strip()) == 0:
            return False, "Empty post text"
        
        if len(text) > self.max_length:
            return False, f"Post exceeds {self.max_length} character limit ({len(text)} chars)"
        
        return True, "ok"
    
    def publish_bill(self, bill: Dict) -> Tuple[bool, Optional[str]]:
        """
        High-level method to format and publish a bill.
        
        Args:
            bill: Dictionary containing bill data
            
        Returns:
            Tuple of (success: bool, post_url: Optional[str])
        """
        if not self.is_configured():
            logger.warning(f"{self.platform_name}: Not configured, skipping")
            return False, None
        
        try:
            formatted = self.format_post(bill)
            is_valid, reason = self.validate_post(formatted)
            
            if not is_valid:
                logger.error(f"{self.platform_name}: Validation failed - {reason}")
                return False, None
            
            success, url = self.post(formatted)
            
            if success:
                logger.info(f"{self.platform_name}: Posted successfully - {url}")
            else:
                logger.error(f"{self.platform_name}: Failed to post")
            
            return success, url
            
        except Exception as e:
            logger.error(f"{self.platform_name}: Error publishing - {e}", exc_info=True)
            return False, None
