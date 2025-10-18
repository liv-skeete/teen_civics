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
from logging.handlers import RotatingFileHandler
import os

# Base logging configuration
logging.basicConfig(
    level=getattr(logging, config.logging.level),
    format=config.logging.format,
    handlers=[logging.StreamHandler()]  # Log to console by default
)

logger = logging.getLogger(__name__)

# Add file handler if specified in config
if config.logging.file_path:
    # Create log directory if it doesn't exist
    log_dir = os.path.dirname(config.logging.file_path)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    # Use a rotating file handler
    file_handler = RotatingFileHandler(
        config.logging.file_path,
        maxBytes=1024 * 1024 * 5,  # 5 MB
        backupCount=2
    )
    file_handler.setFormatter(logging.Formatter(config.logging.format))
    
    # Add the handler to the root logger
    logging.getLogger().addHandler(file_handler)
    logger.info(f"Logging configured to file: {config.logging.file_path}")

from flask import Flask, render_template, request, jsonify, abort
from markupsafe import Markup, escape
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect
import secrets

# Import database functions
from src.database.db import (
    get_all_bills,
    get_bill_by_id,
    get_latest_bill,
    get_latest_tweeted_bill,
    get_all_tweeted_bills,
    get_bill_by_slug,
    update_poll_results,
    search_tweeted_bills,
    count_search_tweeted_bills,
)

# Configure Flask app
app = Flask(__name__)
app.config['DEBUG'] = config.flask.debug

# Security: Generate a secret key if not set
if not app.config.get('SECRET_KEY'):
    app.config['SECRET_KEY'] = secrets.token_hex(32)
    logger.warning("SECRET_KEY not set in environment, using generated key (not suitable for production)")

# Security: Secure session configuration
app.config['SESSION_COOKIE_SECURE'] = not config.flask.debug  # True in production
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

# Security: Initialize CSRF protection
csrf = CSRFProtect(app)

# Security: Initialize rate limiter
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"
)

# --- Constants ---
DEFAULT_ARCHIVE_PAGE_SIZE = 24


# Security: Add security headers middleware
@app.after_request
def add_security_headers(response):
    """Add security headers to all responses."""
    # Prevent clickjacking
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    
    # Content Security Policy
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://www.googletagmanager.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "connect-src 'self' https://www.google-analytics.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data: https:; "
        "connect-src 'self'; "
        "frame-ancestors 'self';"
    )
    
    # Prevent MIME type sniffing
    response.headers['X-Content-Type-Options'] = 'nosniff'
    
    # XSS Protection (legacy but still useful)
    response.headers['X-XSS-Protection'] = '1; mode=block'
    
    # HSTS (HTTP Strict Transport Security) - only in production
    if not config.flask.debug:
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    
    return response

# --- Context Processors ---

@app.context_processor
def inject_ga_measurement_id():
    """Inject GA_MEASUREMENT_ID into all templates."""
    ga_id = config.flask.ga_measurement_id
    return dict(ga_measurement_id=ga_id)

@app.context_processor
def inject_current_year():
    """Inject the current year into all templates for the footer."""
    return {'current_year': datetime.utcnow().year}
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

@app.template_filter('format_datetime_simple')
def format_datetime_simple_filter(date_str: Optional[str]) -> str:
    """Format ISO datetime string into a simple format: YYYY-MM-DD HH:MM:SS"""
    if not date_str:
        return "Not available"
    try:
        # Handle datetime strings with timezone info and microseconds
        if isinstance(date_str, str):
            # Handle the different timestamp formats we might encounter
            if 'T' in date_str:
                # Handle ISO format like "2025-10-10T04:35:51.745392+00:00"
                if '.' in date_str:
                    # Remove microseconds
                    date_part = date_str.split('.')[0]
                else:
                    date_part = date_str
                
                # Remove timezone info
                if '+' in date_part:
                    date_part = date_part.split('+')[0]
                elif date_part.endswith('Z'):
                    date_part = date_part[:-1]
                
                date_obj = datetime.fromisoformat(date_part)
            elif '+' in date_str:
                # Handle format like "2025-10-10 04:35:51+00" or "2025-10-10 04:35:51+00:00"
                date_part = date_str.split('+')[0]
                date_obj = datetime.fromisoformat(date_part)
            elif len(date_str) == 19 and date_str[4] == '-' and date_str[7] == '-' and date_str[10] == ' ' and date_str[13] == ':' and date_str[16] == ':':
                # Already in our target format, return as is
                return date_str
            else:
                # Try to parse as datetime string
                try:
                    date_obj = datetime.fromisoformat(date_str)
                except ValueError:
                    # If that fails, try to parse with space instead of T
                    if 'T' in date_str:
                        fixed_str = date_str.replace('T', ' ')
                        if '+' in fixed_str:
                            fixed_str = fixed_str.split('+')[0]
                        date_obj = datetime.fromisoformat(fixed_str)
                    else:
                        # Try to handle other formats
                        # For "YYYY-MM-DD HH:MM:SS+00" format
                        if '+' in date_str:
                            date_part = date_str.split('+')[0]
                            date_obj = datetime.fromisoformat(date_part)
                        else:
                            raise
            return date_obj.strftime('%Y-%m-%d %H:%M:%S')
        else:
            # Handle datetime objects
            return date_str.strftime('%Y-%m-%d %H:%M:%S')
    except (ValueError, TypeError) as e:
        # Log the error for debugging but don't crash
        logger.debug(f"Date formatting error for '{date_str}': {e}")
        return str(date_str) if date_str else "Not available"

