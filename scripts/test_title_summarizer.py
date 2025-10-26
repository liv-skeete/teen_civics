import os
import sys
import logging
from dotenv import load_dotenv

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.database.db import get_bill_by_id
from src.processors.summarizer import summarize_title

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def test_title_summarization(bill_id: str):
    """
    Tests the title summarization for a specific bill.
    """
    logger.info(f"Testing title summarization for bill: {bill_id}")
    
    # Load environment variables
    load_dotenv()
    
    # Fetch the bill from the database
    bill = get_bill_by_id(bill_id)
    
    if not bill:
        logger.error(f"Bill with ID '{bill_id}' not found in the database.")
        return
        
    bill_title = bill.get("title")
    
    if not bill_title:
        logger.error(f"Bill with ID '{bill_id}' has no title.")
        return
        
    logger.info(f"Original title: {bill_title}")
    
    # Summarize the title
    summarized_title = summarize_title(bill_title)
    
    logger.info(f"Summarized title: {summarized_title}")

if __name__ == "__main__":
    test_title_summarization("sres464-119")