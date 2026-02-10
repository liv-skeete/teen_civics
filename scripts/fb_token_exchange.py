#!/usr/bin/env python3
"""
Facebook Token Exchange Script — One-time manual tool.

Derives a permanent (non-expiring) Page Access Token from a short-lived
user token obtained via the Facebook Graph API Explorer.

Steps:
  1. Exchange short-lived user token → long-lived user token
  2. Use long-lived user token → fetch page tokens
  3. Filter for the target page and print the permanent page token

Required environment variables:
  FB_APP_ID             — Facebook App ID
  FB_APP_SECRET         — Facebook App Secret
  FB_SHORT_LIVED_TOKEN  — Temporary user token from Graph API Explorer

Usage:
    python scripts/fb_token_exchange.py
"""

import os
import sys

import requests
from dotenv import load_dotenv

# Load .env if running locally
load_dotenv()

GRAPH_API_VERSION = "v19.0"
TARGET_PAGE_ID = "997688916756765"


def main() -> int:
    # ------------------------------------------------------------------
    # Validate environment variables
    # ------------------------------------------------------------------
    app_id = os.getenv("FB_APP_ID")
    app_secret = os.getenv("FB_APP_SECRET")
    short_lived_token = os.getenv("FB_SHORT_LIVED_TOKEN")

    missing = []
    if not app_id:
        missing.append("FB_APP_ID")
    if not app_secret:
        missing.append("FB_APP_SECRET")
    if not short_lived_token:
        missing.append("FB_SHORT_LIVED_TOKEN")

    if missing:
        print(f"❌ Missing required environment variables: {', '.join(missing)}", file=sys.stderr)
        return 1

    # ------------------------------------------------------------------
    # Step 1: Exchange short-lived token → long-lived user token
    # ------------------------------------------------------------------
    print("Step 1: Exchanging short-lived token for long-lived user token...")

    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/oauth/access_token"
    params = {
        "grant_type": "fb_exchange_token",
        "client_id": app_id,
        "client_secret": app_secret,
        "fb_exchange_token": short_lived_token,
    }

    resp = requests.get(url, params=params, timeout=30)
    if resp.status_code != 200:
        print(f"❌ Token exchange failed (HTTP {resp.status_code}): {resp.text}", file=sys.stderr)
        return 1

    data = resp.json()
    long_lived_token = data.get("access_token")
    if not long_lived_token:
        print(f"❌ No access_token in response: {data}", file=sys.stderr)
        return 1

    print(f"✅ Long-lived user token obtained (expires_in: {data.get('expires_in', 'N/A')}s)")

    # ------------------------------------------------------------------
    # Step 2: Fetch page tokens using the long-lived user token
    # ------------------------------------------------------------------
    print("Step 2: Fetching page tokens...")

    pages_url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/me/accounts"
    pages_params = {"access_token": long_lived_token}

    resp = requests.get(pages_url, params=pages_params, timeout=30)
    if resp.status_code != 200:
        print(f"❌ Failed to fetch page tokens (HTTP {resp.status_code}): {resp.text}", file=sys.stderr)
        return 1

    pages_data = resp.json()
    pages = pages_data.get("data", [])

    if not pages:
        print("❌ No pages found for this user. Ensure the token has pages_manage_posts permission.", file=sys.stderr)
        return 1

    print(f"✅ Found {len(pages)} page(s)")

    # ------------------------------------------------------------------
    # Step 3: Filter for the target page
    # ------------------------------------------------------------------
    print(f"Step 3: Looking for page ID {TARGET_PAGE_ID}...")

    page_token = None
    for page in pages:
        if page.get("id") == TARGET_PAGE_ID:
            page_token = page.get("access_token")
            print(f"✅ Found page: {page.get('name', 'Unknown')} (id: {page.get('id')})")
            break

    if not page_token:
        print(f"❌ Page ID {TARGET_PAGE_ID} not found in results.", file=sys.stderr)
        print("Available pages:", file=sys.stderr)
        for p in pages:
            print(f"  - {p.get('name', 'Unknown')} (id: {p.get('id')})", file=sys.stderr)
        return 1

    # ------------------------------------------------------------------
    # Step 4: Print the permanent page token
    # ------------------------------------------------------------------
    print("Step 4: Permanent page access token retrieved successfully!")
    print("")
    print("=" * 60)
    print("FACEBOOK_PAGE_TOKEN (permanent, non-expiring):")
    print(page_token)
    print("=" * 60)
    print("")
    print("Set this as your FACEBOOK_PAGE_TOKEN secret in GitHub and Railway.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
