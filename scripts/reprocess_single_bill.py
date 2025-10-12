import os
import sys
import logging
import argparse

# Add the project root to the Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

from src.database.db_utils import get_bill_by_slug, update_bill_summaries
from src.processors.summarizer import summarize_bill_enhanced

logging.basicConfig(level=logging.INFO)

def main(slug: str):
    logging.info(f"Starting reprocessing for bill slug: {slug}")
    
    bill = get_bill_by_slug(slug)
    
    if not bill:
        logging.error(f"Bill with slug '{slug}' not found.")
        return
        
    logging.info(f"Reprocessing bill {bill['bill_id']}...")
    
    # Generate new summary
    new_summary = summarize_bill_enhanced(bill)
    
    logging.info(f"DEBUG - summarize_bill_enhanced returned: {type(new_summary)}")
    logging.info(f"DEBUG - new_summary value: {new_summary}")
    
    if not new_summary:
        logging.error(f"Failed to generate summary for bill {bill['bill_id']}")
        return
        
    # Update the database
    update_bill_summaries(
        bill['bill_id'],
        new_summary.get('overview'),
        new_summary.get('detailed')
    )
    
    logging.info(f"Successfully reprocessed bill {bill['bill_id']}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Reprocess a single bill summary.")
    parser.add_argument("slug", type=str, help="The slug of the bill to reprocess.")
    args = parser.parse_args()
    
    main(args.slug)