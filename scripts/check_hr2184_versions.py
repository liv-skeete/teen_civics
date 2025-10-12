#!/usr/bin/env python3
"""Check what text versions are available for H.R. 2184"""

import os
import sys
import requests
from dotenv import load_dotenv

# Load environment
load_dotenv()

api_key = os.getenv('CONGRESS_API_KEY')

# Get text versions
url = f'https://api.congress.gov/v3/bill/119/hr/2184/text?format=json&api_key={api_key}'

print(f"Fetching text versions from: {url}\n")

response = requests.get(url, timeout=30)
data = response.json()

text_versions = data.get('textVersions', [])

print(f"Found {len(text_versions)} text version(s):\n")

for i, version in enumerate(text_versions, 1):
    print(f"\n{'='*80}")
    print(f"VERSION {i}:")
    print(f"{'='*80}")
    print(f"Type: {version.get('type')}")
    print(f"Date: {version.get('date')}")
    
    formats = version.get('formats', [])
    print(f"\nAvailable formats ({len(formats)}):")
    for fmt in formats:
        print(f"  - {fmt.get('type')}: {fmt.get('url')}")