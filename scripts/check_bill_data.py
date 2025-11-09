#!/usr/bin/env python3
"""
Script to check if a bill exists in the database and retrieve its current data.
Takes an optional bill ID as a command line argument.
"""

import sys
import os
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Load environment variables
from dotenv import load_dotenv
load_dotenv(project_root / '.env')

from src.database.db_utils import get_bill_by_id

def main():
    # Check if a bill ID was provided as a command line argument
    if len(sys.argv) > 1:
        bill_id = sys.argv[1]
    else:
        bill_id = 'hr3872-119'  # Default fallback
    
    print(f"Checking if bill {bill_id} exists in the database...")
    
    # Check if DATABASE_URL is set
    if not os.environ.get('DATABASE_URL'):
        print("❌ DATABASE_URL environment variable not set.")
        print("Please check your .env file or environment configuration.")
        return
    
    # Use the get_bill_by_id function from src.database.db_utils
    bill_data = get_bill_by_id(bill_id)
    
    if bill_data:
        print("✅ Bill found in database!")
        print("\n=== BILL DATA ===")
        for key, value in bill_data.items():
            # Skip printing very long fields to keep output readable
            if key in ['summary_long', 'full_text', 'term_dictionary']:
                if value:
                    print(f"{key}: {str(value)[:200]}{'...' if len(str(value)) > 200 else ''}")
                else:
                    print(f"{key}: (empty)")
            elif key == 'tags':
                if value:
                    tags_list = value.split(',') if isinstance(value, str) else value
                    print(f"{key}: {tags_list}")
                else:
                    print(f"{key}: (empty)")
            else:
                print(f"{key}: {value}")
        
        print("\n=== SUMMARY FIELDS CHECK ===")
        summary_fields = ['summary_overview', 'summary_detailed', 'summary_tweet', 'summary_long']
        for field in summary_fields:
            if field in bill_data:
                value = bill_data[field]
                if value:
                    print(f"✅ {field}: Present ({len(str(value))} characters)")
                else:
                    print(f"❌ {field}: (empty)")
            else:
                print(f"❓ {field}: (field not present)")
                
        print("\n=== BILL TEXT CHECK ===")
        text_fields = ['full_text', 'text_source', 'text_version']
        for field in text_fields:
            if field in bill_data:
                value = bill_data[field]
                if value:
                    print(f"✅ {field}: Present ({len(str(value))} characters)")
                else:
                    print(f"❌ {field}: (empty)")
            else:
                print(f"❓ {field}: (field not present)")
    else:
        print(f"❌ Bill {bill_id} not found in database.")

if __name__ == "__main__":
    main()