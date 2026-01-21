import os
import sys
import logging
from typing import Dict, Any

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.database import db
from src.processors.teen_impact import score_teen_impact
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

def update_teen_impact_score(bill_id: str, score: int):
    """Updates the teen impact score for a bill."""
    logger.info(f"Updating teen impact score for bill {bill_id} to {score}.")
    success = db.update_bill_teen_impact_score(bill_id, score)
    if not success:
        raise Exception(f"Failed to update teen impact score for bill {bill_id}")

def main():
    """Main function to find and update the NET Act bill's teen impact score."""
    try:
        init_connection_pool()
        
        net_act_bill = find_net_act_bill()
        
        # Recalculate the teen impact score
        impact_data = score_teen_impact(net_act_bill)
        new_score = impact_data.get("score")
        
        if new_score is None:
            raise Exception("Failed to calculate teen impact score.")
            
        update_teen_impact_score(net_act_bill["bill_id"], new_score)
        
        logger.info(f"Successfully updated teen impact score for {net_act_bill['bill_id']} to {new_score}.")
        
    except Exception as e:
        logger.error(f"An error occurred: {e}")
    finally:
        close_connection_pool()

if __name__ == "__main__":
    main()