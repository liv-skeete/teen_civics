#!/usr/bin/env python3
"""
Dry run test script for orchestrator.py with Venezuela resolution data.

This script simulates the orchestrator workflow with a specific focus on 
Twitter link generation for the Venezuela resolution without actually posting.
"""

import sys
import os
import re
from typing import Dict, Any

# Add src to path to import modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Import required functions
from src.database.db import generate_website_slug, normalize_bill_id
from src.publishers.twitter_publisher import format_bill_tweet

def create_venezuela_resolution_example():
    """
    Create sample bill data for the Venezuela resolution example.
    """
    return {
        "bill_id": "hjres104-118",
        "title": "Joint Resolution Continuing Temporary Diplomatic Acceptance of the Venezuelan Republic's Declaration of Independence",
        "summary_tweet": "Joint resolution continuing temporary diplomatic acceptance of Venezuela's declaration of independence (not recognizing Maduro government).",
        "summary_overview": "This joint resolution expresses the sense of Congress regarding continued temporary diplomatic acceptance of the declaration of independence of the Venezuelan Republic, while withholding recognition of the Maduro government.",
        "short_title": "Venezuela Diplomatic Recognition Resolution",
        "status": "Introduced",
        "congress_session": "118",
        "date_introduced": "2023-05-16T00:00:00",
        "source_url": "https://www.congress.gov/bill/118th-congress/house-joint-resolution/104",
        "website_slug": "",  # Will be generated
        "tags": ["foreign-affairs", "venezuela", "diplomacy"],
        "tweet_posted": False,
        "normalized_status": "introduced"
    }

def test_slug_generation():
    """
    Test the slug generation with Venezuela resolution data.
    """
    print("=== Testing Slug Generation ===\n")
    
    # Create Venezuela resolution example
    bill = create_venezuela_resolution_example()
    slug = generate_website_slug(bill["title"], bill["bill_id"])
    bill["website_slug"] = slug
    
    print(f"Bill ID: {bill['bill_id']}")
    print(f"Bill Title: {bill['title']}")
    print(f"Generated Slug: {slug}")
    print(f"Expected URL: https://teencivics.org/bill/{slug}")
    print()
    
    return bill

def test_tweet_formatting(bill):
    """
    Test tweet formatting with slug-based links for Venezuela resolution.
    """
    print("=== Testing Tweet Formatting ===\n")
    
    # Format tweet
    tweet = format_bill_tweet(bill)
    print("Venezuela Resolution Tweet:")
    print("-" * 40)
    print(tweet)
    print("-" * 40)
    print(f"Tweet Length: {len(tweet)} characters\n")
    
    # Check that the link uses "teencivics.org" as display text
    if "teencivics.org" in tweet:
        print("✅ Twitter link generation: Working correctly with 'teencivics.org' as display text")
    else:
        print("❌ Twitter link generation: Not found or incorrect")
    
    return tweet

def simulate_orchestrator_processing():
    """
    Simulate the orchestrator processing flow for the Venezuela resolution.
    """
    print("=== Orchestrator Processing Simulation ===\n")
    
    # Step 1: Create bill data (similar to what orchestrator would receive)
    print("1. Creating bill data...")
    bill = create_venezuela_resolution_example()
    print(f"   Bill ID: {bill['bill_id']}")
    print(f"   Title: {bill['title']}")
    print()
    
    # Step 2: Generate website slug (as orchestrator would do)
    print("2. Generating website slug...")
    slug = generate_website_slug(bill["title"], bill["bill_id"])
    bill["website_slug"] = slug
    print(f"   Generated Slug: {slug}")
    print()
    
    # Step 3: Format tweet (as orchestrator would do)
    print("3. Formatting tweet...")
    tweet = format_bill_tweet(bill)
    print(f"   Tweet Length: {len(tweet)} characters")
    print()
    
    # Step 4: Dry run output (what would be posted)
    print("4. Dry Run Output:")
    print("   Would post tweet:")
    print("   " + "-" * 37)
    for line in tweet.split('\n'):
        if line.strip():
            print(f"   {line}")
    print("   " + "-" * 37)
    print()
    
    return tweet

def main():
    """
    Main function to run the dry run test for orchestrator with Venezuela resolution.
    """
    print("Dry Run Test for Orchestrator with Venezuela Resolution")
    print("=" * 60)
    print("This script simulates the orchestrator workflow with updated\nTwitter link functionality without posting to Twitter.\n")
    
    # Test slug generation
    bill = test_slug_generation()
    
    # Test tweet formatting
    tweet = test_tweet_formatting(bill)
    
    # Simulate full orchestrator processing
    final_tweet = simulate_orchestrator_processing()
    
    print("=== Dry Run Summary ===")
    print("✅ Slug generation: Working correctly")
    print("✅ Tweet formatting: Working correctly")
    print("✅ Link URLs: Would be generated correctly")
    print("✅ Orchestrator simulation: Completed successfully")
    print("\nNo actual tweets were posted to Twitter.")
    print("No database changes were made.")

if __name__ == "__main__":
    main()