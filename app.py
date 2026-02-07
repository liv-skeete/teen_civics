#!/usr/bin/env python3
"""
Flask web application for TeenCivics.
Provides routes for displaying bills, an archive, and other static pages.
"""

import re
import json
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

import logging
from logging.handlers import RotatingFileHandler
import os
import secrets

from flask import Flask, render_template, request, jsonify, abort, g, send_from_directory
from markupsafe import Markup, escape
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect, CSRFError

# Import configuration system
from src.config import get_config
config = get_config()

# ---- Logging (handlers set once; Gunicorn will fork workers after import) ----
root_logger = logging.getLogger()
if not root_logger.handlers:
    logging.basicConfig(
        level=getattr(logging, config.logging.level),
        format=config.logging.format,
        handlers=[logging.StreamHandler()],
    )
logger = logging.getLogger(__name__)

# Add file handler if specified in config
if config.logging.file_path:
    log_dir = os.path.dirname(config.logging.file_path)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir)
    file_handler = RotatingFileHandler(
        config.logging.file_path, maxBytes=5 * 1024 * 1024, backupCount=2
    )
    file_handler.setFormatter(logging.Formatter(config.logging.format))
    logging.getLogger().addHandler(file_handler)
    logger.info(f"Logging configured to file: {config.logging.file_path}")

# ---- Flask app ----
app = Flask(__name__)
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
app.config["DEBUG"] = config.flask.debug

# SECRET_KEY: prefer FLASK_SECRET_KEY then SECRET_KEY, otherwise generate (dev)
app.config["SECRET_KEY"] = (
    os.getenv("FLASK_SECRET_KEY")
    or os.getenv("SECRET_KEY")
    or secrets.token_hex(32)
)
if not (os.getenv("FLASK_SECRET_KEY") or os.getenv("SECRET_KEY")):
    logger.warning("SECRET_KEY not set in environment, using generated key (not suitable for production)")

# Session security
app.config["SESSION_COOKIE_SECURE"] = not config.flask.debug
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

# CSRF + rate limiting
csrf = CSRFProtect(app)
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://",
)

# --- Constants ---
DEFAULT_ARCHIVE_PAGE_SIZE = 24

# --- Import database functions (after app initialized) ---
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
from src.processors.summarizer import summarize_title
from src.utils.sponsor_formatter import format_sponsor_sentence

# --- Request ID + security headers ---
@app.before_request
def _reqid_start():
    g._start = time.time()
    g.req_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())

@app.after_request
def add_security_headers(response):
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://www.googletagmanager.com https://static.cloudflareinsights.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "connect-src 'self' https://www.google-analytics.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data: https:; "
        "frame-ancestors 'self';"
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    if not config.flask.debug:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    if hasattr(g, "req_id"):
        response.headers["X-Request-ID"] = g.req_id
    if request.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response

# --- Context processors ---
@app.context_processor
def inject_ga_measurement_id():
    return dict(ga_measurement_id=config.flask.ga_measurement_id)

@app.context_processor
def inject_current_year():
    return {"current_year": datetime.now(timezone.utc).year}

# --- Jinja filters ---
@app.template_filter("format_date")
def format_date_filter(date_str: Optional[str]) -> str:
    if not date_str:
        return "Not available"
    try:
        if "T" in date_str:
            date_obj = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        else:
            date_obj = datetime.strptime(date_str, "%Y-%m-%d")
        return date_obj.strftime("%B %d, %Y")
    except (ValueError, TypeError):
        return date_str

