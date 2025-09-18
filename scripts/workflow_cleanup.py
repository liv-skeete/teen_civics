#!/usr/bin/env python3
"""
Comprehensive cleanup script for the daily workflow.
This runs after the orchestrator to ensure clean formatting and proper database state.
"""

import os
import sys
import logging
import re
import ast

# Add project root to path for imports
project_root = os.path.join(os.path.dirname(__file__), '..')
sys.path.insert(0, project_root)

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def normalize_text(value):
    """Apply comprehensive text normalization"""
    if not value:
        return value
        
    text = str(value).strip()
    
    # If it's a string that looks like a Python list, parse it safely
    if text.startswith('[') and text.endswith(']'):
        try:
            maybe = ast.literal_eval(text)
            if isinstance(maybe, (list, tuple)):
                parts = [str(p).strip() for p in maybe if str(p).strip()]
                text = "\n".join(parts)
        except Exception:
            # Leave original string if parsing fails
            pass

    # Normalize newlines
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    
    # Clean up formatting artifacts from list parsing
    # Remove stray quotes at start/end of lines
    text = re.sub(r"^['\"]|['\"]$", "", text, flags=re.MULTILINE)
    # Remove stray commas at start of lines (like "', 'This bill...")
    text = re.sub(r"^[',]\s*", "", text, flags=re.MULTILINE)
    # Remove standalone quotes and commas on their own lines
    text = re.sub(r"^\s*[',\"]\s*$", "", text, flags=re.MULTILINE)
    
    # Repair split header variants (case-insensitive) - handle newlines and spaces
    text = re.sub(r"(Key Rules)\s*\n?\s*/\s*Changes", r"\1/Changes", text, flags=re.IGNORECASE)
    text = re.sub(r"(Policy Riders or Key Rules)\s*\n?\s*/\s*Changes", r"\1/Changes", text, flags=re.IGNORECASE)
    # Also handle the specific case where /Changes appears on its own line
    text = re.sub(r"(⚖️ Policy Riders or Key Rules)\s*\n\s*/Changes", r"\1/Changes", text, flags=re.IGNORECASE)
    
    # Clean up excessive whitespace and blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)  # Normalize spaces/tabs
    
    return text.strip()

def main():
    """Run comprehensive cleanup after orchestrator"""
    try:
        logger.info("Starting workflow cleanup...")
        
        # Import required modules
        from src.database.db import get_all_bills, update_bill_summaries
        
        # Get all bills from database
        all_bills = get_all_bills(limit=1000)
        if not all_bills:
            logger.warning("No bills found in database")
            return 0
            
        updated_count = 0
        
        # Focus on the most recent bills (likely to have formatting issues)
        recent_bills = all_bills[:5]  # Check last 5 bills
        
        for bill in recent_bills:
            bill_id = bill.get('bill_id', '')
            updates = {}
            
            # Check and normalize summary fields
            for field in ['summary_overview', 'summary_detailed']:
                current_value = bill.get(field)
                if current_value:
                    normalized = normalize_text(current_value)
                    if normalized != current_value:
                        updates[field] = normalized
                        logger.info(f"Will normalize {field} for {bill_id}")
            
            # Update if we have changes
            if updates:
                success = update_bill_summaries(bill_id=bill_id, **updates)
                if success:
                    updated_count += 1
                    logger.info(f"✅ Updated {bill_id}")
                else:
                    logger.error(f"❌ Failed to update {bill_id}")
        
        logger.info(f"Workflow cleanup complete. Updated {updated_count} bills.")
        return 0
            
    except ImportError as e:
        logger.error(f"Import error: {e}")
        return 1
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())