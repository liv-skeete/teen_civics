#!/usr/bin/env python3
"""
Flask web application for TeenCivics.
Provides routes for displaying bills, an archive, and other static pages.
"""

import re
import json
from datetime import datetime
from typing import Any, Dict, List, Optional

# Import configuration system
from src.config import get_config

# Initialize configuration
config = get_config()

# Configure logging
import logging
logging.basicConfig(
    level=getattr(logging, config.logging.level),
    format=config.logging.format
)
logger = logging.getLogger(__name__)

from flask import Flask, render_template, request, jsonify, abort
from markupsafe import Markup, escape

# Import database functions
from src.database.db import (
    get_all_bills,
    get_bill_by_id,
    get_latest_bill,
    get_latest_tweeted_bill,
    get_all_tweeted_bills,
    get_bill_by_slug,
    update_poll_results,
)

# Configure Flask app
app = Flask(__name__)
app.config['DEBUG'] = config.flask.debug

# Helper to format dates
@app.template_filter('format_date')
def format_date_filter(date_str: Optional[str]) -> str:
    """Format ISO date string into a more readable format."""
    if not date_str:
        return "Not available"
    try:
        # Handle both date and datetime strings
        if 'T' in date_str:
            date_obj = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        else:
            date_obj = datetime.strptime(date_str, '%Y-%m-%d')
        return date_obj.strftime('%B %d, %Y')
    except (ValueError, TypeError):
        return date_str

@app.template_filter('format_status')
def format_status_filter(status: str) -> str:
    """Format bill status string into a more readable format."""
    return (status or "").replace("_", " ").title()

@app.template_filter('generate_congress_url')
def generate_congress_url(bill_id: str, congress_session: str = "") -> str:
    """
    Construct a direct link to the bill on Congress.gov.
    Example: https://www.congress.gov/bill/118th-congress/house-bill/5376
    
    Args:
        bill_id: The bill identifier (e.g., 'hr5376', 's1234')
        congress_session: The congress session number (e.g., '118')
    """
    if not bill_id:
        return "https://www.congress.gov/"
    
    if not congress_session:
        return f"https://www.congress.gov/search?q={bill_id}"

    try:
        # Extract bill type and number from bill_id
        bill_type = None
        bill_number = None
        full_type = None
        
        # Patterns for different bill types
        patterns = {
            "hr": "house-bill",
            "s": "senate-bill",
            "hres": "house-resolution",
            "sres": "senate-resolution",
            "hjres": "house-joint-resolution",
            "sjres": "senate-joint-resolution",
            "hconres": "house-concurrent-resolution",
            "sconres": "senate-concurrent-resolution",
        }
        
        bid = bill_id.lower()
        for pattern, congress_type in patterns.items():
            if bid.startswith(pattern):
                # Extract the number part after the bill type
                remainder = bid[len(pattern):]
                # Extract just the numeric part (before any dash or non-digit)
                number_match = re.match(r'^(\d+)', remainder)
                if number_match:
                    bill_type = pattern
                    bill_number = number_match.group(1)
                    full_type = congress_type
                    break
        
        if not bill_type or not bill_number or not full_type:
            return f"https://www.congress.gov/search?q={bill_id}"

        # Ensure numeric pieces are clean
        try:
            congress_int = int(str(congress_session).strip())
            bill_num_int = int(bill_number)
        except Exception:
            return f"https://www.congress.gov/search?q={bill_id}"

        return f"https://www.congress.gov/bill/{congress_int}th-congress/{full_type}/{bill_num_int}"
    except Exception:
        return f"https://www.congress.gov/search?q={bill_id}"

@app.template_filter('from_json')
def from_json_filter(json_str):
    """Parse JSON string into Python object"""
    if not json_str:
        return None
    try:
        import json
        return json.loads(json_str)
    except (ValueError, TypeError, json.JSONDecodeError):
        return None

@app.template_filter('format_detailed_html')
def format_detailed_html_filter(text: str) -> Markup:
    """Single source of truth for formatting bill summaries."""
    if not text:
        return Markup("")
    
    # Remove any HTML artifacts
    text = text.replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n")
    
    # Process line by line
    lines = text.split('\n')
    html_parts = []
    in_list = False
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # Headers (start with emoji)
        if any(line.startswith(emoji) for emoji in ['🏠', '📋', '💰', '🛠️', '⚖️', '🚀', '📌', '👉', '🔍', '🔎', '📝', '🔑', '📜']):
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            html_parts.append(f'<h4>{escape(line)}</h4>')
        
        # Bullet points
        elif line.startswith('•') or line.startswith('-'):
            if not in_list:
                html_parts.append("<ul>")
                in_list = True
            # Remove bullet and add as list item
            text_content = line[1:].strip()
            html_parts.append(f'<li>{escape(text_content)}</li>')
        
        # Regular text
        else:
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            html_parts.append(f'<p>{escape(line)}</p>')
    
    # Close any open list
    if in_list:
        html_parts.append("</ul>")
    
    return Markup('\n'.join(html_parts))

@app.template_filter('shorten_title')
def shorten_title_filter(title: str, max_length: int = 60) -> str:
    """Shorten a title to a maximum length, adding ellipsis if truncated."""
    if not title:
        return ""
    if len(title) <= max_length:
        return title
    return title[:max_length].rsplit(' ', 1)[0] + "..."

# --- Routes ---

@app.route('/')
def index():
    """Homepage: Displays the most recent tweeted bill."""
    import time
    start_time = time.time()
    logger.info("=== Homepage request started ===")
    
    try:
        db_start = time.time()
        latest_bill = get_latest_tweeted_bill()
        db_time = time.time() - db_start
        logger.info(f"Database query completed in {db_time:.3f}s")
        
        if not latest_bill:
            logger.warning("No latest bill found")
            return render_template('index.html', bill=None)
        
        render_start = time.time()
        response = render_template('index.html', bill=latest_bill)
        render_time = time.time() - render_start
        total_time = time.time() - start_time
        
        logger.info(f"Template rendered in {render_time:.3f}s")
        logger.info(f"=== Homepage request completed in {total_time:.3f}s ===")
        return response
    except Exception as e:
        logger.error(f"Error loading homepage: {e}", exc_info=True)
        return render_template('index.