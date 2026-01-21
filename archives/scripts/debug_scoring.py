#!/usr/bin/env python3
"""
Debug script to understand why awareness resolutions are scoring 6/10 instead of 2-4.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.processors.teen_impact import score_teen_impact

# Test bills with just their titles to see baseline scoring
test_bills = [
    {
        "title": "A resolution recognizing the seriousness of polycystic ovary syndrome (PCOS) and expressing support for the designation of September 2025 as \"PCOS Awareness Month\"",
        "bill_type": "SRES"
    },
    {
        "title": "A resolution designating September 2025 as \"National Infant Mortality Awareness Month\", raising awareness of infant mortality, and increasing efforts to reduce infant mortality.",
        "bill_type": "SRES"
    }
]

for i, bill in enumerate(test_bills, 1):
    print(f"\n=== Bill {i}: {bill['title']} ===")
    result = score_teen_impact(bill)
    print(f"Score: {result['score']}/10")
    print(f"Raw float: {result['score_float']:.2f}")
    print(f"Is symbolic: {result['is_symbolic_awareness']}")
    print(f"Has action: {result['has_action']}")
    print(f"Teen targeted: {result['teen_targeted']}")
    print(f"Directness multiplier: {result['directness_multiplier']}")
    print(f"Explanation: {result['explanation']}")
    print("Category scores:")
    for cat, score in result['category_scores'].items():
        print(f"  {cat}: {score:.2f}")
    print("Weights:")
    for cat, weight in result['weights'].items():
        print(f"  {cat}: {weight:.3f}")