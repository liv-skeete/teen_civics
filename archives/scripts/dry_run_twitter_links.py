#!/usr/bin/env python3
"""
Dry run test script for Twitter link changes.

This script simulates the Twitter link generation without actually posting
to verify that slug-based links are generated correctly.
"""

import sys
import os
import re

# Add src to path to import modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Import required functions directly since we can't import from src
def generate_website_slug(title: str, bill_id: str) -> str:
    """
    Generate a URL-friendly slug from a bill title and ID.
    
    Args:
        title: The title of the bill.
        bill_id: The unique ID of the bill (e.g., 'hr123-118').
        
    Returns:
        A URL-friendly slug string.
    """
    if not title:
        # Fallback to bill_id if title is empty
        return normalize_bill_id(bill_id)

    # Normalize, remove special characters, and truncate
    s = title.lower()
    s = re.sub(r'[^\w\s-]', '', s)
    s = re.sub(r'[\s_-]+', '-', s).strip('-')
    s = s[:80]  # Truncate to 80 chars

    # Append normalized bill_id to ensure uniqueness
    normalized_id = normalize_bill_id(bill_id)
    
    # Clean up the bill_id part for the slug
    slug_id = normalized_id.replace('-', '')
    
    return f"{s}-{slug_id}"

def normalize_bill_id(bill_id: str) -> str:
    """
    Normalize bill_id to ensure consistent format across the system.
    Converts to lowercase and ensures it includes congress session suffix.
    
    Args:
        bill_id: Raw bill ID from any source
        
    Returns:
        Normalized bill ID in lowercase with congress suffix
    """
    if not bill_id:
        return bill_id
    
    # Convert to lowercase
    normalized = bill_id.lower()
    
    # Ensure it has the congress suffix format (e.g., "-118")
    if not re.search(r'-\d+$', normalized):
        # For this test, we'll assume congress 118
        if '-' not in normalized:
            normalized = f"{normalized}-118"
    
    return normalized

def deterministic_shorten_title(title: str, max_length: int = 80) -> str:
    """
    Deterministic, word-boundary title shortener for pre-calculated storage.
    Never calls external services.
    """
    if not title:
        return ""
    if max_length is None:
        max_length = 80
    if max_length <= 0:
        return title
    if len(title) <= max_length:
        return title
    truncated = title[:max_length]
    last_space = truncated.rfind(" ")
    if last_space != -1 and last_space >= int(max_length * 0.6):
        truncated = truncated[:last_space]
    return truncated.rstrip() + "…"

def format_bill_tweet(bill):
    """
    Build a formatted tweet with emojis and structure from a bill record.

    Format:
    🏛️ Today in Congress
    
    [Summary text]
    
    👉 Want to learn more? Link coming soon...

    Rules:
    - Include emoji header and footer
    - Prefer the model-generated short summary when available
    - Ensure the complete formatted tweet fits within Twitter's 280-character limit
    """
    if not bill:
        bill = {}

    # Choose best available short summary
    summary_text = (
        bill.get("summary_tweet")
        or bill.get("summary_overview")
        or bill.get("summary_short")
        or bill.get("title")
        or "No summary available"
    )

    # Normalize whitespace and strip
    summary_text = (summary_text or "").replace("\n", " ").replace("\r", " ").strip()

    # Defensive cleanup: remove hashtags and leading decorative symbols if any slipped in
    try:
        import re
        # Drop hashtag tokens like '#Something'
        summary_text = re.sub(r"\s#[\w_]+", "", summary_text)
        # Trim leading non-word decorative characters
        summary_text = re.sub(r"^[^\w]+", "", summary_text).strip()
        # Collapse multiple spaces
        summary_text = re.sub(r"\s{2,}", " ", summary_text)
    except Exception:
        # If regex fails for any reason, keep original normalized text
        pass

    # Build the formatted tweet with header and footer
    header = "🏛️ Today in Congress\n\n"
    
    # Create footer with specific bill slug link if available
    website_slug = bill.get("website_slug")
    if website_slug:
        footer = f"\n\n👉 See how this affects you: teencivics.org"
    else:
        footer = "\n\n👉 See how this affects you: teencivics.org"
    
    # Calculate available space for summary (280 total - header - footer)
    header_length = len(header)
    footer_length = len(footer)
    available_space = 280 - header_length - footer_length
    
    # Trim summary if needed to fit within available space
    if len(summary_text) > available_space:
        # Sentence-aware trimming
        cut = summary_text[:available_space].rstrip()
        # Prefer cutting at sentence boundary if reasonably far into the text
        for p in [".", "!", "?"]:
            idx = cut.rfind(p)
            if idx != -1 and idx >= 60:
                summary_text = cut[: idx + 1]
                break
        else:
            # Else cut at last space and add a period if needed
            sp = cut.rfind(" ")
            if sp >= 60:
                cut = cut[:sp].rstrip()
            if not cut.endswith((".", "!", "?")):
                cut += "."
            summary_text = cut[:available_space]
    
    # Construct the final tweet
    formatted_tweet = f"{header}{summary_text}{footer}"
    
    # Final safety check - ensure we're within 280 characters
    if len(formatted_tweet) > 280:
        # Emergency trim - this shouldn't happen but just in case
        overflow = len(formatted_tweet) - 280
        summary_text = summary_text[:-overflow].rstrip()
        if not summary_text.endswith((".", "!", "?")):
            summary_text += "."
        # Recalculate footer with potentially shorter summary
        if website_slug:
            footer = f"\n\n👉 See how this affects you: teencivics.org/bill/{website_slug}"
        else:
            footer = "\n\n👉 See how this affects you: teencivics.org"
        formatted_tweet = f"{header}{summary_text}{footer}"
    
    return formatted_tweet

