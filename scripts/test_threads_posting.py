#!/usr/bin/env python3
"""
Test script for Threads integration.
Verifies credentials and optionally posts a test message.

Usage:
    python scripts/test_threads_posting.py           # Dry run (no posting)
    python scripts/test_threads_posting.py --post    # Actually post to Threads
"""

import os
import sys
import argparse
import logging

from dotenv import load_dotenv

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.publishers.threads_publisher import ThreadsPublisher

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_threads_posting(actually_post: bool = False):
    """Test the Threads integration."""
    load_dotenv()
    
    print("\n" + "=" * 50)
    print("🧵 Threads Integration Test")
    print("=" * 50)
    
    # Check credentials
    user_id = os.getenv("THREADS_USER_ID")
    token = os.getenv("THREADS_ACCESS_TOKEN")
    
    print("\n📋 Credential Check:")
    print(f"   THREADS_USER_ID: {'✅ Set' if user_id else '❌ Missing'}")
    print(f"   THREADS_ACCESS_TOKEN: {'✅ Set' if token else '❌ Missing'}")
    
    if not user_id or not token:
        print("\n⚠️  Missing credentials. Please add to your .env file:")
        print("   THREADS_USER_ID=your_user_id")
        print("   THREADS_ACCESS_TOKEN=your_access_token")
        print("\n📖 See the guide below for how to obtain these credentials.")
        print_token_guide()
        return False

    # Initialize publisher
    publisher = ThreadsPublisher()
    
    print(f"\n📊 Publisher Status:")
    print(f"   Platform: {publisher.platform_name}")
    print(f"   Max Length: {publisher.max_length} chars")
    print(f"   Configured: {'✅ Yes' if publisher.is_configured() else '❌ No'}")
    
    if not publisher.is_configured():
        print("\n❌ Publisher verification failed.")
        return False
    
    # Test formatting with a sample bill
    test_bill = {
        "summary_tweet": "A bipartisan bill was introduced to expand computer science education in public schools, providing funding for teacher training and curriculum development across all 50 states.",
        "website_slug": "hr-1234-119",
        "title": "Computer Science Education Act",
        "normalized_status": "introduced"
    }
    
    formatted = publisher.format_post(test_bill)
    
    print(f"\n📝 Formatted Post Preview ({len(formatted)}/{publisher.max_length} chars):")
    print("-" * 50)
    print(formatted)
    print("-" * 50)
    
    # Validate
    is_valid, reason = publisher.validate_post(formatted)
    print(f"\n✅ Validation: {'Passed' if is_valid else 'Failed - ' + reason}")
    
    if actually_post:
        print("\n🚀 Posting to Threads...")
        
        # Use a test message instead of the bill format for testing
        test_message = (
            "🤖 Test Post\n\n"
            "This is an automated test from TeenCivics integration. "
            "If you see this, the Threads API is working!\n\n"
            "👉 https://teencivics.org"
        )
        
        success, url = publisher.post(test_message)
        
        if success:
            print(f"\n✅ SUCCESS! Post published to Threads")
            print(f"   URL: {url}")
            return True
        else:
            print("\n❌ FAILED: Could not publish post")
            print("   Check the logs above for error details.")
            return False
    else:
        print("\n💡 Dry run complete. Use --post flag to actually post.")
        return True


def print_token_guide():
    """Print instructions for obtaining Threads credentials."""
    guide = """
╔══════════════════════════════════════════════════════════════════╗
║         HOW TO GET YOUR THREADS ACCESS TOKEN                      ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                   ║
║  1. Go to: https://developers.facebook.com/                       ║
║                                                                   ║
║  2. Create a Meta Developer account (if you don't have one)       ║
║                                                                   ║
║  3. Create a new App:                                             ║
║     • Click "Create App"                                          ║
║     • Select "Other" use case                                     ║
║     • Choose "Business" app type                                  ║
║     • Name your app (e.g., "TeenCivics Threads Bot")              ║
║                                                                   ║
║  4. Add the Threads API product:                                  ║
║     • In your app dashboard, click "Add Products"                 ║
║     • Find "Threads API" and click "Set Up"                       ║
║                                                                   ║
║  5. Configure permissions:                                        ║
║     • Go to Threads API > Settings                                ║
║     • Add your Threads account as a test user                     ║
║     • Request: threads_basic, threads_content_publish             ║
║                                                                   ║
║  6. Generate Access Token:                                        ║
║     • Go to Threads API > Access Token                            ║
║     • Use the "Generate Token" tool                               ║
║     • This gives you a SHORT-LIVED token (1 hour)                 ║
║                                                                   ║
║  7. Exchange for LONG-LIVED token:                                ║
║     • Make a GET request to:                                      ║
║       https://graph.threads.net/access_token                      ║
║       ?grant_type=th_exchange_token                               ║
║       &client_secret=YOUR_APP_SECRET                              ║
║       &access_token=YOUR_SHORT_LIVED_TOKEN                        ║
║     • This returns a token valid for 60 days                      ║
║                                                                   ║
║  8. Get your User ID:                                             ║
║     • Make a GET request to:                                      ║
║       https://graph.threads.net/v1.0/me                           ║
║       ?access_token=YOUR_LONG_LIVED_TOKEN                         ║
║     • The "id" field is your THREADS_USER_ID                      ║
║                                                                   ║
║  9. Add to .env:                                                  ║
║     THREADS_USER_ID=your_user_id_here                             ║
║     THREADS_ACCESS_TOKEN=your_long_lived_token_here               ║
║                                                                   ║
║  ⚠️  Important: Long-lived tokens expire after 60 days.           ║
║     You'll need to refresh them before expiry.                    ║
║                                                                   ║
╚══════════════════════════════════════════════════════════════════╝
"""
    print(guide)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test Threads integration")
    parser.add_argument(
        "--post",
        action="store_true",
        help="Actually post a test message to Threads"
    )
    parser.add_argument(
        "--guide",
        action="store_true",
        help="Print the token generation guide"
    )
    args = parser.parse_args()
    
    if args.guide:
        print_token_guide()
    else:
        success = test_threads_posting(actually_post=args.post)
        sys.exit(0 if success else 1)