@app.template_filter("format_datetime_simple")
def format_datetime_simple_filter(date_str: Optional[str]) -> str:
    if not date_str:
        return "Not available"
    try:
        if isinstance(date_str, str):
            if "T" in date_str:
                date_part = date_str.split(".")[0] if "." in date_str else date_str
                if "+" in date_part:
                    date_part = date_part.split("+")[0]
                if date_part.endswith("Z"):
                    date_part = date_part[:-1]
                date_obj = datetime.fromisoformat(date_part)
            elif "+" in date_str:
                date_part = date_str.split("+")[0]
                date_obj = datetime.fromisoformat(date_part)
            elif (
                len(date_str) == 19
                and date_str[4] == "-"
                and date_str[7] == "-"
                and date_str[10] == " "
                and date_str[13] == ":"
                and date_str[16] == ":"
            ):
                return date_str
            else:
                try:
                    date_obj = datetime.fromisoformat(date_str)
                except ValueError:
                    if "T" in date_str:
                        fixed_str = date_str.replace("T", " ")
                        if "+" in fixed_str:
                            fixed_str = fixed_str.split("+")[0]
                        date_obj = datetime.fromisoformat(fixed_str)
                    else:
                        if "+" in date_str:
                            date_part = date_str.split("+")[0]
                            date_obj = datetime.fromisoformat(date_part)
                        else:
                            raise
            return date_obj.strftime("%Y-%m-%d %H:%M:%S (UTC)")
        else:
            return date_str.strftime("%Y-%m-%d %H:%M:%S (UTC)")
    except (ValueError, TypeError) as e:
        logger.debug(f"Date formatting error for '{date_str}': {e}")
        return str(date_str) if date_str else "Not available"

@app.template_filter("format_status")
def format_status_filter(status: str) -> str:
    return (status or "").replace("_", " ").title()

@app.template_filter("generate_congress_url")
def generate_congress_url(bill_id: str, congress_session: str = "") -> str:
    if not bill_id:
        return "https://www.congress.gov/"
    if not congress_session:
        return f"https://www.congress.gov/search?q={bill_id}"
    try:
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
        bill_type = bill_number = full_type = None
        for prefix, congress_type in patterns.items():
            if bid.startswith(prefix):
                remainder = bid[len(prefix):]
                import re as _re
                number_match = _re.match(r"^(\d+)", remainder)
                if number_match:
                    bill_type = prefix
                    bill_number = number_match.group(1)
                    full_type = congress_type
                    break
        if not bill_type or not bill_number or not full_type:
            return f"https://www.congress.gov/search?q={bill_id}"
        try:
            congress_int = int(str(congress_session).strip())
            bill_num_int = int(bill_number)
        except Exception:
            return f"https://www.congress.gov/search?q={bill_id}"
        return f"https://www.congress.gov/bill/{congress_int}th-congress/{full_type}/{bill_num_int}"
    except Exception:
        return f"https://www.congress.gov/search?q={bill_id}"

@app.template_filter("from_json")
def from_json_filter(json_str):
    if not json_str:
        return None
    try:
        return json.loads(json_str)
    except (ValueError, TypeError, json.JSONDecodeError):
        return None

@app.template_filter("format_detailed_html")
def format_detailed_html_filter(text: str) -> Markup:
    if not text:
        return Markup("")
    text = text.replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n")
    # Strip markdown bold markers (**text** -> text)
    import re as _re
    text = _re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
    lines = text.split("\n")
    html_parts = []
    in_list = False
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if any(line.startswith(emoji) for emoji in ['🏠','💰','🛠️','⚖️','🚀','📌','👉','🔎','📝','🔑','📜','👥','💡']):
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            html_parts.append(f"<h4>{escape(line)}</h4>")
        elif line.startswith('•') or line.startswith('-'):
            if not in_list:
                html_parts.append("<ul>")
                in_list = True
            text_content = line[1:].strip()
            html_parts.append(f"<li>{escape(text_content)}</li>")
        else:
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            html_parts.append(f"<p>{escape(line)}</p>")
    if in_list:
        html_parts.append("</ul>")
    return Markup("\n".join(html_parts))

