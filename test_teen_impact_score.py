#!/usr/bin/env python3
"""Test that the summarizer generates teen impact scores in the correct format."""

import sys
sys.path.insert(0, 'src')

from database.db import get_all_tweeted_bills
from processors.summarizer import summarize_bill_enhanced
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
        pattern = r'Teen impact score:\s*(\d+)/10'
        match = re.search(pattern, long_summary, re.IGNORECASE)
        
        if match:
            score = match.group(1)
            print(f"✅ Teen impact score found: {score}/10")
            
            # Extract the full line for context
            lines = long_summary.split('\n')
            for line in lines:
                if 'teen impact score' in line.lower():
                    print(f"   Full line: {line.strip()}")
            
            return True
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

if __name__ == "__main__":
    success = test_teen_impact_score()
    sys.exit(0 if success else 1)