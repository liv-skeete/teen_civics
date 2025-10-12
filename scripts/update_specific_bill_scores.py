import os
import sys
import re
import logging
from dotenv import load_dotenv
import psycopg2.extras

# Add the project root to the Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

from src.database.connection import postgres_connect
from src.database.db_utils import get_bill_by_id
from src.processors.summarizer import summarize_bill_enhanced

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def update_specific_bill_scores():
    """
    Fetches specific bills, regenerates their summaries and 'Teen Impact Score', 
    and updates them in the database.
    """
    load_dotenv()
    
    bill_ids_to_update = ['sres429-119', 'sres422-119']
    
    logger.info("Starting to update specific bill scores...")
    
    try:
        with postgres_connect() as conn:
            for bill_id in bill_ids_to_update:
                logger.info(f"Processing bill: {bill_id}")
                
                # Fetch the bill using the existing utility function
                bill = get_bill_by_id(bill_id)
                
                if bill:
                    logger.info(f"Found bill: {bill['title']}")
                    
                    # Regenerate the summary which contains the new score
                    new_summary_data = summarize_bill_enhanced(bill)
                    
                    if new_summary_data and new_summary_data.get('detailed'):
                        # Extract score for logging purposes
                        score_match = re.search(r"Teen impact score: (\d+/10)", new_summary_data['detailed'])
                        new_score_display = score_match.group(1) if score_match else "Not found"
                        
                        logger.info(f"Generated new Teen Impact Score: {new_score_display}")
                        
                        # Update the bill with the new summaries
                        with conn.cursor() as update_cursor:
                            update_cursor.execute(
                                """
                                UPDATE bills
                                SET summary_overview = %s, 
                                    summary_detailed = %s, 
                                    updated_at = CURRENT_TIMESTAMP
                                WHERE bill_id = %s
                                """,
                                (new_summary_data.get('overview'), new_summary_data.get('detailed'), bill_id),
                            )
                        logger.info(f"Successfully updated bill {bill_id} with new summary and score.")
                    else:
                        logger.warning(f"Could not generate a new summary for bill {bill_id}.")
                else:
                    logger.error(f"Bill with ID {bill_id} not found in the database.")
                    
    except Exception as e:
        logger.error(f"An error occurred during the update process: {e}", exc_info=True)

    logger.info("Finished updating specific bill scores.")

if __name__ == "__main__":
    update_specific_bill_scores()