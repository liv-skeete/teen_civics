"""
Twitter/X publisher for posting bill updates.
This module provides functionality to post formatted bill information to Twitter/X.
"""

import os
import re
import logging
import hashlib
from typing import Dict, Optional

import tweepy
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables
logger.info("Loading environment variables...")
load_dotenv()
logger.info("Environment variables loaded")

# Twitter API credentials
TWITTER_API_KEY = os.getenv('TWITTER_API_KEY')
TWITTER_API_SECRET = os.getenv('TWITTER_API_SECRET')
TWITTER_ACCESS_TOKEN = os.getenv('TWITTER_ACCESS_TOKEN')
TWITTER_ACCESS_SECRET = os.getenv('TWITTER_ACCESS_SECRET')
TWITTER_BEARER_TOKEN = os.getenv('TWITTER_BEARER_TOKEN')

# Avoid logging any credential values in production
logger.info("Twitter API credentials loaded; verifying presence only")
# Check if all required credentials are present
required_creds = [TWITTER_API_KEY, TWITTER_API_SECRET, TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_SECRET]
if all(required_creds):
    logger.info("All required API credentials are present")
else:
    missing = [name for name, value in zip(['API_KEY', 'API_SECRET', 'ACCESS_TOKEN', 'ACCESS_SECRET'], required_creds) if not value]
    logger.error(f"Missing required credentials: {missing}")


# Initialize Tweepy API (None if credentials missing)
# Debug helper to avoid leaking full secrets
def _mask(v: Optional[str]) -> str:
    if not v:
        return "missing"
    return f"{v[:4]}***{v[-4:]}" if len(v) >= 8 else "set"






# Initialize both v1.1 and v2 API clients
api_v1 = None
client_v2 = None

logger.info("Initializing Twitter API clients...")

if all([TWITTER_API_KEY, TWITTER_API_SECRET, TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_SECRET]):
    try:
        # OAuth 1.0a for v1.1 API
        logger.info("Creating OAuthHandler for v1.1 API...")
        auth_v1 = tweepy.OAuthHandler(TWITTER_API_KEY, TWITTER_API_SECRET)
        logger.info("Setting access token for v1.1 API...")
        auth_v1.set_access_token(TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_SECRET)
        logger.info("Authenticating with Twitter API v1.1...")
        api_v1 = tweepy.API(auth_v1, wait_on_rate_limit=True)
        logger.info("Authenticated with Twitter API v1.1 successfully.")
        
        # Verify authentication by getting user details
        try:
            user = api_v1.verify_credentials()
            logger.info(f"Successfully authenticated as: {user.screen_name}")
        except Exception as e:
            logger.warning(f"Authentication verification failed: {e}")
        
        # Try to initialize v2 client if Bearer token is available
        if TWITTER_BEARER_TOKEN:
            try:
                logger.info("Initializing Twitter API v2 client...")
                client_v2 = tweepy.Client(
                    bearer_token=TWITTER_BEARER_TOKEN,
                    consumer_key=TWITTER_API_KEY,
                    consumer_secret=TWITTER_API_SECRET,
                    access_token=TWITTER_ACCESS_TOKEN,
                    access_token_secret=TWITTER_ACCESS_SECRET
                )
                logger.info("Twitter API v2 client initialized successfully")
            except Exception as e:
                logger.warning(f"Failed to initialize Twitter API v2 client: {e}")
        else:
            logger.warning("TWITTER_BEARER_TOKEN not found - v2 API unavailable")
            
    except Exception as e:
        logger.error(f"Failed to initialize Twitter API: {e}")
        api_v1 = None
        client_v2 = None
else:
    logger.warning("Twitter API credentials not found in environment variables")

logger.info(f"API v1 initialized: {api_v1 is not None}")
logger.info(f"API v2 initialized: {client_v2 is not None}")

def is_twitter_configured() -> bool:
    """Check if all required Twitter API credentials are present and non-empty."""
    required = [TWITTER_API_KEY, TWITTER_API_SECRET, TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_SECRET]
    configured = all(required)
    if not configured:
        logger.warning("Twitter: Missing one or more required credentials (API_KEY, API_SECRET, ACCESS_TOKEN, ACCESS_SECRET)")
    return configured


