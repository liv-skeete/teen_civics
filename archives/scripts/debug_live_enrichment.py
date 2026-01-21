import logging
import os
import sys

# Add the src directory to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

# Load environment variables from .env file
from load_env import load_env
load_env()

from fetchers.feed_parser import fetch_and_enrich_bills

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def debug_bill_enrichment(bill_slug):
    """
    Fetches and enriches bills, then filters for a specific bill and logs its data.
    """
    logging.info(f"Starting enrichment process to find bill: {bill_slug}")
    
    # Extract bill number and congress from the slug (e.g., hr2316-119)
    if '-' not in bill_slug:
        logging.error(f"Invalid bill slug format: {bill_slug}")
        return
    
    parts = bill_slug.split('-')
    if len(parts) != 2:
        logging.error(f"Invalid bill slug format: {bill_slug}")
        return
        
    bill_number_part = parts[0]  # e.g., hr2316
    congress = parts[1]  # e.g., 119
    
    # For testing, we'll fetch a reasonable number of bills (e.g., 100) to increase chances of finding the specific bill
    # This is a temporary solution for debugging. In a real fix, we'd want a more targeted approach.
    limit = 100
    
    try:
        enriched_bills_generator = fetch_and_enrich_bills(limit=limit)
        
        target_bill = None
        for bill in enriched_bills_generator:
            if bill.get('bill_id') == bill_slug:
                target_bill = bill
                break
                
        if target_bill:
            logging.info("--- Final Enriched Bill ---")
            import json
            print(json.dumps(target_bill, indent=2))
            logging.info("--------------------------")
        else:
            logging.warning(f"Target bill {bill_slug} not found in the enriched bills.")
            
    except Exception as e:
        logging.error(f"An error occurred during the enrichment process: {e}", exc_info=True)

if __name__ == "__main__":
    # The bill slug for the problematic bill
    problem_bill_slug = "hr2316-119"
    debug_bill_enrichment(problem_bill_slug)