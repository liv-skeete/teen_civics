"""
Twitter/X publisher for posting bill updates.
This module provides functionality to post formatted bill information to Twitter/X.
"""

import os
import logging
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

# Debug: Log masked API keys to confirm they are loaded
def mask_key(key):
    if key and len(key) > 8:
        return f"{key[:4]}...{key[-4:]}"
    return "not set" if not key else "set"

logger.info("Checking API key availability:")
logger.info(f"TWITTER_API_KEY: {mask_key(TWITTER_API_KEY)}")
logger.info(f"TWITTER_API_SECRET: {mask_key(TWITTER_API_SECRET)}")
logger.info(f"TWITTER_ACCESS_TOKEN: {mask_key(TWITTER_ACCESS_TOKEN)}")
logger.info(f"TWITTER_ACCESS_SECRET: {mask_key(TWITTER_ACCESS_SECRET)}")
logger.info(f"TWITTER_BEARER_TOKEN: {mask_key(TWITTER_BEARER_TOKEN)}")

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

def post_tweet(text: str) -> tuple[bool, str | None]:
    """
    Post a tweet with the given text.
    
    Args:
        text (str): The text to post as a tweet
        
    Returns:
        tuple: (success: bool, tweet_url: str | None) - True and URL if successful, False and None otherwise
    """
    if api_v1 is None and client_v2 is None:
        logger.error("Twitter API not initialized - cannot post tweet")
        return False, None

    if not text or len(text.strip()) == 0:
        logger.error("Cannot post empty tweet")
        return False, None

    if len(text) > 280:
        logger.error(f"Tweet text exceeds 280 characters ({len(text)} chars)")
        return False, None

    # Try v1.1 API first
    if api_v1:
        try:
            logger.info(f"Attempting to post tweet via v1.1 API: {text[:50]}...")
            tweet = api_v1.update_status(text)
            tweet_url = f"https://twitter.com/user/status/{tweet.id}"
            logger.info(f"Tweet posted successfully via v1.1 API: {tweet_url}")
            return True, tweet_url
        except tweepy.TweepyException as e:
            logger.warning(f"v1.1 API failed: {e}")
            # Continue to try v2 if available
        except Exception as e:
            logger.error(f"Unexpected error with v1.1 API: {e}")

    # Try v2 API if v1.1 failed or not available
    if client_v2:
        try:
            logger.info(f"Attempting to post tweet via v2 API: {text[:50]}...")
            response = client_v2.create_tweet(text=text)
            if response and response.data:
                tweet_id = response.data['id']
                tweet_url = f"https://twitter.com/user/status/{tweet_id}"
                logger.info(f"Tweet posted successfully via v2 API: {tweet_url}")
                return True, tweet_url
            else:
                logger.error("v2 API response missing tweet data")
                return True, None  # Posted but no URL available
        except tweepy.TweepyException as e:
            logger.error(f"v2 API failed: {e}")
        except Exception as e:
            logger.error(f"Unexpected error with v2 API: {e}")

    logger.error("All Twitter API posting methods failed")
    return False, None


def format_bill_tweet(bill: Dict) -> str:
    """
    Format a bill dictionary into a tweet string.
    
    Args:
        bill (dict): Bill dictionary from congress_fetcher.get_recent_bills()
        
    Returns:
        str: Formatted tweet string (max 280 characters)
    """
    if not bill:
        return ""
    
    # Extract bill information with fallbacks
    title = bill.get('title', 'Unknown Title')
    latest_action = bill.get('latest_action', 'No action recorded')
    bill_id = bill.get('bill_id', 'Unknown ID')
    
    # Truncate title and latest action if necessary
    max_title_length = 150
    max_action_length = 100
    
    if len(title) > max_title_length:
        title = title[:max_title_length - 3] + "..."
    
    if len(latest_action) > max_action_length:
        latest_action = latest_action[:max_action_length - 3] + "..."
    
    # Construct the tweet
    tweet_template = """🏛️ NEW BILL ALERT
{title}

Latest Action: {latest_action}

ID: {bill_id}"""
    
    tweet = tweet_template.format(
        title=title,
        latest_action=latest_action,
        bill_id=bill_id
    )
    
    # Ensure tweet doesn't exceed 280 characters
    if len(tweet) > 280:
        # Further truncate if needed
        excess = len(tweet) - 280
        if len(latest_action) > excess + 3:
            latest_action = latest_action[:-(excess + 3)] + "..."
        else:
            # If still too long, truncate title more aggressively
            title_max = max(50, len(title) - (excess - len(latest_action)) - 3)
            title = title[:title_max] + "..."
        
        tweet = tweet_template.format(
            title=title,
            latest_action=latest_action,
            bill_id=bill_id
        )
    
    return tweet


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
       