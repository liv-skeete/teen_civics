"""
Script to clear stale "meaningful action" generic text from bills table.
This forces regeneration of arguments on next access/update.
"""

import sys
import os
import logging
from sqlalchemy import text

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.load_env import load_env
from src.database.db import db_connect

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def clear_stale_arguments():
    """Clear argument_support and argument_oppose where content matches old generic text."""
    
    # Load environment variables
    load_env()

    # Text to identify the old generic fallback
    OLD_GENERIC_KEYPHRASE = "it takes meaningful action on"
    
    try:
        with db_connect() as conn:
            with conn.cursor() as cursor:
                logger.info(f"Checking for arguments containing: '{OLD_GENERIC_KEYPHRASE}'")
                
                # Count affected rows first
                pattern = f"%{OLD_GENERIC_KEYPHRASE}%"
                cursor.execute("""
                    SELECT COUNT(*) FROM bills 
                    WHERE argument_support LIKE %s
                       OR argument_oppose LIKE %s
                """, (pattern, pattern))
                
                result = cursor.fetchone()[0]
                
                if result == 0:
                    logger.info("✅ No stale arguments found.")
                    return

                logger.info(f"__FOUND {result} BILLS WITH STALE ARGUMENTS__")
                logger.info("Clearing arguments now...")

                # Update to NULL
                cursor.execute("""
                    UPDATE bills 
                    SET argument_support = NULL, 
                        argument_oppose = NULL 
                    WHERE argument_support LIKE %s
                       OR argument_oppose LIKE %s
                """, (pattern, pattern))
                
                # Commit is handled by db_connect context manager on success
                
                logger.info(f"✅ Successfully cleared arguments for {result} bills.")
            
    except Exception as e:
        logger.error(f"Error clearing stale arguments: {e}")
        sys.exit(1)

if __name__ == "__main__":
    clear_stale_arguments()
