#!/usr/bin/env python3
"""Download the full text of H.R. 2184 Introduced version"""

import requests
from bs4 import BeautifulSoup

# Try the Introduced version (should have full text)
url = "https://www.congress.gov/119/bills/hr2184/BILLS-119hr2184ih.htm"

print(f"Downloading from: {url}\n")

response = requests.get(url, timeout=30)
content = response.text

print(f"Downloaded {len(content)} characters\n")
print("="*80)
print("FIRST 2000 CHARACTERS:")
print("="*80)
print(content[:2000])
print("\n" + "="*80)
print("MIDDLE SECTION (chars 3000-5000):")
print("="*80)
print(content[3000:5000])
print("\n" + "="*80)
print("LAST 1000 CHARACTERS:")
print("="*80)
print(content[-1000:])

# Try to extract just the text
soup = BeautifulSoup(content, 'html.parser')
text = soup.get_text()

print("\n\n" + "="*80)
print("EXTRACTED TEXT LENGTH:", len(text))
print("="*80)
print("\nFIRST 2000 CHARS OF EXTRACTED TEXT:")
print(text[:2000])