#!/usr/bin/env python3
"""
Debug script to see the actual API response for HR.2462
"""
import sys
sys.path.insert(0, 'src')

# Load environment variables first
from src.load_env import load_env
load_env()

from src.database.db import get_bill_by_id
from anthropic import Anthropic
import os
import json

# Get the bill
bill = get_bill_by_id("hr2462-119")
if not bill:
    print("❌ Bill not found")
    sys.exit(1)

print(f"Bill: {bill['title']}")
print(f"Full text length: {len(bill.get('full_text', ''))}")
print()

# Set up Anthropic client
api_key = os.getenv("ANTHROPIC_API_KEY")
if not api_key:
    print("❌ ANTHROPIC_API_KEY not set")
    sys.exit(1)

client = Anthropic(api_key=api_key)

# Create the prompt
system = """You are a legislative analyst creating summaries for teens. Analyze bills and explain their impact in clear, accessible language.

Return ONLY a JSON object with these exact keys:
- "overview": 2-3 sentence summary (100-200 chars)
- "detailed": Comprehensive analysis (300-800 chars) explaining what the bill does and its impact
- "term_dictionary": Array of {"term": "...", "definition": "..."} objects for key legislative terms
- "tweet": Engaging 1-2 sentence summary (max 200 chars)

Requirements:
- Use clear, accessible language appropriate for teens
- Explain real-world impacts and why it matters
- Include relevant legislative terms in term_dictionary
- Be factual and non-partisan
- Return ONLY valid JSON, no markdown formatting"""

bill_text = bill.get('full_text', '')[:10000]  # First 10k chars
user = f"""Analyze this bill and create a summary:

Title: {bill['title']}
Bill ID: {bill['bill_id']}
Latest Action: {bill.get('latest_action', 'N/A')}

Full Text:
{bill_text}

Return your analysis as a JSON object with overview, detailed, term_dictionary, and tweet fields."""

print("=" * 80)
print("MAKING API CALL...")
print("=" * 80)

try:
    response = client.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=4096,
        temperature=0.2,
        system=system,
        messages=[{"role": "user", "content": [{"type": "text", "text": user}]}],
    )
    
    print(f"\nResponse ID: {response.id}")
    print(f"Model: {response.model}")
    print(f"Stop reason: {response.stop_reason}")
    print(f"Usage: {response.usage}")
    print()
    
    # Extract text from response
    text_parts = []
    for block in response.content:
        if hasattr(block, 'text'):
            text_parts.append(block.text)
    
    full_text = "".join(text_parts)
    
    print("=" * 80)
    print("RAW RESPONSE TEXT:")
    print("=" * 80)
    print(full_text)
    print()
    
    # Try to parse as JSON
    print("=" * 80)
    print("PARSED JSON:")
    print("=" * 80)
    try:
        parsed = json.loads(full_text)
        print(json.dumps(parsed, indent=2))
        
        # Check field lengths
        print()
        print("=" * 80)
        print("FIELD ANALYSIS:")
        print("=" * 80)
        for key in ['overview', 'detailed', 'tweet']:
            value = parsed.get(key, '')
            print(f"{key}: {len(value)} chars")
            if value:
                print(f"  Preview: {value[:100]}...")
        
        term_dict = parsed.get('term_dictionary', [])
        print(f"term_dictionary: {len(term_dict)} terms")
        
    except json.JSONDecodeError as e:
        print(f"❌ JSON parsing failed: {e}")
        print(f"First 500 chars: {full_text[:500]}")
    
except Exception as e:
    print(f"❌ API call failed: {e}")
    import traceback
    traceback.print_exc()