def _truncate_title_at_word_boundary(text: str, max_length: int) -> str:
    if not text:
        return ""
    if len(text) <= max_length:
        return text
    truncated = text[:max_length]
    last_space = truncated.rfind(" ")
    if last_space != -1 and last_space >= int(max_length * 0.6):
        truncated = truncated[:last_space]
    return truncated.rstrip() + "…"

@app.template_filter("shorten_title")
def shorten_title_filter(title: str, max_length: int = 150) -> str:
    """
    Deterministic title shortener: never calls external services.
    - If title length <= max_length: return original.
    - If max_length <= 0: return full title (no truncation).
    - Else: truncate cleanly at a word boundary with an ellipsis.
    """
    if not title:
        return ""
    if max_length is None:
        max_length = 150
    if max_length <= 0:
        return title
    if len(title) <= max_length:
        return title
    return _truncate_title_at_word_boundary(title, max_length)

@app.template_filter("format_sponsor_sentence")
def format_sponsor_sentence_filter(raw_sponsor: str) -> str:
    """
    Format a raw sponsor string into a teen-friendly sentence.
    E.g., "Rep. Estes, Ron [R-KS-4]" -> "Sponsored by Representative Ron Estes, a Republican from Kansas's 4th District."
    """
    return format_sponsor_sentence(raw_sponsor)

def extract_teen_impact_score(summary: str) -> Optional[int]:
    if not summary:
        return None
    import re as _re
    match = _re.search(r"teen\s+impact\s+score:\s*(\d+)/10", summary, _re.IGNORECASE)
    if match:
        try:
            score = int(match.group(1))
            if 0 <= score <= 10:
                return score
        except (ValueError, IndexError):
            pass
    return None

# --- Routes ---
@app.route("/")
def index():
    start_time = time.time()
    logger.info("=== Homepage request started ===")
    try:
        db_start = time.time()
        latest_bill = get_latest_tweeted_bill() or get_latest_bill()
        db_time = time.time() - db_start
        logger.info(f"Database query completed in {db_time:.3f}s")
        if not latest_bill:
            logger.warning("No bills found in database")
            return render_template("index.html", bill=None)
        render_start = time.time()
        response = render_template("index.html", bill=latest_bill)
        render_time = time.time() - render_start
        total_time = time.time() - start_time
        logger.info(f"Template rendered in {render_time:.3f}s")
        logger.info(f"=== Homepage request completed in {total_time:.3f}s ===")
        return response
    except Exception as e:
        logger.error(f"Error loading homepage: {e}", exc_info=True)
        return render_template("index.html", bill=None, error="Unable to load the latest bill. Please try again later.")

