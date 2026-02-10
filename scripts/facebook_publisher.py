#!/usr/bin/env python3
"""
Standalone Facebook Page publisher for GitHub Actions workflow.

Posts a message to the TeenCivics Facebook Page using the Graph API.
This is a CLI wrapper; the main publishing logic lives in
src/publishers/facebook_publisher.py (used by the orchestrator).

Required environment variables:
  FACEBOOK_PAGE_ID    — Facebook Page ID
  FACEBOOK_PAGE_TOKEN — Permanent Page Access Token

Usage:
    python scripts/facebook_publisher.py "Your message here"
"""

import os
import sys

import requests
from dotenv import load_dotenv

# Load .env if running locally
load_dotenv()

GRAPH_API_VERSION = "v19.0"


def main() -> int:
    # ------------------------------------------------------------------
    # Parse CLI argument
    # ------------------------------------------------------------------
    if len(sys.argv) < 2 or not sys.argv[1].strip():
        print("❌ Usage: python scripts/facebook_publisher.py \"<message>\"", file=sys.stderr)
        return 1

    content = sys.argv[1].strip()

    # ------------------------------------------------------------------
    # Validate environment variables
    # ------------------------------------------------------------------
    page_id = os.getenv("FACEBOOK_PAGE_ID")
    page_token = os.getenv("FACEBOOK_PAGE_TOKEN")

    if not page_id:
        print("❌ Missing environment variable: FACEBOOK_PAGE_ID", file=sys.stderr)
        return 1
    if not page_token:
        print("❌ Missing environment variable: FACEBOOK_PAGE_TOKEN", file=sys.stderr)
        return 1

    # ------------------------------------------------------------------
    # Post to Facebook Page
    # ------------------------------------------------------------------
    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{page_id}/feed"
    params = {
        "message": content,
        "access_token": page_token,
    }

    print(f"📘 Posting to Facebook Page {page_id}...")
    print(f"   Message length: {len(content)} chars")

    try:
        resp = requests.post(url, params=params, timeout=30)
    except requests.RequestException as e:
        print(f"❌ Request failed: {e}", file=sys.stderr)
        return 1

    if resp.status_code != 200:
        print(f"❌ Facebook API error (HTTP {resp.status_code}): {resp.text}", file=sys.stderr)
        return 1

    data = resp.json()
    post_id = data.get("id")

    if post_id:
        post_url = f"https://facebook.com/{page_id}/posts/{post_id}"
        print(f"✅ Facebook post published successfully!")
        print(f"   Post ID: {post_id}")
        print(f"   URL: {post_url}")
        return 0

    print(f"❌ Unexpected response (no post ID): {data}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