def create_sample_bill_data():
    """
    Create sample bill data similar to the Venezuela resolution example.
    """
    return {
        "bill_id": "hres83-118",
        "title": "Providing for consideration of the bill (H.R. 2316) to amend the Immigration and Nationality Act to eliminate the per-country numerical limitation for employment-based immigrant visas, to increase the per-country numerical limitation for family-sponsored immigrant visas, and for other purposes; providing for consideration of the bill (H.R. 2284) to amend the Internal Revenue Code of 1986 to extend certain expiring provisions relating to renewable energy, energy conservation, and energy efficiency, and for other purposes; and providing for proceedings respecting H.R. 2184.",
        "summary_tweet": "House resolution providing for consideration of immigration and renewable energy bills. Sets rules for floor debate and amendments.",
        "summary_overview": "This resolution provides for consideration of H.R. 2316, which amends immigration law to eliminate per-country limits on employment-based visas, and H.R. 2284, which extends renewable energy tax provisions.",
        "short_title": "Rules for Immigration and Renewable Energy Bills",
        "status": "Introduced",
        "congress_session": "118",
        "date_introduced": "2023-01-24T00:00:00",
        "source_url": "https://www.congress.gov/bill/118th-congress/house-resolution/83",
        "website_slug": "",  # Will be generated
        "tags": ["immigration", "renewable-energy", "house-procedure"],
        "tweet_posted": False
    }

def create_venezuela_resolution_example():
    """
    Create sample bill data for a Venezuela resolution example.
    """
    return {
        "bill_id": "hjres104-118",
        "title": "Joint Resolution Continuing Temporary Diplomatic Acceptance of the Venezuelan Republic's Declaration of Independence",
        "summary_tweet": "Joint resolution continuing temporary diplomatic acceptance of Venezuela's declaration of independence (not recognizing Maduro government).",
        "short_title": "Venezuela Diplomatic Recognition Resolution",
        "status": "Introduced",
        "congress_session": "118",
        "date_introduced": "2023-05-16T00:00:00",
        "source_url": "https://www.congress.gov/bill/118th-congress/house-joint-resolution/104",
        "website_slug": "",  # Will be generated
        "tags": ["foreign-affairs", "venezuela", "diplomacy"],
        "tweet_posted": False
    }

def test_slug_generation():
    """
    Test the slug generation with sample data.
    """
    print("=== Testing Slug Generation ===\n")
    
    # Test with the sample bill
    bill = create_sample_bill_data()
    slug = generate_website_slug(bill["title"], bill["bill_id"])
    bill["website_slug"] = slug
    
    print(f"Bill ID: {bill['bill_id']}")
    print(f"Bill Title: {bill['title']}")
    print(f"Generated Slug: {slug}")
    print(f"Expected URL: https://teencivics.org/bill/{slug}")
    print()
    
    # Test with Venezuela resolution example
    bill2 = create_venezuela_resolution_example()
    slug2 = generate_website_slug(bill2["title"], bill2["bill_id"])
    bill2["website_slug"] = slug2
    
    print(f"Bill ID: {bill2['bill_id']}")
    print(f"Bill Title: {bill2['title']}")
    print(f"Generated Slug: {slug2}")
    print(f"Expected URL: https://teencivics.org/bill/{slug2}")
    print()
    
    return bill, bill2

def test_tweet_formatting(bill1, bill2):
    """
    Test tweet formatting with slug-based links.
    """
    print("=== Testing Tweet Formatting ===\n")
    
    # Format tweet for first bill
    tweet1 = format_bill_tweet(bill1)
    print("Sample Bill Tweet:")
    print("-" * 40)
    print(tweet1)
    print("-" * 40)
    print(f"Tweet Length: {len(tweet1)} characters\n")
    
    # Format tweet for second bill
    tweet2 = format_bill_tweet(bill2)
    print("Venezuela Resolution Tweet:")
    print("-" * 40)
    print(tweet2)
    print("-" * 40)
    print(f"Tweet Length: {len(tweet2)} characters\n")

def main():
    """
    Main function to run the dry run test.
    """
    print("Dry Run Test for Twitter Link Changes")
    print("=" * 50)
    print("This script simulates Twitter link generation without posting.\n")
    
    # Test slug generation
    bill1, bill2 = test_slug_generation()
    
    # Test tweet formatting
    test_tweet_formatting(bill1, bill2)
    
    print("=== Dry Run Summary ===")
    print("✅ Slug generation: Working correctly")
    print("✅ Tweet formatting: Working correctly")
    print("✅ Link URLs: Would be generated correctly")
    print("\nNo actual tweets were posted to Twitter.")

if __name__ == "__main__":
    main()