@app.template_filter('format_status')
def format_datetime_simple_filter(date_str: Optional[str]) -> str:
    """Format ISO datetime string into a simple format: YYYY-MM-DD HH:MM:SS"""
    if not date_str:
        return "Not available"
    try:
        # Handle datetime strings with timezone info
        if 'T' in date_str:
            # Remove timezone info and microseconds
            if '.' in date_str:
                date_str = date_str.split('.')[0]
            if '+' in date_str:
                date_str = date_str.split('+')[0]
            if date_str.endswith('Z'):
                date_str = date_str[:-1]
            date_obj = datetime.fromisoformat(date_str)
        else:
            date_obj = datetime.strptime(date_str, '%Y-%m-%d')
        return date_obj.strftime('%Y-%m-%d %H:%M:%S')
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
    """Homepage: Displays the most recent tweeted bill, falls back to latest bill if none tweeted."""
    import time
    start_time = time.time()
    logger.info("=== Homepage request started ===")
    
    try:
        db_start = time.time()
        # First try to get the latest tweeted bill
        latest_bill = get_latest_tweeted_bill()
        
        # If no tweeted bills, fall back to the most recent bill regardless of tweet status
        if not latest_bill:
            logger.info("No tweeted bills found, falling back to most recent bill")
            latest_bill = get_latest_bill()
        
        db_time = time.time() - db_start
        logger.info(f"Database query completed in {db_time:.3f}s")
        
        if not latest_bill:
            logger.warning("No bills found in database")
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
    """Archive page: Displays all tweeted bills with search, filtering, and pagination."""
    import time
    import math
    from src.database.connection import get_connection_string

    start_time = time.time()
    logger.info("=== Archive request started ===")

    try:
        # Verify database configuration
        if not get_connection_string():
            error_msg = "Database connection not configured."
            logger.error(error_msg)
            return render_template('archive.html', bills=[], error_message=error_msg), 500

        # Get query parameters
        q = request.args.get('q', '').strip()
        status = request.args.get('status', 'all')
        try:
            page = int(request.args.get('page', 1))
            if page < 1: page = 1
        except ValueError:
            page = 1
        
        page_size = DEFAULT_ARCHIVE_PAGE_SIZE
        
        db_start = time.time()
        total_results = 0
        bills = []

        logger.info(f"Searching for query='{q}', status='{status}', page={page}")
        bills = search_tweeted_bills(q, status, page, page_size)
        total_results = count_search_tweeted_bills(q, status)

        db_time = time.time() - db_start
        logger.info(f"Database query completed in {db_time:.3f}s, found {total_results} total results.")

        # Calculate pagination
        total_pages = math.ceil(total_results / page_size) if total_results > 0 else 1
        if page > total_pages:
            page = total_pages

        # Add teen impact score to each bill
        for bill in bills:
            summary = bill.get('summary_detailed', '')
            bill['teen_impact_score'] = extract_teen_impact_score(summary)

        render_start = time.time()
        response = render_template(
            'archive.html',
            bills=bills,
            q=q,
            status_filter=status,
            current_page=page,
            total_pages=total_pages,
            total_results=total_results,
            page_size=page_size
        )
        render_time = time.time() - render_start
        total_time = time.time() - start_time
        
        logger.info(f"Template rendered in {render_time:.3f}s")
        logger.info(f"=== Archive request completed in {total_time:.3f}s ===")
        return response

    except Exception as e:
        error_msg = f"Failed to load archive: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return render_template('archive.html', bills=[], error_message=error_msg), 500

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
@limiter.limit("10 per minute")
@csrf.exempt
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
@csrf.exempt
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
    from src.load_env import load_env
    load_env()  # Manually load .env using custom function
    os.environ['FLASK_SKIP_DOTENV'] = '1'  # Skip Flask's auto dotenv loading to avoid timeout
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
