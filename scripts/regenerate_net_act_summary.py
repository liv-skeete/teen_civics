import os
import sys
import logging
from typing import Dict, Any

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.database import db
from src.processors.summarizer import summarize_bill_enhanced as summarize_bill
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

def regenerate_summary_and_tweet(bill: Dict[str, Any]) -> Dict[str, Any]:
    """Regenerates the summary and tweet for a given bill."""
    logger.info(f"Regenerating summary for bill: {bill['bill_id']}")
    if not bill.get("full_text"):
        raise Exception("Bill has no full text to summarize.")
    
    summary_data = summarize_bill(bill)
    
    if not summary_data or not all(k in summary_data for k in ['overview', 'detailed', 'tweet', 'term_dictionary']):
        raise Exception("Failed to generate a valid summary.")
        
    return summary_data

def update_bill_in_db(bill_id: str, summary_data: Dict[str, Any]):
    """Updates the bill's summary and tweet in the database."""
    logger.info(f"Updating bill {bill_id} in the database.")
    success = db.update_bill_summaries(
        bill_id=bill_id,
        overview=summary_data["overview"],
        detailed=summary_data["detailed"],
        tweet=summary_data["tweet"],
        term_dictionary=summary_data["term_dictionary"]
    )
    if not success:
        raise Exception("Failed to update the bill in the database.")
    logger.info("Database update successful.")

def main():
    """Main function to find, regenerate, and update the NET Act bill."""
    try:
        init_connection_pool()
        
        net_act_bill = find_net_act_bill()
        
        new_summary_data = regenerate_summary_and_tweet(net_act_bill)
        
        update_bill_in_db(net_act_bill["bill_id"], new_summary_data)
        
        print("\n--- New Tweet Content ---")
        print(new_summary_data["tweet"])
        print("-------------------------\n")
        
    except Exception as e:
        logger.error(f"An error occurred: {e}")
    finally:
        close_connection_pool()

if __name__ == "__main__":
    main()