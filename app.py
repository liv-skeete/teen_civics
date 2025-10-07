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
            
        # Headers (start with emoji) - using standardized emojis from summarizer.py
        if any(line.startswith(emoji) for emoji in ['🏠', '💰', '🛠️', '⚖️', '🚀', '📌', '👉', '🔎', '📝', '🔑', '📜', '👥', '💡']):
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

def extract_teen_impact_score(summary: str) -> Optional[int]:
    """
    Extract teen impact score from bill summary text.
    Looks for pattern like "Teen impact score: X/10" or "Teen Impact Score: X/10"
    
    Args:
        summary: The bill summary text
        
    Returns:
        The teen impact score (0-10) or None if not found
    """
    if not summary:
        return None
    
    # Pattern to match "Teen impact score: X/10" (case insensitive)
    pattern = r'teen\s+impact\s+score:\s*(\d+)/10'
    match = re.search(pattern, summary, re.IGNORECASE)
    
    if match:
        try:
            score = int(match.group(1))
            # Validate score is in valid range
            if 0 <= score <= 10:
                return score
        except (ValueError, IndexError):
            pass
    
    return None

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
        return render_template('index.html', bill=None, error="Unable to load the latest bill. Please try again later.")

@app.route('/archive')
def archive():
    """Archive page: Displays all tweeted bills with optional filtering."""
    import time
    import os
    from src.database.connection import get_connection_string
    
    start_time = time.time()
    logger.info("=== Archive request started ===")
    
    try:
        # Verify database configuration before proceeding
        conn_string = get_connection_string()
        if not conn_string:
            error_msg = "Database connection not configured. Missing DATABASE_URL or Supabase environment variables."
            logger.error(error_msg)
            logger.error("Environment check: DATABASE_URL=%s, SUPABASE_DB_HOST=%s",
                        'SET' if os.environ.get('DATABASE_URL') else 'NOT SET',
                        'SET' if os.environ.get('SUPABASE_DB_HOST') else 'NOT SET')
            return render_template(
                'archive.html',
                bills=[],
                status_filter='all',
                current_page=1,
                total_pages=1,
                error_message=error_msg
            ), 500
        
        logger.info("Database connection string configured: %s",
                   conn_string[:20] + '...' if len(conn_string) > 20 else conn_string)
        
        # Get filter parameter
        status_filter = request.args.get('status', 'all')
        
        # Get all bills with enhanced logging
        db_start = time.time()
        logger.info("Calling get_all_tweeted_bills()...")
        bills = get_all_tweeted_bills()
        db_time = time.time() - db_start
        
        # Log detailed results
        logger.info(f"Database query completed in {db_time:.3f}s")
        logger.info(f"Retrieved {len(bills)} bills from database")
        
        if not bills:
            logger.warning("No bills returned from database. This may indicate:")
            logger.warning("  1. Database is empty (no bills have been tweeted)")
            logger.warning("  2. Database connection failed silently")
            logger.warning("  3. Query returned no results due to filtering")
        else:
            logger.info(f"Sample bills: {[bill.get('bill_id', 'unknown') for bill in bills[:3]]}")
        
        # Extract teen impact scores from summaries
        for bill in bills:
            summary = bill.get('summary_detailed', '')
            teen_impact_score = extract_teen_impact_score(summary)
            bill['teen_impact_score'] = teen_impact_score
        
        # Apply status filter if not 'all'
        if status_filter != 'all' and bills:
            # Normalize the filter value to match database format (lowercase with underscores)
            normalized_filter = status_filter.lower().replace(' ', '_')
            bills = [bill for bill in bills if bill.get('status') == normalized_filter]
            logger.info(f"Filtered to {len(bills)} bills with status '{status_filter}'")
        
        # For now, we'll show all bills on one page (no pagination)
        # If pagination is needed in the future, we can add it
        current_page = 1
        total_pages = 1
        
        render_start = time.time()
        response = render_template(
            'archive.html',
            bills=bills,
            status_filter=status_filter,
            current_page=current_page,
            total_pages=total_pages
        )
        render_time = time.time() - render_start
        total_time = time.time() - start_time
        
        logger.info(f"Template rendered in {render_time:.3f}s")
        logger.info(f"=== Archive request completed in {total_time:.3f}s ===")
        return response
    except Exception as e:
        error_msg = f"Failed to load archive: {str(e)}"
        logger.error(error_msg, exc_info=True)
        logger.error("Exception type: %s", type(e).__name__)
        
        # Provide detailed error context
        import os
        logger.error("Environment diagnostics:")
        logger.error("  DATABASE_URL: %s", 'SET' if os.environ.get('DATABASE_URL') else 'NOT SET')
        logger.error("  SUPABASE_DB_HOST: %s", 'SET' if os.environ.get('SUPABASE_DB_HOST') else 'NOT SET')
        logger.error("  Working directory: %s", os.getcwd())
        
        return render_template(
            'archive.html',
            bills=[],
            status_filter='all',
            current_page=1,
            total_pages=1,
            error_message=error_msg
        ), 500

