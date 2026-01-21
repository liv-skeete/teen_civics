import sys
import os
import logging
from typing import Dict, Any
import psycopg2.extras

# Add the project root to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database.connection import postgres_connect
from src.processors.summarizer import summarize_bill_enhanced
from src.load_env import load_env

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def regenerate_scores():
    """
    Fetches all bills from the database, regenerates their summaries and Teen Impact Scores,
    and updates the records in the database.
    """
    load_env()
    logger.info("Starting regeneration of Teen Impact Scores for all bills.")
    
    try:
        with postgres_connect() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                logger.info("Fetching all bills from the database...")
                cursor.execute("SELECT * FROM bills")
                bills = cursor.fetchall()
                logger.info(f"Found {len(bills)} bills to process.")

                for bill in bills:
                    bill_id = bill["bill_id"]
                    logger.info(f"Processing bill: {bill_id}")

                    try:
                        # Recreate the bill dictionary expected by the summarizer
                        bill_data = dict(bill)
                        
                        # The summarizer might need specific fields, ensure they exist
                        # even if they are None.
                        required_fields = [
                            'title', 'short_title', 'status', 'summary_tweet', 
                            'summary_long', 'congress_session', 'date_introduced', 
                            'source_url', 'full_text', 'text_format', 'text_url'
                        ]
                        for field in required_fields:
                            if field not in bill_data:
                                bill_data[field] = None

                        # Regenerate the summary
                        new_summary = summarize_bill_enhanced(bill_data)

                        # Update the database
                        with conn.cursor() as update_cursor:
                            update_cursor.execute(
                                """
                                UPDATE bills
                                SET summary_overview = %s, summary_detailed = %s, updated_at = CURRENT_TIMESTAMP
                                WHERE id = %s
                                """,
                                (new_summary.get("overview"), new_summary.get("detailed"), bill["id"]),
                            )
                        logger.info(f"Successfully updated score for bill {bill_id}")

                    except Exception as e:
                        logger.error(f"Failed to process bill {bill_id}: {e}")

    except Exception as e:
        logger.error(f"An error occurred during the regeneration process: {e}")

if __name__ == "__main__":
    regenerate_scores()