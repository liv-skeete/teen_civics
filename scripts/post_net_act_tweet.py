import os
import sys
import logging
from typing import Dict, Any

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.database import db
from src.publishers.twitter_publisher import format_bill_tweet, post_tweet
from src.database.connection import init_connection_pool, close_connection_pool

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def find_net_act_bill() -> Dict[str, Any]:
    """Finds the NET Act bill in the database."""
    logger.info("Searching for the NET Act bill...")
    bills = db.search_bills_by_title("NET Act")
    if not bills:
        raise Exception("NET Act bill not found.")
    if len(bills) > 1:
        logger.warning("Multiple bills found for 'NET Act'. Using the first one.")
    return bills[0]

def main():
    """Main function to find the NET Act bill and post a tweet about it."""
    try:
        init_connection_pool()
        
        net_act_bill = find_net_act_bill()
        
        # Format the tweet
        tweet_text = format_bill_tweet(net_act_bill)
        
        logger.info(f"Formatted tweet:\n{tweet_text}")
        
        # Post the tweet
        success, tweet_url = post_tweet(tweet_text)
        
        if success:
            logger.info(f"Successfully posted tweet: {tweet_url}")
            # Optionally, update the bill with the new tweet URL
            if tweet_url:
                db.update_tweet_info(net_act_bill["bill_id"], tweet_url)
        else:
            raise Exception("Failed to post tweet.")
            
    except Exception as e:
        logger.error(f"An error occurred: {e}")
    finally:
        close_connection_pool()

if __name__ == "__main__":
    main()