@app.route('/debug/env')
def debug_env():
    """Debug endpoint to verify environment configuration (only in debug mode)."""
    import os
    from src.database.connection import get_connection_string
    
    # Only allow in debug mode
    if not app.config.get('DEBUG'):
        abort(404)
    
    try:
        conn_string = get_connection_string()
        
        # Mask sensitive parts of connection string
        masked_conn = None
        if conn_string:
            # Show first 30 chars and last 20 chars, mask the middle
            if len(conn_string) > 50:
                masked_conn = conn_string[:30] + '...[MASKED]...' + conn_string[-20:]
            else:
                masked_conn = conn_string[:10] + '...[MASKED]'
        
        env_status = {
            'database_configured': conn_string is not None,
            'connection_string_preview': masked_conn,
            'environment_variables': {
                'DATABASE_URL': 'SET' if os.environ.get('DATABASE_URL') else 'NOT SET',
                'SUPABASE_DB_HOST': 'SET' if os.environ.get('SUPABASE_DB_HOST') else 'NOT SET',
                'SUPABASE_DB_USER': 'SET' if os.environ.get('SUPABASE_DB_USER') else 'NOT SET',
                'SUPABASE_DB_PASSWORD': 'SET' if os.environ.get('SUPABASE_DB_PASSWORD') else 'NOT SET',
                'SUPABASE_DB_NAME': 'SET' if os.environ.get('SUPABASE_DB_NAME') else 'NOT SET',
                'SUPABASE_DB_PORT': os.environ.get('SUPABASE_DB_PORT', 'NOT SET'),
            },
            'working_directory': os.getcwd(),
            'python_path': os.environ.get('PYTHONPATH', 'NOT SET'),
        }
        
        # Try to test database connection
        try:
            from src.database.connection import get_db_connection
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT COUNT(*) FROM bills WHERE tweeted = TRUE")
                    count = cur.fetchone()[0]
                    env_status['database_test'] = {
                        'status': 'SUCCESS',
                        'tweeted_bills_count': count
                    }
        except Exception as db_error:
            env_status['database_test'] = {
                'status': 'FAILED',
                'error': str(db_error),
                'error_type': type(db_error).__name__
            }
        
        return jsonify(env_status)
    except Exception as e:
        logger.error(f"Error in debug endpoint: {e}", exc_info=True)
        return jsonify({
            'error': str(e),
            'error_type': type(e).__name__
        }), 500

@app.route('/bill/<string:slug>')
def bill_detail(slug: str):
    """Bill detail page: Displays a single bill by slug."""
    import time
    start_time = time.time()
    logger.info(f"=== Bill detail request started for slug: {slug} ===")
    
    try:
        db_start = time.time()
        bill = get_bill_by_slug(slug)
        db_time = time.time() - db_start
        logger.info(f"Database query completed in {db_time:.3f}s")
        
        if not bill:
            logger.warning(f"Bill not found for slug: {slug}")
            abort(404)
        
        render_start = time.time()
        response = render_template('bill.html', bill=bill)
        render_time = time.time() - render_start
        total_time = time.time() - start_time
        
        logger.info(f"Template rendered in {render_time:.3f}s")
        logger.info(f"=== Bill detail request completed in {total_time:.3f}s ===")
        return response
    except Exception as e:
        logger.error(f"Error loading bill detail for slug '{slug}': {e}", exc_info=True)
        abort(404)

@app.route('/about')
def about():
    """About page."""
    return render_template('about.html')

@app.route('/contact')
def contact():
    """Contact page."""
    return render_template('contact.html')

@app.route('/resources')
def resources():
    """Resources page."""
    return render_template('resources.html')

@app.errorhandler(404)
def page_not_found(e):
    """404 error handler."""
    return render_template('404.html'), 404

# --- API Routes ---

@app.route('/api/vote', methods=['POST'])
def record_vote():
    """API endpoint to record a user's poll vote."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "Invalid JSON data"}), 400
        
        bill_id = data.get('bill_id')
        vote_type = data.get('vote_type')
        previous_vote = data.get('previous_vote')

        if not bill_id or not vote_type:
            return jsonify({"success": False, "error": "Missing bill_id or vote_type"}), 400

        success = update_poll_results(bill_id, vote_type, previous_vote)
        
        if success:
            return jsonify({"success": True})
        else:
            logger.warning(f"Failed to update poll results for bill_id={bill_id}, vote_type={vote_type}")
            return jsonify({"success": False, "error": "Failed to update poll results"}), 500
    
    except Exception as e:
        logger.error(f"Error recording vote: {e}", exc_info=True)
        return jsonify({"success": False, "error": "An error occurred while recording your vote"}), 500

@app.route('/api/poll-results/<string:bill_id>')
def get_poll_results(bill_id: str):
    """API endpoint to get poll results for a specific bill."""
    try:
        bill = get_bill_by_id(bill_id)
        if not bill:
            return jsonify({"success": False, "error": "Bill not found"}), 404
        
        return jsonify({
            "success": True,
            "bill_id": bill_id,
            "yes_votes": bill.get('poll_results_yes', 0),
            "no_votes": bill.get('poll_results_no', 0)
        })
    except Exception as e:
        logger.error(f"Error fetching poll results for bill_id '{bill_id}': {e}", exc_info=True)
        return jsonify({"success": False, "error": "An error occurred while fetching poll results"}), 500

if __name__ == '__main__':
    try:
        logger.info(f"Starting Flask app on {config.flask.host}:{config.flask.port}")
        logger.info(f"Debug mode: {config.flask.debug}")
        app.run(
            debug=config.flask.debug,
            host=config.flask.host,
            port=config.flask.port
        )
    except Exception as e:
        logger.error(f"Failed to start Flask app: {e}", exc_info=True)