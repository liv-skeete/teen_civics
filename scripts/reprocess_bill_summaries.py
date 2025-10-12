import os
import sys
import regex
import logging

# Add the project root to the Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

from src.database.db_utils import get_all_bills, update_bill_summaries

logging.basicConfig(level=logging.INFO)

def reformat_summary(text: str) -> str:
    if not text:
        return ""
    
    s = str(text).replace("\r\n", "\n").replace("\r", "\n")
    s = regex.sub(r'(?<!^)(\p{Emoji})', r'\n\1', s)
    s = s.replace('•', '\n•')
    return s

def main():
    logging.info("Starting bill summary reprocessing...")
    bills = get_all_bills()
    for bill in bills:
        bill_id = bill['bill_id']
        logging.info(f"Reprocessing bill {bill_id}...")
        
        overview = bill.get('summary_overview', '')
        detailed = bill.get('summary_detailed', '')
        
        new_overview = reformat_summary(overview)
        new_detailed = reformat_summary(detailed)
        
        update_bill_summaries(bill_id, new_overview, new_detailed)
        logging.info(f"Successfully reprocessed bill {bill_id}")
        
    logging.info("Finished reprocessing all bill summaries.")

if __name__ == "__main__":
    main()