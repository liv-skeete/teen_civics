#!/usr/bin/env python3
"""
Test script to verify the enhanced summarizer with teen-focused sections.
"""

import json
from src.processors.summarizer import summarize_bill_enhanced

# Test bill data - a student loan bill to test high teen impact scoring
test_bill = {
    "bill_id": "hr1234-118",
    "title": "Student Loan Forgiveness and College Affordability Act",
    "bill_type": "HR",
    "bill_number": "1234",
    "congress": "118",
    "introduced_date": "2024-01-15",
    "latest_action": "Referred to the Committee on Education and Labor",
    "status": "introduced",
    "sponsor": "Rep. Smith (D-CA)",
}

print("Testing enhanced summarizer with teen-focused sections...")
print("=" * 80)
print(f"\nTest Bill: {test_bill['title']}")
print(f"Bill Type: {test_bill['bill_type']}.{test_bill['bill_number']}")
print("\nGenerating summary...\n")

try:
    result = summarize_bill_enhanced(test_bill)
    
    print("✅ Summary generated successfully!")
    print("=" * 80)
    
    print("\n📱 TWEET (with attention hook):")
    print("-" * 80)
    print(result['tweet'])
    print(f"Length: {len(result['tweet'])} characters")
    
    print("\n📝 OVERVIEW:")
    print("-" * 80)
    print(result['overview'])
    
    print("\n📋 DETAILED SUMMARY:")
    print("-" * 80)
    print(result['detailed'])
    
    print("\n📚 TERM DICTIONARY:")
    print("-" * 80)
    try:
        terms = json.loads(result['term_dictionary'])
        if terms:
            for term in terms:
                print(f"  • {term.get('term', 'N/A')}: {term.get('definition', 'N/A')}")
        else:
            print("  (No terms defined)")
    except:
        print(f"  {result['term_dictionary']}")
    
    print("\n" + "=" * 80)
    print("\n✅ VERIFICATION CHECKLIST:")
    print("-" * 80)
    
    # Check for required sections in detailed summary
    required_sections = [
        "🔎 Overview",
        "👥 Who does this affect?",
        "🔑 Key Provisions",
        "🛠️ Policy Changes",
        "⚖️ Policy Riders or Key Rules/Changes",
        "📌 Procedural/Administrative Notes",
        "👉 In short",
        "💡 Why should I care?"
    ]
    
    for section in required_sections:
        if section in result['detailed']:
            print(f"  ✅ {section}")
        else:
            print(f"  ❌ MISSING: {section}")
    
    # Check for teen impact score
    if "Teen impact score:" in result['detailed']:
        print(f"  ✅ Teen impact score present")
        # Extract the score
        import re
        score_match = re.search(r'Teen impact score: (\d+)/10', result['detailed'])
        if score_match:
            score = int(score_match.group(1))
            print(f"     Score: {score}/10")
            if score > 5:
                if "Teen-specific impact:" in result['detailed']:
                    print(f"  ✅ Teen-specific impact explanation present (score > 5)")
                else:
                    print(f"  ⚠️  Teen-specific impact explanation missing (score > 5)")
    else:
        print(f"  ❌ Teen impact score missing")
    
    # Check tweet has attention hook
    tweet_lower = result['tweet'].lower()
    has_hook = any([
        tweet_lower.startswith(('new bill', 'congress', 'bill would', 'bill could')),
        any(char.isdigit() for char in result['tweet'][:50]),  # Number in first 50 chars
        '?' in result['tweet'][:100],  # Question in first 100 chars
    ])
    
    if has_hook:
        print(f"  ✅ Tweet appears to have attention hook")
    else:
        print(f"  ⚠️  Tweet may lack clear attention hook")
    
    print("\n" + "=" * 80)
    print("✅ Test completed successfully!")
    
except Exception as e:
    print(f"\n❌ Error during summarization: {e}")
    import traceback
    traceback.print_exc()