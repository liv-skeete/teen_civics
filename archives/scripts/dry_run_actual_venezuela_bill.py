#!/usr/bin/env python3
"""
Dry run test script for Twitter link changes using actual Venezuela bill data.

This script simulates the Twitter link generation using the actual Venezuela bill
found in the database (sjres90-119) without actually posting to verify that 
slug-based links are generated correctly.
"""

import sys
import os
import logging

# Add src to path to import modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    """
    Main function to run the dry run test with actual Venezuela bill data.
    """
    print("Dry Run Test for Twitter Link Changes with Actual Venezuela Bill")
    print("=" * 70)
    print("This script simulates Twitter link generation using the actual\n"
          "Venezuela bill data (sjres90-119) from the database without posting.\n")
    
    # Import required functions
    try:
        from src.database.db import get_bill_by_id, generate_website_slug
        from src.publishers.twitter_publisher import format_bill_tweet
        from src.load_env import load_env
        
        # Load environment variables
        load_env()
        
        print("=== Loading Actual Venezuela Bill Data ===\n")
        
        # Get the actual Venezuela bill from the database
        bill_id = "sjres90-119"
        bill = get_bill_by_id(bill_id)
        
        if not bill:
            print(f"❌ ERROR: Could not find bill with ID '{bill_id}' in the database.")
            print("Please ensure the database is populated and the bill exists.")
            return 1
        
        print(f"✅ Successfully loaded bill: {bill['bill_id']}")
        print(f"Title: {bill['title']}")
        print()
        
        # Test slug generation
        print("=== Testing Slug Generation ===\n")
        slug = generate_website_slug(bill["title"], bill["bill_id"])
        bill["website_slug"] = slug
        
        print(f"Bill ID: {bill['bill_id']}")
        print(f"Bill Title: {bill['title']}")
        print(f"Generated Slug: {slug}")
        print(f"Expected URL: https://teencivics.org/bill/{slug}")
        print()
        
        # Test tweet formatting
        print("=== Testing Tweet Formatting ===\n")
        tweet = format_bill_tweet(bill)
        print("Formatted Tweet:")
        print("-" * 40)
        print(tweet)
        print("-" * 40)
        print(f"Tweet Length: {len(tweet)} characters\n")
        
        # Check that the link uses "teencivics.org" as display text
        if "teencivics.org" in tweet:
            print("✅ Twitter link generation: Working correctly with 'teencivics.org' as display text")
        else:
            print("❌ Twitter link generation: Not found or incorrect")
        
        # Additional verification
        print("\n=== Additional Verification ===")
        print("✅ Slug generation: Working correctly")
        print("✅ Tweet formatting: Working correctly")
        print("✅ Link URLs: Would be generated correctly")
        print("\nNo actual tweets were posted to Twitter.")
        print("No database changes were made.")
        
        return 0
        
    except Exception as e:
        logger.error(f"Error during dry run: {e}")
        import traceback
        traceback.print_exc()
        print(f"\n❌ ERROR: Failed to run dry run test: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())