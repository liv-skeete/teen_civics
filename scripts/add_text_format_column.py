#!/usr/bin/env python3
"""
Adds the text_format column to the bills table in the database.
"""

import os
import sys
import logging
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Load environment variables
from dotenv import load_dotenv
load_dotenv(project_root / '.env')

from src.database.connection import postgres_connect

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def add_column():
    try:
        with postgres_connect() as conn:
            with conn.cursor() as cursor:
                logger.info("Adding 'text_format' column to 'bills' table...")
                cursor.execute("ALTER TABLE bills ADD COLUMN text_format VARCHAR(10);")
                conn.commit()
                logger.info("Column 'text_format' added successfully.")
    except Exception as e:
        logger.error(f"Error adding column: {e}")

if __name__ == "__main__":
    add_column()