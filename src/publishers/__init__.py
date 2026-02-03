"""
Publishers package - Multi-platform social media posting for TeenCivics.

Supported platforms:
- Twitter/X (via tweepy)
- Bluesky (via atproto)
- Threads (via Meta API - future)
"""

from src.publishers.base_publisher import BasePublisher
from src.publishers.twitter_publisher import (
    post_tweet,
    format_bill_tweet,
    validate_tweet_content,
)
from src.publishers.bluesky_publisher import (
    BlueskyPublisher,
    post_to_bluesky,
    format_bill_for_bluesky,
)
from src.publishers.publisher_manager import (
    PublisherManager,
    get_publisher_manager,
)

__all__ = [
    # Base
    "BasePublisher",
    # Twitter
    "post_tweet",
    "format_bill_tweet",
    "validate_tweet_content",
    # Bluesky
    "BlueskyPublisher",
    "post_to_bluesky",
    "format_bill_for_bluesky",
    # Manager
    "PublisherManager",
    "get_publisher_manager",
]
