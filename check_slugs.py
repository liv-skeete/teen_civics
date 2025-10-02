#!/usr/bin/env python3
"""Check website_slug values in database"""

import os
from dotenv import load_dotenv
load_dotenv()

from src.database.db import get_all_tweeted_bills

bills = get_all_tweeted_bills()
if bills:
    print(f"Found {len(bills)} bills\n")
    for i, bill in enumerate(bills[:5], 1):
        print(f"{i}. Bill ID: {bill.get('bill_id')}")
        print(f"   Website Slug: '{bill.get('website_slug')}'")
        print(f"   Expected URL: /bill/{bill.get('website_slug')}")
        print()
else:
    print("No bills found")