def post_tweet(text: str) -> tuple[bool, str | None]:
    """
    Post a tweet with the given text.

    Returns:
        (success, tweet_url) where tweet_url can be a generic web URL if screen name is unknown.
    """
    if api_v1 is None and client_v2 is None:
        logger.error("Twitter API not initialized - cannot post tweet")
        return False, None

    if not text or len(text.strip()) == 0:
        logger.error("Cannot post empty tweet")
        return False, None

    # Calculate effective length accounting for t.co URL shortening
    # Twitter shortens all URLs to 23 characters (t.co links)
    url_pattern = r'https?://[^\s]+'
    urls = re.findall(url_pattern, text)
    effective_length = len(text)
    for url in urls:
        # Each URL gets shortened to 23 chars
        effective_length = effective_length - len(url) + 23
    
    if effective_length > 280:
        logger.error(f"Tweet text exceeds 280 characters ({effective_length} effective chars, {len(text)} raw chars)")
        return False, None

    logger.info(f"Tweet length check: {effective_length} effective chars (raw: {len(text)} chars)")

    # DIAGNOSTIC: Log full tweet content hash for duplicate detection
    import hashlib
    tweet_hash = hashlib.md5(text.encode()).hexdigest()
    logger.info(f"🔍 DIAGNOSTIC: Attempting to post tweet with hash: {tweet_hash}")
    logger.info(f"🔍 DIAGNOSTIC: Full tweet content: {text}")

    # Prefer v2 API first (generally better supported)
    if client_v2:
        try:
            logger.info(f"Attempting to post tweet via v2 API: {text[:50]}...")
            response = client_v2.create_tweet(text=text)
            if response and getattr(response, "data", None):
                # Tweepy v2 returns response.data as a dict-like structure
                tweet_id = response.data.get("id") if isinstance(response.data, dict) else response.data["id"]
                tweet_url = f"https://twitter.com/i/web/status/{tweet_id}"
                logger.info(f"Tweet posted successfully via v2 API: {tweet_url}")
                return True, tweet_url
            else:
                logger.error("v2 API response missing tweet data")
                # Consider this a failure to allow fallback to v1
        except tweepy.Forbidden as e:
            error_msg = str(e)
            logger.error(f"v2 API failed with Forbidden error (likely permissions): {e}")
            logger.error("This may indicate limited API access. Check your app permissions.")
            # Don't fallback to v1 for permission errors
            return False, None
        except tweepy.TweepyException as e:
            error_msg = str(e)
            logger.error(f"v2 API failed: {e}")
            # DIAGNOSTIC: Check if this is a duplicate content error
            if "duplicate" in error_msg.lower():
                logger.error(f"🔍 DIAGNOSTIC: DUPLICATE CONTENT ERROR detected in v2 API")
                logger.error(f"🔍 DIAGNOSTIC: Tweet hash that was rejected: {tweet_hash}")
                logger.error(f"🔍 DIAGNOSTIC: This tweet content was already posted to Twitter")
                # Return a special indicator that this is a duplicate
                return False, "DUPLICATE_CONTENT"
        except Exception as e:
            logger.error(f"Unexpected error with v2 API: {e}")

    # Fallback to v1.1 API if v2 failed or unavailable
    if api_v1:
        try:
            logger.info(f"Attempting to post tweet via v1.1 API: {text[:50]}...")
            tweet = api_v1.update_status(status=text)
            tweet_url = f"https://twitter.com/i/web/status/{tweet.id}"
            logger.info(f"Tweet posted successfully via v1.1 API: {tweet_url}")
            return True, tweet_url
        except tweepy.Forbidden as e:
            error_msg = str(e)
            logger.error(f"v1.1 API failed with Forbidden error (likely permissions): {e}")
            logger.error("This may indicate limited API access. Check your app permissions.")
            # This is a critical error, don't continue
            return False, None
        except tweepy.TweepyException as e:
            error_msg = str(e)
            logger.warning(f"v1.1 API failed: {e}")
            # DIAGNOSTIC: Check if this is a duplicate content error
            if "duplicate" in error_msg.lower():
                logger.error(f"🔍 DIAGNOSTIC: DUPLICATE CONTENT ERROR detected in v1.1 API")
                logger.error(f"🔍 DIAGNOSTIC: Tweet hash that was rejected: {tweet_hash}")
                logger.error(f"🔍 DIAGNOSTIC: This tweet content was already posted to Twitter")
                # Return a special indicator that this is a duplicate
                return False, "DUPLICATE_CONTENT"
        except Exception as e:
            logger.error(f"Unexpected error with v1.1 API: {e}")

    logger.error("All Twitter API posting methods failed")
    return False, None


