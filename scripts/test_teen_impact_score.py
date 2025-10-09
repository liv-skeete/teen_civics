#!/usr/bin/env python3
"""Test that the summarizer generates teen impact scores in the correct format."""

import sys
sys.path.insert(0, 'src')

from database.db import get_all_tweeted_bills
from processors.summarizer import summarize_bill_enhanced
from processors.teen_impact import score_teen_impact
import re

def test_teen_impact_score():
    """Test that teen impact score is generated in correct format."""
    print("Testing teen impact score generation...\n")
    
    # Get one bill to test with
    bills = get_all_tweeted_bills()
    if not bills:
        print("❌ No bills found in database")
        return False
    
    test_bill = bills[0]
    print(f"Testing with bill: {test_bill['bill_id']}")
    print(f"Title: {test_bill['title'][:80]}...\n")
    
    # Generate summary
    print("Generating summary...")
    try:
        summary = summarize_bill_enhanced(test_bill)
        
        if not summary:
            print("❌ No summary generated")
            return False
        
        # The enhanced summarizer returns 'detailed' not 'long_summary'
        long_summary = summary.get('detailed') or summary.get('long_summary', '')
        
        if not long_summary:
            print("❌ No detailed summary in response")
            print(f"Available keys: {list(summary.keys())}")
            return False
        print(f"Summary generated ({len(long_summary)} chars)\n")
        
        # Check for teen impact score in the correct format
        # Pattern: "Teen impact score: X/10" where X is 1-10
        pattern = r'Teen impact score:\s*(\d{1,2})/10'
        match = re.search(pattern, long_summary, re.IGNORECASE)
        
        if match:
            score = int(match.group(1))
            if 0 <= score <= 10:
                print(f"✅ Teen impact score found and is valid: {score}/10")
        
                # Extract the full line for context
                lines = long_summary.split('\n')
                for line in lines:
                    if 'teen impact score' in line.lower():
                        print(f"   Full line: {line.strip()}")
                return True
            else:
                print(f"❌ Teen impact score {score}/10 is out of range (0-10)")
                return False
        else:
            print("❌ Teen impact score NOT found in correct format")
            print("\nSearching for 'teen impact' in summary:")
            lines = long_summary.split('\n')
            found_teen_mention = False
            for line in lines:
                if 'teen' in line.lower():
                    print(f"   {line.strip()}")
                    found_teen_mention = True
            
            if not found_teen_mention:
                print("   (No mention of 'teen' found at all)")
            
            return False
            
    except Exception as e:
        print(f"❌ Error generating summary: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_awareness_resolution_scoring():
    """
    Awareness-only resolution with no programmatic actions should score in 2–4 range.
    """
    bill = {
        "bill_id": "sres999-119",
        "title": "Designating XYZ Awareness Month",
        "status": "introduced",
        "summary_detailed": (
            "This simple resolution recognizes and celebrates XYZ Awareness Month, "
            "calling for raising awareness and observing the month. It commends "
            "organizations and expresses support for public education efforts."
        ),
        "latest_action": "Introduced in Senate",
        "bill_type": "SRES",
    }
    result = score_teen_impact(bill)
    score = int(result.get("score", -1))
    print(f"Awareness-only result: {score}/10 -> {result.get('explanation')}")
    return 2 <= score <= 4


def test_direct_school_policy_scoring():
    """
    Direct student/school-targeted policy with mandates should score in 8–10 range.
    """
    bill = {
        "bill_id": "s1234-119",
        "title": "A bill to require schools to provide access to mental health counselors",
        "status": "introduced",
        "summary_detailed": (
            "The bill requires K-12 schools to establish school mental health counseling programs, "
            "mandates minimum counselor-to-student ratios, and directs the Department of Education "
            "to issue guidance. States shall implement the requirements within 2 years."
        ),
        "latest_action": "Referred to committee",
        "bill_type": "S",
    }
    result = score_teen_impact(bill)
    score = int(result.get("score", -1))
    print(f"Direct school policy result: {score}/10 -> {result.get('explanation')}")
    return 8 <= score <= 10


def test_general_public_health_indirect_scoring():
    """
    General public-health funding with indirect teen pathway (families/dependents, workforce)
    should land 5–7 range.
    """
    bill = {
        "bill_id": "hr5678-119",
        "title": "Public Health Funding and Workforce Development Act",
        "status": "introduced",
        "summary_detailed": (
            "The bill authorizes appropriations and grants for community public health programs, "
            "establishes apprenticeship programs to expand the public health workforce, supports "
            "families and dependents through community clinic access, directs HHS to coordinate "
            "state efforts, and includes provisions on public health data privacy and reporting. "
            "It also funds environmental health initiatives to improve air and water quality."
        ),
        "latest_action": "Referred to committee",
        "bill_type": "HR",
    }
    result = score_teen_impact(bill)
    score = int(result.get("score", -1))
    print(f"General public-health (indirect) result: {score}/10 -> {result.get('explanation')}")
    return 5 <= score <= 7


if __name__ == "__main__":
    ok = True
    print("Running teen impact score format test...")
    ok = test_teen_impact_score() and ok

    print("\nRunning deterministic scoring tests...")
    try:
        a_ok = test_awareness_resolution_scoring()
        print(f"Awareness-only test -> {'PASS' if a_ok else 'FAIL'}")
        ok = ok and a_ok
    except Exception as e:
        print(f"Awareness-only test error: {e}")
        ok = False

    try:
        d_ok = test_direct_school_policy_scoring()
        print(f"Direct school policy test -> {'PASS' if d_ok else 'FAIL'}")
        ok = ok and d_ok
    except Exception as e:
        print(f"Direct school policy test error: {e}")
        ok = False

    try:
        g_ok = test_general_public_health_indirect_scoring()
        print(f"General public health (indirect) test -> {'PASS' if g_ok else 'FAIL'}")
        ok = ok and g_ok
    except Exception as e:
        print(f"General public-health test error: {e}")
        ok = False

    sys.exit(0 if ok else 1)