@app.route("/archive")
def archive():
    """
    Archive page route with search, filtering, and sorting capabilities.
    
    Query parameters:
    - q: Search query string
    - status: Bill status filter (default: 'all')
    - page: Current page number (default: 1)
    - sort_by_impact: Sort by teen impact score (1/true/on/yes or 0)
    
    Returns optimized, paginated bill results with proper error handling.
    """
    import math
    from src.database.connection import get_connection_string
    
    start_time = time.time()
    logger.info("=== Archive request started ===")
    
    try:
        # Verify database connection
        if not get_connection_string():
            error_msg = "Database connection not configured."
            logger.error(error_msg)
            return render_template(
                "archive.html",
                bills=[],
                error_message=error_msg,
                q="",
                status_filter="all",
                current_page=1,
                total_pages=1,
                total_results=0,
                page_size=DEFAULT_ARCHIVE_PAGE_SIZE,
                sort_by_impact=False
            ), 500
        
        # Parse query parameters with validation
        q = request.args.get("q", "").strip()
        status = request.args.get("status", "all").strip()
        
        # Validate status parameter
        valid_statuses = [
            "all", "agreed_to_in_house", "agreed_to_in_senate", "became_law",
            "committee_consideration", "failed_house", "failed_senate",
            "introduced", "passed_house", "passed_senate",
            "referred_to_committee", "reported_by_committee", "vetoed"
        ]
        if status not in valid_statuses:
            logger.warning(f"Invalid status parameter: {status}")
            status = "all"
        
        # Parse page number safely with bounds checking
        try:
            page = int(request.args.get("page", 1))
            page = max(1, page)  # Ensure page is at least 1
        except (ValueError, TypeError):
            logger.warning(f"Invalid page parameter: {request.args.get('page')}")
            page = 1
        
        # Parse sort_by_impact parameter (multiple formats supported)
        sort_by_impact_param = request.args.get("sort_by_impact", "0").strip().lower()
        sort_by_impact = sort_by_impact_param in ("1", "true", "on", "yes")
        
        page_size = DEFAULT_ARCHIVE_PAGE_SIZE
        
        # Log request details for debugging
        logger.info(
            f"Archive query: q='{q}', status='{status}', "
            f"page={page}, sort_by_impact={sort_by_impact}"
        )
        
        # Execute database queries
        db_start = time.time()
        
        try:
            bills = search_tweeted_bills(
                q, status, page, page_size, sort_by_impact=sort_by_impact
            )
            total_results = count_search_tweeted_bills(q, status)
        except Exception as db_error:
            logger.error(f"Database query error: {db_error}", exc_info=True)
            return render_template(
                "archive.html",
                bills=[],
                error_message="Unable to retrieve bills. Please try again later.",
                q=q,
                status_filter=status,
                current_page=page,
                total_pages=1,
                total_results=0,
                page_size=page_size,
                sort_by_impact=sort_by_impact
            ), 500
        
        db_time = time.time() - db_start
        logger.info(
            f"Database query completed in {db_time:.3f}s, "
            f"found {total_results} total results, returned {len(bills)} bills"
        )
        
        # Calculate pagination with validation
        total_pages = math.ceil(total_results / page_size) if total_results > 0 else 1
        
        # Adjust page if it exceeds total pages
        if page > total_pages and total_pages > 0:
            logger.info(f"Page {page} exceeds total pages {total_pages}, adjusting")
            page = total_pages
        
        # Render template
        render_start = time.time()
        response = render_template(
            "archive.html",
            bills=bills,
            q=q,
            status_filter=status,
            current_page=page,
            total_pages=total_pages,
            total_results=total_results,
            page_size=page_size,
            sort_by_impact=sort_by_impact,
        )
        
        render_time = time.time() - render_start
        total_time = time.time() - start_time
        
        logger.info(f"Template rendered in {render_time:.3f}s")
        logger.info(f"=== Archive request completed in {total_time:.3f}s ===")
        
        return response
        
    except Exception as e:
        error_msg = f"Failed to load archive: {str(e)}"
        logger.error(error_msg, exc_info=True)
        
        # Return error page with proper fallback values
        return render_template(
            "archive.html",
            bills=[],
            error_message=error_msg,
            q=request.args.get("q", ""),
            status_filter=request.args.get("status", "all"),
            current_page=1,
            total_pages=1,
            total_results=0,
            page_size=DEFAULT_ARCHIVE_PAGE_SIZE,
            sort_by_impact=False
        ), 500

@app.route("/debug/env")
def debug_env():
    from src.database.connection import get_connection_string
    if not app.config.get("DEBUG"):
        abort(404)
    try:
        conn_string = get_connection_string()
        masked_conn = None
        if conn_string:
            masked_conn = (
                conn_string[:30] + "...[MASKED]..." + conn_string[-20:]
                if len(conn_string) > 50
                else conn_string[:10] + "...[MASKED]"
            )
        env_status = {
            "database_configured": conn_string is not None,
            "connection_string_preview": masked_conn,
            "environment_variables": {
                "DATABASE_URL": "SET" if os.environ.get("DATABASE_URL") else "NOT SET",
            },
            "working_directory": os.getcwd(),
            "python_path": os.environ.get("PYTHONPATH", "NOT SET"),
        }
        return jsonify(env_status)
    except Exception as e:
        return jsonify({"error": str(e), "error_type": type(e).__name__}), 500

