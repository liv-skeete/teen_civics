#!/usr/bin/env python3
"""
Unit tests for tweet validation and formatting functions.
"""

import sys
import os
import unittest
from unittest.mock import patch, MagicMock

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from publishers.twitter_publisher import validate_tweet_content, format_bill_tweet


class TestTweetValidation(unittest.TestCase):
    """Test cases for tweet validation and formatting."""

    def setUp(self):
        """Set up test data."""
        self.valid_bill_data = {
            "bill_id": "hr1234-119",
            "title": "Sample Bill Title",
            "summary_tweet": "This is a sample tweet summary.",
            "website_slug": "sample-bill-title-hr1234-119",
            "status": "Introduced",
            "normalized_status": "introduced"
        }

    def test_validate_tweet_content_valid(self):
        """Test that a valid tweet passes validation."""
        tweet = (
            "🏛️ Today in Congress\n\n"
            "This is a sample tweet summary that is longer to meet the minimum length requirement for validation.\n\n"
            "👉 See how this affects you: teencivics.org/bill/sample-bill-title-hr1234-119"
        )
        is_valid, reason = validate_tweet_content(tweet, self.valid_bill_data)
        self.assertTrue(is_valid, f"Valid tweet should pass validation. Reason: {reason}")

    def test_validate_tweet_content_no_summary_available(self):
        """Test that a tweet with 'No summary available' fails validation."""
        tweet = (
            "🏛️ Today in Congress\n\n"
            "No summary available.\n\n"
            "👉 See how this affects you: teencivics.org/bill/sample-bill-title-hr1234-119"
        )
        is_valid, reason = validate_tweet_content(tweet, self.valid_bill_data)
        self.assertFalse(is_valid, "Tweet with 'No summary available' should fail validation")
        self.assertIn("placeholder phrase", reason)

    def test_validate_tweet_content_coming_soon(self):
        """Test that a tweet with 'coming soon' fails validation."""
        tweet = (
            "🏛️ Today in Congress\n\n"
            "Details coming soon.\n\n"
            "👉 See how this affects you: teencivics.org/bill/sample-bill-title-hr1234-119"
        )
        is_valid, reason = validate_tweet_content(tweet, self.valid_bill_data)
        self.assertFalse(is_valid, "Tweet with 'coming soon' should fail validation")
        self.assertIn("placeholder phrase", reason)

    def test_validate_tweet_content_too_short(self):
        """Test that a tweet with too short summary fails validation."""
        tweet = (
            "🏛️ Today in Congress\n\n"
            "Short.\n\n"
            "👉 See how this affects you: teencivics.org/bill/sample-bill-title-hr1234-119"
        )
        is_valid, reason = validate_tweet_content(tweet, self.valid_bill_data)
        self.assertFalse(is_valid, "Tweet with too short summary should fail validation")
        self.assertIn("too short", reason)

    def test_validate_tweet_content_missing_link(self):
        """Test that a tweet with missing link fails validation."""
        tweet = (
            "🏛️ Today in Congress\n\n"
            "This is a sample tweet summary.\n\n"
            "👉 See how this affects you: teencivics.org/bill/sample-bill-title-hr1234-119"
        )
        # Use bill data with different slug
        bill_data = self.valid_bill_data.copy()
        bill_data["website_slug"] = "different-slug"
        is_valid, reason = validate_tweet_content(tweet, bill_data)
        self.assertFalse(is_valid, "Tweet with incorrect link should fail validation")
        self.assertIn("Missing or incorrect bill link", reason)

    def test_validate_tweet_content_missing_slug(self):
        """Test that a tweet with missing website_slug fails validation."""
        tweet = (
            "🏛️ Today in Congress\n\n"
            "This is a sample tweet summary.\n\n"
            "👉 See how this affects you: teencivics.org/bill/sample-bill-title-hr1234-119"
        )
        # Use bill data without website_slug
        bill_data = self.valid_bill_data.copy()
        bill_data["website_slug"] = ""
        is_valid, reason = validate_tweet_content(tweet, bill_data)
        self.assertFalse(is_valid, "Tweet with missing website_slug should fail validation")
        self.assertIn("Missing website_slug", reason)

    def test_format_bill_tweet_with_valid_data(self):
        """Test that format_bill_tweet produces valid output with normal data."""
        tweet = format_bill_tweet(self.valid_bill_data)
        self.assertIsInstance(tweet, str)
        self.assertGreater(len(tweet), 50, "Tweet should have substantial content")
        self.assertIn("🏛️ Today in Congress", tweet, "Tweet should include header")
        self.assertIn("teencivics.org/bill/sample-bill-title-hr1234-119", tweet, "Tweet should include correct link")
        self.assertIn("👉 See how this affects you:", tweet, "Tweet should include footer")

    def test_format_bill_tweet_no_summary_available(self):
        """Test that format_bill_tweet never emits 'No summary available'."""
        bill_data = self.valid_bill_data.copy()
        bill_data["summary_tweet"] = "No summary available."
        bill_data["summary_overview"] = ""
        bill_data["summary_short"] = ""
        bill_data["title"] = "Test Bill Title"
        
        tweet = format_bill_tweet(bill_data)
        self.assertIsInstance(tweet, str)
        self.assertNotIn("No summary available", tweet, "Tweet should never contain 'No summary available'")
        self.assertIn("Test Bill Title", tweet, "Tweet should contain bill title when summaries are missing")

    def test_format_bill_tweet_empty_data(self):
        """Test that format_bill_tweet handles empty data gracefully."""
        tweet = format_bill_tweet({})
        self.assertIsInstance(tweet, str)
        self.assertGreater(len(tweet), 20, "Tweet should have content even with empty data")
        self.assertIn("🏛️ Today in Congress", tweet, "Tweet should include header even with empty data")


if __name__ == '__main__':
    unittest.main()