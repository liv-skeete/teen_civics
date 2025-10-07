#!/usr/bin/env python3
"""
Script to fix the MERICA Act bill's corrupted summary_detailed field.
Converts Python dict/JSON string to properly formatted text.
"""

import os
import sys
import ast
import json
import logging
from src.database.connection import postgres_connect
from src.load_env import load_env

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def parse_corrupted_summary(corrupted_text):
    """
    Parse the corrupted summary text (Python dict string) and convert to formatted text.
    
    Args:
        corrupted_text: String containing Python dict or JSON
        
    Returns:
        Properly formatted text with emoji headers and bullet points
    """
    try:
        # Try parsing as Python literal first
        data = ast.literal_eval(corrupted_text)
    except (ValueError, SyntaxError):
        try:
            # Try parsing as JSON
            data = json.loads(corrupted_text)
        except json.JSONDecodeError:
            logger.error("Failed to parse corrupted summary as Python dict or JSON")
            return None
    
    if not isinstance(data, dict):
        logger.error("Parsed data is not a dictionary")
        return None
    
    # Build formatted text
    formatted_parts = []
    
    for key, value in data.items():
        # Add the emoji header on its own line
        formatted_parts.append(key)
        formatted_parts.append("")  # Empty line after header
        
        if isinstance(value, list):
            # Format list items with bullet points
            for item in value:
                formatted_parts.append(f"• {item}")
        else:
            # Add text content
            formatted_parts.append(str(value))
        
        # Add empty line between sections
        formatted_parts.append("")
    
    # Join with newlines and remove trailing empty lines
    formatted_text = "\n".join(formatted_parts).rstrip()
    
    return formatted_text

def fix_merica_act_summary():
    """
    Fix the MERICA Act bill's corrupted summary_detailed field.
    """
    bill_id = 'hr3872-119'
    
    logger.info(f"Starting fix for bill: {bill_id}")
    
    try:
        with postgres_connect() as conn:
            with conn.cursor() as cursor:
                # Query the current corrupted summary
                cursor.execute(
                    "SELECT summary_detailed FROM bills WHERE bill_id = %s",
                    (bill_id,)
                )
                result = cursor.fetchone()
                
                if not result:
                    logger.error(f"Bill {bill_id} not found in database")
                    return False
                
                corrupted_summary = result[0]
                
                if not corrupted_summary:
                    logger.error(f"Bill {bill_id} has no summary_detailed field")
                    return False
                
                logger.info("Current corrupted summary (first 200 chars):")
                logger.info(corrupted_summary[:200])
                
                # Parse and format the summary
                formatted_summary = parse_corrupted_summary(corrupted_summary)
                
                if not formatted_summary:
                    logger.error("Failed to parse and format the summary")
                    return False
                
                logger.info("\nFormatted summary (first 500 chars):")
                logger.info(formatted_summary[:500])
                
                # Update the database with the corrected summary
                cursor.execute(
                    "UPDATE bills SET summary_detailed = %s WHERE bill_id = %s",
                    (formatted_summary, bill_id)
                )
                
                logger.info(f"\n✅ Successfully updated summary for bill {bill_id}")
                
                # Verify the update
                cursor.execute(
                    "SELECT summary_detailed FROM bills WHERE bill_id = %s",
                    (bill_id,)
                )
                updated_result = cursor.fetchone()
                
                if updated_result:
                    logger.info("\nVerification - Updated summary (first 500 chars):")
                    logger.info(updated_result[0][:500])
                
                return True
                
    except Exception as e:
        logger.error(f"Error fixing MERICA Act summary: {e}")
        return False

def main():
    """Main entry point."""
    # Load environment variables
    load_env()
    
    # Fix the summary
    success = fix_merica_act_summary()
    
    if success:
        logger.info("\n🎉 MERICA Act summary has been successfully fixed!")
        sys.exit(0)
    else:
        logger.error("\n❌ Failed to fix MERICA Act summary")
        sys.exit(1)

if __name__ == "__main__":
    main()