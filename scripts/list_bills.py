import os
import sys
import logging

# Add the project root to the Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

from src.database.db_utils import get_all_bills
from src.database.connection import get_connection_string
from src.load_env import load_env

logging.basicConfig(level=logging.INFO)

def main():
    load_env()
    logging.info("Listing all bills...")
    
    # Ensure the database connection is configured
    if not get_connection_string():
        logging.error("Database connection not configured. Please set DATABASE_URL or Supabase environment variables.")
        return
        
    bills = get_all_bills()
    for bill in bills:
        print(f"Bill ID: {bill['bill_id']}, Slug: {bill['website_slug']}")
        
if __name__ == "__main__":
    main()