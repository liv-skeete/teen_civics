"""
Publisher Manager - Orchestrates posting to multiple social media platforms.
Handles Twitter, Bluesky, and Threads in a unified way.
"""

import logging
from typing import Dict, List, Tuple, Optional

from src.publishers.base_publisher import BasePublisher

# Configure logging
logger = logging.getLogger(__name__)


class PublisherManager:
    """
    Manages multi-platform publishing for TeenCivics.
    
    Automatically detects which platforms are configured and posts to all of them.
    Individual platform failures don't block other platforms from posting.
    """
    
    def __init__(self):
        self.publishers: List[BasePublisher] = []
        self._load_publishers()
    
    def _load_publishers(self):
        """
        Load and register all configured publishers.
        Only adds publishers that have valid credentials configured.
        """
        # Twitter publisher (existing)
        try:
            from src.publishers.twitter_publisher import api_v1, client_v2
            
            # Create a minimal wrapper to check if Twitter is configured
            if api_v1 is not None or client_v2 is not None:
                logger.info("PublisherManager: Twitter is configured")
                # We'll handle Twitter specially since it doesn't follow BasePublisher yet
                self._twitter_configured = True
            else:
                logger.info("PublisherManager: Twitter not configured")
                self._twitter_configured = False
        except Exception as e:
            logger.warning(f"PublisherManager: Could not load Twitter publisher - {e}")
            self._twitter_configured = False
        
        # Bluesky publisher
        try:
            from src.publishers.bluesky_publisher import BlueskyPublisher
            
            bluesky = BlueskyPublisher()
            if bluesky.is_configured():
                self.publishers.append(bluesky)
                logger.info("PublisherManager: Bluesky is configured")
            else:
                logger.info("PublisherManager: Bluesky not configured")
        except ImportError as e:
            logger.warning(f"PublisherManager: Could not import Bluesky publisher - {e}")
        except Exception as e:
            logger.warning(f"PublisherManager: Error loading Bluesky publisher - {e}")
        
        # Threads publisher (future)
        try:
            from src.publishers.threads_publisher import ThreadsPublisher
            
            threads = ThreadsPublisher()
            if threads.is_configured():
                self.publishers.append(threads)
                logger.info("PublisherManager: Threads is configured")
            else:
                logger.info("PublisherManager: Threads not configured")
        except ImportError:
            # Threads publisher not yet implemented
            logger.debug("PublisherManager: Threads publisher not available")
        except Exception as e:
            logger.warning(f"PublisherManager: Error loading Threads publisher - {e}")
        
        logger.info(f"PublisherManager: Loaded {len(self.publishers)} BasePublisher platforms")
    
    def get_configured_platforms(self) -> List[str]:
        """Return list of configured platform names."""
        platforms = []
        
        if self._twitter_configured:
            platforms.append("twitter")
        
        for publisher in self.publishers:
            platforms.append(publisher.platform_name)
        
        return platforms
    
    def publish_bill_to_all(self, bill: Dict) -> Dict[str, Tuple[bool, Optional[str]]]:
        """
        Publish a bill to all configured platforms.
        
        Args:
            bill: Dictionary containing bill data
            
        Returns:
            Dict mapping platform name to (success, url) tuple
        """
        results = {}
        
        # Handle Twitter separately (legacy publisher, not BasePublisher)
        if self._twitter_configured:
            try:
                from src.publishers.twitter_publisher import (
                    format_bill_tweet, post_tweet, validate_tweet_content
                )
                
                tweet_text = format_bill_tweet(bill)
                is_valid, reason = validate_tweet_content(tweet_text, bill)
                
                if is_valid:
                    success, url = post_tweet(tweet_text)
                    results["twitter"] = (success, url)
                    if success:
                        logger.info(f"PublisherManager: Twitter posted - {url}")
                    else:
                        logger.error(f"PublisherManager: Twitter failed to post")
                else:
                    logger.error(f"PublisherManager: Twitter validation failed - {reason}")
                    results["twitter"] = (False, None)
                    
            except Exception as e:
                logger.error(f"PublisherManager: Twitter error - {e}", exc_info=True)
                results["twitter"] = (False, None)
        
        # Handle all BasePublisher platforms
        for publisher in self.publishers:
            try:
                success, url = publisher.publish_bill(bill)
                results[publisher.platform_name] = (success, url)
            except Exception as e:
                logger.error(f"PublisherManager: {publisher.platform_name} error - {e}", exc_info=True)
                results[publisher.platform_name] = (False, None)
        
        # Log summary
        success_count = sum(1 for s, _ in results.values() if s)
        total_count = len(results)
        logger.info(f"PublisherManager: Posted to {success_count}/{total_count} platforms")
        
        return results
    
    def publish_to_platform(self, platform: str, bill: Dict) -> Tuple[bool, Optional[str]]:
        """
        Publish to a specific platform only.
        
        Args:
            platform: Platform name ('twitter', 'bluesky', 'threads')
            bill: Dictionary containing bill data
            
        Returns:
            Tuple of (success, url)
        """
        if platform == "twitter" and self._twitter_configured:
            try:
                from src.publishers.twitter_publisher import (
                    format_bill_tweet, post_tweet, validate_tweet_content
                )
                
                tweet_text = format_bill_tweet(bill)
                is_valid, reason = validate_tweet_content(tweet_text, bill)
                
                if is_valid:
                    return post_tweet(tweet_text)
                else:
                    logger.error(f"Twitter validation failed: {reason}")
                    return False, None
            except Exception as e:
                logger.error(f"Twitter error: {e}")
                return False, None
        
        for publisher in self.publishers:
            if publisher.platform_name == platform:
                return publisher.publish_bill(bill)
        
        logger.error(f"Platform '{platform}' not found or not configured")
        return False, None
    
    def dry_run(self, bill: Dict) -> Dict[str, str]:
        """
        Generate formatted posts for all platforms without actually posting.
        Useful for testing and preview.
        
        Args:
            bill: Dictionary containing bill data
            
        Returns:
            Dict mapping platform name to formatted post content
        """
        previews = {}
        
        # Twitter preview
        if self._twitter_configured:
            try:
                from src.publishers.twitter_publisher import format_bill_tweet
                previews["twitter"] = format_bill_tweet(bill)
            except Exception as e:
                previews["twitter"] = f"Error: {e}"
        
        # BasePublisher platform previews
        for publisher in self.publishers:
            try:
                previews[publisher.platform_name] = publisher.format_post(bill)
            except Exception as e:
                previews[publisher.platform_name] = f"Error: {e}"
        
        return previews


# Module-level singleton
_manager = None


def get_publisher_manager() -> PublisherManager:
    """Get or create the PublisherManager singleton."""
    global _manager
    if _manager is None:
        _manager = PublisherManager()
    return _manager


if __name__ == "__main__":
    # Test the publisher manager
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    manager = PublisherManager()
    
    print("\n📱 Configured Platforms:")
    for platform in manager.get_configured_platforms():
        print(f"  ✅ {platform}")
    
    # Test with sample bill
    test_bill = {
        "summary_tweet": "A bipartisan bill was introduced to expand computer science education in public schools, providing funding for teacher training.",
        "website_slug": "hr-1234-119",
        "title": "Computer Science Education Act",
        "normalized_status": "introduced"
    }
    
    print("\n📝 Dry Run Preview:")
    previews = manager.dry_run(test_bill)
    for platform, content in previews.items():
        print(f"\n--- {platform.upper()} ({len(content)} chars) ---")
        print(content)