def format_bill_tweet(bill: Dict) -> str:
    """
    Build a formatted tweet with emojis and structure from a bill record.

    Format:
    🏛️ Today in Congress
    
    [Summary text]
    
    👉 Want to learn more? Link coming soon...

    Rules:
    - Include emoji header and footer
    - Prefer the model-generated short summary when available
    - Ensure the complete formatted tweet fits within Twitter's 280-character limit
    """
    if not bill:
        bill = {}

    # Choose best available short summary; never emit placeholder text
    summary_text = (
        bill.get("summary_tweet")
        or bill.get("summary_overview")
        or bill.get("summary_short")
        or bill.get("title")
    )
    
    # Check if summary contains placeholder text
    if summary_text and "no summary available" in summary_text.lower():
        summary_text = None
    
    # If still empty or contains placeholder, synthesize a safe, informative fallback from available fields
    if not summary_text:
        status_raw = (bill.get("normalized_status") or bill.get("status") or "").strip()
        status_disp = status_raw.replace("_", " ").title() if status_raw else "Introduced"
        title = (bill.get("title") or bill.get("short_title") or bill.get("bill_id") or "").strip()
        base = title if title else (bill.get("bill_id") or "This bill")
        summary_text = f"{base}. Status: {status_disp}."

    # Normalize whitespace and strip
    summary_text = (summary_text or "").replace("\n", " ").replace("\r", " ").strip()

    # Defensive cleanup: remove hashtags and leading decorative symbols if any slipped in
    try:
        import re
        # Drop hashtag tokens like '#Something'
        summary_text = re.sub(r"\s#[\w_]+", "", summary_text)
        # Trim leading non-word decorative characters
        summary_text = re.sub(r"^[^\w]+", "", summary_text).strip()
        # Collapse multiple spaces
        summary_text = re.sub(r"\s{2,}", " ", summary_text)
    except Exception:
        # If regex fails for any reason, keep original normalized text
        pass

    # Build the formatted tweet with header and footer
    header = "🏛️ Today in Congress\n\n"
    
    # Create footer with specific bill slug link if available
    website_slug = bill.get("website_slug")
    if website_slug:
        link = f"https://teencivics.org/bill/{website_slug}"
    else:
        link = "https://teencivics.org"

    footer_text = "\n\n👉 See how this affects you: "
    
    # Twitter shortens https links to 23 characters
    tco_link_length = 23

    # Calculate available space for summary
    # The footer_text + link will be counted where the link counts as tco_link_length
    header_length = len(header)
    footer_with_placeholder_length = len(footer_text) + tco_link_length
    available_space = 280 - header_length - footer_with_placeholder_length
    
    # Ensure we have minimum 50 chars for summary
    if available_space < 50:
        logger.warning(f"Very limited space for summary: {available_space} chars")
        available_space = max(50, available_space)
    
    # Trim summary if needed to fit within available space
    if len(summary_text) > available_space:
        logger.info(f"Trimming summary from {len(summary_text)} to {available_space} chars")
        # Sentence-aware trimming
        cut = summary_text[:available_space].rstrip()
        # Prefer cutting at sentence boundary if reasonably far into the text
        for p in [".", "!", "?"]:
            idx = cut.rfind(p)
            if idx != -1 and idx >= 40:  # Lowered threshold for shorter content
                summary_text = cut[: idx + 1]
                break
        else:
            # Else cut at last space and add ellipsis
            sp = cut.rfind(" ")
            if sp >= 40:
                cut = cut[:sp].rstrip()
            if not cut.endswith((".", "!", "?")):
                cut += "..."
            summary_text = cut[:available_space]
    
    # Construct the final tweet
    footer = f"{footer_text}{link}"
    formatted_tweet = f"{header}{summary_text}{footer}"
    
    # Final safety check - ensure we're within 280 characters
    # Properly calculate: header + summary + footer_text + tco_link_length
    final_length = len(header) + len(summary_text) + len(footer_text) + tco_link_length
    
    if final_length > 280:
        logger.warning(f"Tweet still too long after trimming: {final_length} chars. Emergency trim required.")
        # Emergency trim - this shouldn't happen but just in case
        overflow = final_length - 280
        # Add safety margin
        overflow += 5
        
        if len(summary_text) > overflow:
            summary_text = summary_text[:-overflow].rstrip()
            # Ensure the text doesn't end with an incomplete word
            if " " in summary_text:
                summary_text = summary_text.rsplit(' ', 1)[0].rstrip()
            if not summary_text.endswith((".", "!", "?")):
                summary_text += "..."
            elif summary_text.endswith("."):
                summary_text = summary_text[:-1] + "..."
        else:
            # Summary is too short even for overflow - use minimal version
            summary_text = summary_text[:50].rsplit(' ', 1)[0] + "..."
        
        # Rebuild tweet with trimmed summary
        footer = f"{footer_text}{link}"
        formatted_tweet = f"{header}{summary_text}{footer}"
        logger.info(f"After emergency trim: {len(header) + len(summary_text) + len(footer_text) + tco_link_length} chars")
    
    # Log the effective length (as Twitter will see it after t.co shortening)
    effective_length = len(header) + len(summary_text) + len(footer_text) + tco_link_length
    logger.info(f"📝 Tweet effective length (with t.co): {effective_length} chars, actual string length: {len(formatted_tweet)} chars")
    
    return formatted_tweet


