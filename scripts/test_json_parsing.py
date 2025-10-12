#!/usr/bin/env python3
"""
Test JSON parsing directly with the actual response from Claude.
"""

import json
import re

# This is the actual response from Claude (from the debug output)
raw_response = '''
{
"overview": "Senate Resolution 428 formally recognizes Hispanic Heritage Month and acknowledges the cultural heritage and significant contributions of Latino Americans to the United States. The resolution passed the Senate by unanimous consent.",

"detailed": "🔎 Overview
- Senate Resolution 428 establishes formal Senate recognition of Hispanic Heritage Month and Latino contributions to American society

🔑 Key Provisions
- Formally recognizes Hispanic Heritage Month at the federal level
- Celebrates Latino cultural heritage in the United States
- Acknowledges the historic and ongoing contributions of Latino Americans
- Provides official Senate commemoration of Latino achievement and impact

📌 Procedural/Administrative Notes
- Introduced in the Senate on September 30, 2025
- Passed by Unanimous Consent
- No amendments were made to the original resolution
- Represents a formal statement of the Senate's position

👉 In short
- Ceremonial resolution marking Hispanic Heritage Month
- Passed Senate with full bipartisan support
- Represents formal recognition of Latino cultural impact and contributions",

"term_dictionary": [
{"term": "Unanimous Consent", "definition": "A Senate procedure where a resolution passes without objection or formal vote"},
{"term": "Senate Resolution", "definition": "A formal statement of Senate position that does not require House approval or Presidential signature"},
{"term": "Hispanic Heritage Month", "definition": "Annual celebration from September 15 to October 15 recognizing Hispanic American culture and contributions"}
],

"tweet": "Senate unanimously passes resolution recognizing Hispanic Heritage Month and celebrating Latino contributions to the United States."
}
'''

print("Testing JSON parsing...")
print("="*60)

# Test 1: Direct JSON parse
try:
    parsed = json.loads(raw_response)
    print("✓ Direct JSON parse successful!")
    print(f"  Keys: {list(parsed.keys())}")
    for key, value in parsed.items():
        if isinstance(value, str):
            print(f"  {key}: {len(value)} chars")
        elif isinstance(value, list):
            print(f"  {key}: {len(value)} items")
except Exception as e:
    print(f"✗ Direct JSON parse failed: {e}")
    
    # Test 2: Clean and retry
    cleaned = raw_response.strip()
    # Remove any potential BOM or hidden characters
    cleaned = cleaned.encode('utf-8', 'ignore').decode('utf-8')
    
    try:
        parsed = json.loads(cleaned)
        print("✓ Cleaned JSON parse successful!")
        print(f"  Keys: {list(parsed.keys())}")
    except Exception as e2:
        print(f"✗ Cleaned JSON parse also failed: {e2}")
        
        # Test 3: Manual extraction with regex
        print("\nTrying regex extraction...")
        
        # Extract overview
        overview_match = re.search(r'"overview"\s*:\s*"([^"]*)"', raw_response)
        if overview_match:
            print(f"✓ Found overview: {len(overview_match.group(1))} chars")
        
        # Extract detailed (handle multiline)
        detailed_match = re.search(r'"detailed"\s*:\s*"(.*?)",\s*\n\s*"', raw_response, re.DOTALL)
        if detailed_match:
            print(f"✓ Found detailed: {len(detailed_match.group(1))} chars")
        
        # Extract term_dictionary
        term_dict_match = re.search(r'"term_dictionary"\s*:\s*(\[.*?\])', raw_response, re.DOTALL)
        if term_dict_match:
            print(f"✓ Found term_dictionary: {len(term_dict_match.group(1))} chars")
        
        # Extract tweet
        tweet_match = re.search(r'"tweet"\s*:\s*"([^"]*)"', raw_response)
        if tweet_match:
            print(f"✓ Found tweet: {len(tweet_match.group(1))} chars")