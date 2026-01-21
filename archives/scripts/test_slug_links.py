#!/usr/bin/env python3
"""
Test script to verify that Twitter publisher correctly uses bill slugs in links.
"""

import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from publishers.twitter_publisher import format_bill_tweet

def test_slug_links():
    """Test that format_bill_tweet correctly uses bill slugs in links."""
    
    print("=" * 60)
    print("TESTING TWITTER PUBLISHER SLUG LINKS")
    print("=" * 60)
    
    # Test 1: Bill with website_slug
    print("\nTest 1: Bill with website_slug")
    bill_with_slug = {
        'summary_tweet': 'Senate resolution would force withdrawal of U.S. troops from Venezuela operations Congress never authorized. Failed key vote 49-51, blocking debate on Presidential war powers.',
        'title': 'Resolution on Withdrawal of Troops from Venezuela',
        'website_slug': 'resolution-withdrawal-troops-venezuela-sres83-119'
    }
    
    tweet_with_slug = format_bill_tweet(bill_with_slug)
    print(f"Tweet with slug ({len(tweet_with_slug)} chars):")
    print("-" * 50)
    print(tweet_with_slug)
    print("-" * 50)
    
    # Check if the slug link is correctly included
    expected_slug_link = "teencivics.org/bill/resolution-withdrawal-troops-venezuela-sres83-119"
    has_slug_link = expected_slug_link in tweet_with_slug
    print(f"Contains slug link: {'✅' if has_slug_link else '❌'}")
    
    # Test 2: Bill without website_slug (fallback)
    print("\nTest 2: Bill without website_slug (fallback)")
    bill_without_slug = {
        'summary_tweet': 'House bill proposes new education funding for computer science programs in public schools.',
        'title': 'Computer Science Education Funding Act'
        # No website_slug field
    }
    
    tweet_without_slug = format_bill_tweet(bill_without_slug)
    print(f"Tweet without slug ({len(tweet_without_slug)} chars):")
    print("-" * 50)
    print(tweet_without_slug)
    print("-" * 50)
    
    # Check if the generic link is correctly included
    has_generic_link = "teencivics.org" in tweet_without_slug
    print(f"Contains generic link: {'✅' if has_generic_link else '❌'}")
    
    # Test 3: Character limit test
    print("\nTest 3: Long summary with character limits")
    long_bill = {
        'summary_tweet': 'This is a very long summary that might exceed the character limit when combined with the header and footer. We need to make sure the tweet formatting works correctly even with long content. The system should truncate appropriately to fit within Twitter\'s 280 character limit while preserving the slug link in the footer.',
        'title': 'Long Summary Bill',
        'website_slug': 'long-summary-bill-hr5678-119'
    }
    
    long_tweet = format_bill_tweet(long_bill)
    print(f"Long tweet ({len(long_tweet)} chars):")
    print("-" * 50)
    print(long_tweet)
    print("-" * 50)
    
    within_limit = len(long_tweet) <= 280
    print(f"Within 280 character limit: {'✅' if within_limit else '❌'}")
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    if has_slug_link and has_generic_link and within_limit:
        print("✅ All tests passed!")
        print("Twitter publisher correctly uses bill slugs in links.")
    else:
        print("❌ Some tests failed!")
        if not has_slug_link:
            print("  - Slug link not correctly included")
        if not has_generic_link:
            print("  - Generic link fallback not working")
        if not within_limit:
            print("  - Character limit not respected")
    
    return has_slug_link and has_generic_link and within_limit

if __name__ == "__main__":
    success = test_slug_links()
    sys.exit(0 if success else 1)