def validate_tweet_content(text: str, bill: dict) -> tuple[bool, str]:
    """
    Validate tweet content quality to prevent placeholder/low-quality posts.
    Returns (is_valid, reason) where reason explains the failure.
    Rules:
      - Forbid placeholder phrases (e.g., "No summary available", "coming soon", "TBD").
      - Require a valid bill link with website_slug.
      - Require a minimum informative body length after removing the header and footer.
    """
    try:
        t = (text or "").strip()
        if not t:
            return False, "Empty tweet text"
        low = t.lower()

        forbidden = [
            "no summary available",
            "link coming soon",
            "coming soon",
            "tbd",
            "to be determined",
        ]
        for phrase in forbidden:
            if phrase in low:
                return False, f"Contains placeholder phrase '{phrase}'"

        # Ensure the exact bill link is present
        slug = (bill.get("website_slug") or "").strip() if isinstance(bill, dict) else ""
        if slug:
            expected = f"teencivics.org/bill/{slug}"
            if expected not in t:
                return False, "Missing or incorrect bill link"
        else:
            return False, "Missing website_slug"

        # Measure body length (text before footer arrow and without header)
        try:
            body_part = t.split("👉")[0]
            body_part = body_part.replace("🏛️ Today in Congress", "").strip()
        except Exception:
            body_part = t
        if len(body_part) < 50:
            return False, f"Summary too short ({len(body_part)} chars)"

        return True, "ok"
    except Exception as e:
        # Fail closed on validator errors
        return False, f"Validator exception: {e}"


if __name__ == "__main__":
    logger.info("Starting Twitter publisher main execution...")
    
    # Import and use congress_fetcher
    try:
        logger.info("Attempting to import congress_fetcher...")
        from src.fetchers.congress_fetcher import get_recent_bills
        logger.info("Congress fetcher imported successfully")
        
        # Fetch the first bill
        logger.info("Fetching recent bills...")
        bills = get_recent_bills(limit=1)
        logger.info(f"Received {len(bills) if bills else 0} bills")
        
        if not bills:
            logger.error("No bills found to post")
            exit(1)
        
        bill = bills[0]
        logger.info(f"Processing bill: {bill.get('bill_id')}")
        
        # Format the bill into a tweet
        tweet_text = format_bill_tweet(bill)
        logger.info(f"Formatted tweet: {tweet_text}")
        
        # Post the tweet
        logger.info("Attempting to post tweet...")
        success, tweet_url = post_tweet(tweet_text)
        
        if success:
            if tweet_url:
                print(f"✅ Tweet posted successfully! {tweet_url}")
            else:
                print("✅ Tweet posted successfully! (URL not available)")
        else:
            print("❌ Failed to post tweet")
            exit(1)
            
    except ImportError as e:
        logger.error(f"Could not import congress_fetcher module: {e}")
        print("❌ Congress fetcher module not available")
        exit(1)
    except Exception as e:
        logger.error(f"Error in main execution: {e}")
        # Fallback: print a demo tweet so formatting can be reviewed without API keys
        demo = {
            "summary_tweet": (
                "DEMO: A bipartisan bill was introduced to expand access to computer science education "
                "and fund teacher training across public schools."
            )
        }
        demo_tweet = format_bill_tweet(demo)
        print("Demo tweet preview (no post attempted):")
        print(demo_tweet)
        # Exit successfully so local runs/CI can still validate format
        exit(0)