@app.route("/bill/<string:slug>")
def bill_detail(slug: str):
    from werkzeug.exceptions import HTTPException
    try:
        bill = get_bill_by_slug(slug)
        if not bill:
            abort(404)
        return render_template("bill.html", bill=bill)
    except HTTPException:
        # Re-raise HTTP exceptions (404, etc) as-is, don't convert to 500
        raise
    except Exception as e:
        logger.error(f"Error loading bill with slug '{slug}': {e}", exc_info=True)
        abort(500)

@app.route("/about")
def about():
    return render_template("about.html")

@app.route("/contact")
def contact():
    return render_template("contact.html")

@app.route("/resources")
def resources():
    return render_template("resources.html")

@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static'),
                               'favicon.ico', mimetype='image/vnd.microsoft.icon')

@app.route('/robots.txt')
def robots_txt():
    return send_from_directory(os.path.dirname(os.path.abspath(__file__)), 'robots.txt')

@app.route('/sitemap.xml')
def sitemap_xml():
    return send_from_directory(os.path.dirname(os.path.abspath(__file__)), 'sitemap.xml')

@app.errorhandler(404)
def page_not_found(e):
    return render_template("404.html"), 404

@app.errorhandler(500)
def internal_server_error(e):
    return render_template("500.html"), 500

@app.errorhandler(CSRFError)
def handle_csrf_error(e):
    logger.warning(f"CSRF error on {request.path}: {e.description}")
    if request.path.startswith("/api/"):
        return jsonify({"error": "CSRF validation failed", "details": e.description}), 400
    return render_template("500.html"), 400

@app.route("/api/vote", methods=["POST"])
@limiter.limit("10 per minute")
@csrf.exempt
def record_vote():
    try:
        data = request.get_json()
        bill_id = data.get("bill_id")
        vote_type = data.get("vote_type")
        previous_vote = data.get("previous_vote")

        logger.info(
            "Vote attempt req_id=%s bill_id=%s vote_type=%s previous_vote=%s content_type=%s origin=%s",
            getattr(g, "req_id", "-"),
            bill_id,
            vote_type,
            previous_vote,
            request.headers.get("Content-Type"),
            request.headers.get("Origin"),
        )

        if not bill_id or vote_type not in ["yes", "no", "unsure"]:
            abort(400, description="Invalid request data")

        updated = update_poll_results(bill_id, vote_type, previous_vote)
        if not updated:
            abort(404, description="Bill not found or vote update failed")

        return jsonify({"success": True})
    except Exception as e:
        logger.error(f"Error recording vote: {e}", exc_info=True)
        abort(500, description="Internal server error")

@app.route("/api/poll-results/<string:bill_id>")
def get_poll_results(bill_id: str):
    try:
        bill = get_bill_by_id(bill_id)
        if not bill:
            abort(404, description="Bill not found")
        yes = int(bill.get("poll_results_yes", 0) or 0)
        no = int(bill.get("poll_results_no", 0) or 0)
        unsure = int(bill.get("poll_results_unsure", 0) or 0)
        total = yes + no + unsure
        results = {
            "yes_votes": yes,
            "no_votes": no,
            "unsure_votes": unsure,
            "total": total
        }
        return jsonify(results)
    except Exception as e:
        logger.error(f"Error getting poll results for bill '{bill_id}': {e}", exc_info=True)
        abort(500, description="Internal server error")

if __name__ == "__main__":
    if os.environ.get("RAILWAY_ENVIRONMENT"):
        logger.info("Running on Railway — skipping .env load.")
    else:
        try:
            from src.load_env import load_env
            load_env()
            logger.info(".env loaded for local development.")
        except ImportError:
            logger.info("No load_env module found, continuing.")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))