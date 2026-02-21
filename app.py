#!/usr/bin/env python3
"""
Flask web application for TeenCivics.
Provides routes for displaying bills and other static pages.
"""

import re
import json
import time
import uuid
import hmac
import math
import threading
import urllib.parse
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from functools import wraps

import logging
from logging.handlers import RotatingFileHandler
import os
import secrets
import requests

from flask import (
    Flask, render_template, request, jsonify, abort, g,
    send_from_directory, session, redirect, url_for, make_response,
)
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

# Support sub-path deployment (e.g. /beta on staging).
# Railway strips /beta from PATH_INFO before forwarding to Flask, so Flask
# routes work as normal (/api/vote, /static/...).  We just need url_for() to
# emit /beta/... URLs so the browser can find them.  Setting SCRIPT_NAME in
# the WSGI environ achieves this without touching Flask's routing.
# Set URL_PREFIX=/beta on the Railway staging service.
_url_prefix = os.environ.get('URL_PREFIX', '')
if _url_prefix:
    class _PrefixMiddleware:
        """Injects SCRIPT_NAME so url_for() generates sub-path-prefixed URLs."""
        def __init__(self, wsgi_app, prefix):
            self.app = wsgi_app
            self.prefix = prefix

        def __call__(self, environ, start_response):
            environ['SCRIPT_NAME'] = self.prefix
            # Railway already strips the prefix from PATH_INFO, so we only
            # strip it ourselves when it's still present (local testing).
            path = environ.get('PATH_INFO', '')
            if path.startswith(self.prefix):
                environ['PATH_INFO'] = path[len(self.prefix):] or '/'
            return self.app(environ, start_response)

    app.wsgi_app = _PrefixMiddleware(app.wsgi_app, _url_prefix)

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
# NOTE: With multiple Gunicorn workers, each worker has independent rate limit
# counters. To share state, switch to Redis: storage_uri="redis://..."
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
    search_and_count_bills,
    record_individual_vote,
    record_vote_and_update_poll,
    get_voter_votes,
    update_bill_arguments,
)
from src.processors.summarizer import summarize_title
from src.processors.argument_generator import generate_bill_arguments
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
    if request.path.startswith("/api/") or request.path.startswith("/admin/api/"):
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

# --- Health Check Routes (no DB, no auth, no rate limit) ---

@app.route("/healthz")
@csrf.exempt
@limiter.exempt
def healthz():
    """Health check endpoint - always responds quickly, no DB dependency."""
    return jsonify({"status": "ok", "timestamp": time.time()}), 200


@app.route("/healthz/db")
@csrf.exempt
@limiter.exempt
def healthz_db():
    """Deep health check that tests DB connectivity."""
    try:
        from src.database.connection import postgres_connect
        with postgres_connect() as conn:
            if conn is None:
                return jsonify({"status": "degraded", "db": "unreachable"}), 503
            cur = conn.cursor()
            cur.execute("SELECT 1")
            cur.close()
            return jsonify({"status": "ok", "db": "connected"}), 200
    except Exception as e:
        return jsonify({"status": "degraded", "db": str(e)}), 503


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
def archive_redirect():
    """Redirect old /archive URL to /bills for backward compatibility."""
    return redirect(url_for('bills', **request.args), code=301)

@app.route("/bills")
def bills():
    """
    Bills page route with search, filtering, and sorting capabilities.
    
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
    logger.info("=== Bills page request started ===")
    
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
            f"Bills query: q='{q}', status='{status}', "
            f"page={page}, sort_by_impact={sort_by_impact}"
        )
        
        # Execute database queries
        db_start = time.time()
        
        try:
            bills, total_results = search_and_count_bills(
                q, status, page, page_size, sort_by_impact=sort_by_impact
            )
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
        logger.info(f"=== Bills page request completed in {total_time:.3f}s ===")
        
        return response
        
    except Exception as e:
        error_msg = f"Failed to load bills page: {str(e)}"
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
        return render_template(
            "500.html",
            error_message="Unable to load this bill right now. The database may be temporarily unavailable. Please try again in a few minutes."
        ), 500

@app.route("/about")
def about():
    return render_template("about.html")

@app.route("/grants")
def grants():
    return render_template("grants.html")

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

@app.route('/privacy.html')
def privacy():
    return send_from_directory(os.path.dirname(os.path.abspath(__file__)), 'privacy.html')

@app.route('/robots.txt')
def robots_txt():
    return send_from_directory(os.path.dirname(os.path.abspath(__file__)), 'robots.txt')

@app.route('/sitemap.xml')
def sitemap_xml():
    return send_from_directory(os.path.dirname(os.path.abspath(__file__)), 'sitemap.xml')

# --- Admin Constants ---
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")
ADMIN_SESSION_TIMEOUT = 7200  # 2 hours in seconds
ADMIN_LOGIN_ATTEMPTS = {}  # IP -> [(timestamp, ...)]
_admin_login_lock = threading.Lock()
ADMIN_LOCKOUT_WINDOW = 3600  # 1 hour — entries older than this are pruned


def _prune_login_attempts() -> None:
    """Remove ADMIN_LOGIN_ATTEMPTS entries older than the lockout window.

    Must be called while holding _admin_login_lock.
    """
    cutoff = time.time() - ADMIN_LOCKOUT_WINDOW
    stale_ips = [
        ip for ip, attempts in ADMIN_LOGIN_ATTEMPTS.items()
        if all(ts < cutoff for ts in attempts)
    ]
    for ip in stale_ips:
        del ADMIN_LOGIN_ATTEMPTS[ip]

# Table whitelist to prevent accessing pg_catalog tables etc.
ADMIN_ALLOWED_TABLES = None  # populated dynamically from information_schema

# Fields that are safe to update via the admin UI
ADMIN_EDITABLE_FIELDS = {
    'title', 'short_title', 'status', 'normalized_status',
    'summary_overview', 'summary_detailed', 'summary_tweet', 'summary_long',
    'tags', 'teen_impact_score',
    'problematic', 'problem_reason',
    'sponsor_name', 'sponsor_party', 'sponsor_state',
    # Allow all columns for generic table editor
}

def _admin_enabled():
    """Check if admin feature is enabled (ADMIN_PASSWORD is set)."""
    return bool(ADMIN_PASSWORD)

def admin_required(f):
    """Decorator that checks admin authentication. Returns 404 if admin is disabled."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not _admin_enabled():
            abort(404)
        if not session.get("admin_authenticated"):
            return redirect(url_for("admin_login"))
        # Session timeout check
        login_time = session.get("admin_login_time")
        if login_time:
            elapsed = time.time() - login_time
            if elapsed > ADMIN_SESSION_TIMEOUT:
                session.pop("admin_authenticated", None)
                session.pop("admin_login_time", None)
                return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return decorated

# --- Admin Routes ---

@app.route("/admin")
def admin_dashboard():
    if not _admin_enabled():
        abort(404)
    if not session.get("admin_authenticated"):
        return redirect(url_for("admin_login"))
    # Session timeout check
    login_time = session.get("admin_login_time")
    if login_time and (time.time() - login_time) > ADMIN_SESSION_TIMEOUT:
        session.pop("admin_authenticated", None)
        session.pop("admin_login_time", None)
        return redirect(url_for("admin_login"))
    try:
        from src.database.connection import postgres_connect
        import psycopg2.extras
        with postgres_connect() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT COUNT(*) as cnt FROM bills")
                total_bills = cur.fetchone()["cnt"]
                cur.execute("""
                    SELECT COUNT(*) as cnt FROM bills
                    WHERE last_edited_at IS NOT NULL
                    AND last_edited_at != ''
                    AND last_edited_at::timestamp > NOW() - INTERVAL '7 days'
                """)
                recently_edited = cur.fetchone()["cnt"]
                cur.execute("""
                    SELECT bill_id, title, last_edited_at, last_edited_by
                    FROM bills
                    WHERE last_edited_at IS NOT NULL
                    AND last_edited_at != ''
                    ORDER BY last_edited_at::timestamp DESC
                    LIMIT 10
                """)
                recent_edits = cur.fetchall()
        return render_template("admin/dashboard.html",
                               total_bills=total_bills,
                               recently_edited=recently_edited,
                               recent_edits=recent_edits)
    except Exception as e:
        logger.error(f"Admin dashboard error: {e}", exc_info=True)
        return render_template("admin/dashboard.html",
                               total_bills=0, recently_edited=0, recent_edits=[])

@app.route("/admin/login", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def admin_login():
    if not _admin_enabled():
        abort(404)
    if request.method == "GET":
        if session.get("admin_authenticated"):
            return redirect(url_for("admin_dashboard"))
        return render_template("admin/login.html", error=None)
    # POST — prune stale login-attempt entries before processing
    with _admin_login_lock:
        _prune_login_attempts()
    password = request.form.get("password", "")
    if hmac.compare_digest(password, ADMIN_PASSWORD):
        session["admin_authenticated"] = True
        session["admin_login_time"] = time.time()
        logger.info("Admin login successful from %s", get_remote_address())
        return redirect(url_for("admin_dashboard"))
    else:
        logger.warning("Admin login failed from %s", get_remote_address())
        return render_template("admin/login.html", error="Incorrect password."), 401

@app.route("/admin/logout")
def admin_logout():
    if not _admin_enabled():
        abort(404)
    session.pop("admin_authenticated", None)
    session.pop("admin_login_time", None)
    return redirect(url_for("index"))

# --- Admin: Table Browser Routes ---

@app.route("/admin/tables")
@admin_required
def admin_tables():
    try:
        from src.database.connection import postgres_connect
        import psycopg2.extras
        with postgres_connect() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT table_name FROM information_schema.tables
                    WHERE table_schema = 'public'
                    ORDER BY table_name
                """)
                tables = [row["table_name"] for row in cur.fetchall()]
        return render_template("admin/tables.html", tables=tables)
    except Exception as e:
        logger.error(f"Admin tables error: {e}", exc_info=True)
        return render_template("admin/tables.html", tables=[])

@app.route("/admin/tables/<table_name>/rows")
@admin_required
def admin_table_rows(table_name):
    try:
        from src.database.connection import postgres_connect
        import psycopg2.extras
        import psycopg2.sql

        page = max(1, int(request.args.get("page", 1)))
        per_page = min(100, max(10, int(request.args.get("per_page", 50))))
        offset = (page - 1) * per_page

        with postgres_connect() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                # Validate table exists in public schema
                cur.execute("""
                    SELECT table_name FROM information_schema.tables
                    WHERE table_schema = 'public' AND table_name = %s
                """, (table_name,))
                if not cur.fetchone():
                    abort(404)

                # Get schema
                cur.execute("""
                    SELECT column_name, data_type
                    FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = %s
                    ORDER BY ordinal_position
                """, (table_name,))
                schema = cur.fetchall()
                columns = [col["column_name"] for col in schema]

                # Count rows
                cur.execute(
                    psycopg2.sql.SQL("SELECT COUNT(*) as cnt FROM {}").format(
                        psycopg2.sql.Identifier(table_name)
                    )
                )
                total_rows = cur.fetchone()["cnt"]
                total_pages = math.ceil(total_rows / per_page) if total_rows > 0 else 1

                # Get rows
                cur.execute(
                    psycopg2.sql.SQL("SELECT * FROM {} ORDER BY id DESC LIMIT %s OFFSET %s").format(
                        psycopg2.sql.Identifier(table_name)
                    ),
                    (per_page, offset)
                )
                rows = cur.fetchall()

        return render_template("admin/table_rows.html",
                               table_name=table_name,
                               schema=schema,
                               columns=columns,
                               rows=rows,
                               page=page,
                               per_page=per_page,
                               total_rows=total_rows,
                               total_pages=total_pages)
    except Exception as e:
        logger.error(f"Admin table rows error: {e}", exc_info=True)
        abort(500)

@app.route("/admin/tables/<table_name>/rows/<int:row_id>/edit")
@admin_required
def admin_edit_row(table_name, row_id):
    try:
        from src.database.connection import postgres_connect
        import psycopg2.extras
        import psycopg2.sql

        with postgres_connect() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                # Validate table exists
                cur.execute("""
                    SELECT table_name FROM information_schema.tables
                    WHERE table_schema = 'public' AND table_name = %s
                """, (table_name,))
                if not cur.fetchone():
                    abort(404)

                # Get schema
                cur.execute("""
                    SELECT column_name, data_type
                    FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = %s
                    ORDER BY ordinal_position
                """, (table_name,))
                schema = cur.fetchall()

                # Get row
                cur.execute(
                    psycopg2.sql.SQL("SELECT * FROM {} WHERE id = %s").format(
                        psycopg2.sql.Identifier(table_name)
                    ),
                    (row_id,)
                )
                row = cur.fetchone()
                if not row:
                    abort(404)

        return render_template("admin/edit_row.html",
                               table_name=table_name,
                               row_id=row_id,
                               schema=schema,
                               row=row)
    except Exception as e:
        logger.error(f"Admin edit row error: {e}", exc_info=True)
        abort(500)

# --- Admin: Bills Routes ---

@app.route("/admin/bills")
@admin_required
def admin_bills():
    try:
        from src.database.connection import postgres_connect
        import psycopg2.extras

        page = max(1, int(request.args.get("page", 1)))
        per_page = 25
        offset = (page - 1) * per_page
        q = request.args.get("q", "").strip()
        status_filter = request.args.get("status", "all").strip()

        with postgres_connect() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                # Build query
                where_clauses = []
                params = []
                if q:
                    where_clauses.append("(bill_id ILIKE %s OR title ILIKE %s)")
                    params.extend([f"%{q}%", f"%{q}%"])
                if status_filter and status_filter != "all":
                    where_clauses.append("(status = %s OR normalized_status = %s)")
                    params.extend([status_filter, status_filter])

                where_sql = ""
                if where_clauses:
                    where_sql = "WHERE " + " AND ".join(where_clauses)

                # Count
                cur.execute(f"SELECT COUNT(*) as cnt FROM bills {where_sql}", params)
                total_bills = cur.fetchone()["cnt"]
                total_pages = math.ceil(total_bills / per_page) if total_bills > 0 else 1

                # Get bills
                cur.execute(
                    f"""SELECT id, bill_id, title, status, normalized_status,
                               subject_tags, hidden,
                               last_edited_at, last_edited_by
                        FROM bills {where_sql}
                        ORDER BY date_processed DESC NULLS LAST
                        LIMIT %s OFFSET %s""",
                    params + [per_page, offset]
                )
                bills = cur.fetchall()

        return render_template("admin/bills.html",
                               bills=bills,
                               page=page,
                               total_pages=total_pages,
                               total_bills=total_bills,
                               q=q,
                               status_filter=status_filter)
    except Exception as e:
        logger.error(f"Admin bills error: {e}", exc_info=True)
        return render_template("admin/bills.html",
                               bills=[], page=1, total_pages=1,
                               total_bills=0, q="", status_filter="all")

@app.route("/admin/bills/<bill_id>/summary")
@admin_required
def admin_bill_summary(bill_id):
    try:
        from src.database.connection import postgres_connect
        import psycopg2.extras

        with postgres_connect() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT * FROM bills WHERE bill_id = %s", (bill_id,))
                bill = cur.fetchone()
                if not bill:
                    abort(404)

        return render_template("admin/bill_summary.html", bill=bill)
    except Exception as e:
        logger.error(f"Admin bill summary error: {e}", exc_info=True)
        abort(500)

# --- Admin API Routes ---

@app.route("/admin/api/sync-contact-forms", methods=["POST"])
@admin_required
def admin_sync_contact_forms():
    """Trigger manual sync of rep contact form URLs."""
    try:
        from src.fetchers.contact_form_sync import sync_contact_forms
        result = sync_contact_forms()
        return jsonify({"success": True, "results": result})
    except Exception as e:
        logger.error(f"Contact form sync error: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/admin/api/tables")
@admin_required
def admin_api_tables():
    try:
        from src.database.connection import postgres_connect
        import psycopg2.extras
        with postgres_connect() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT table_name FROM information_schema.tables
                    WHERE table_schema = 'public'
                    ORDER BY table_name
                """)
                tables = [row["table_name"] for row in cur.fetchall()]
        return jsonify({"tables": tables})
    except Exception as e:
        logger.error(f"Admin API tables error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

@app.route("/admin/api/tables/<table_name>/schema")
@admin_required
def admin_api_table_schema(table_name):
    try:
        from src.database.connection import postgres_connect
        import psycopg2.extras
        with postgres_connect() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT table_name FROM information_schema.tables
                    WHERE table_schema = 'public' AND table_name = %s
                """, (table_name,))
                if not cur.fetchone():
                    return jsonify({"error": "Table not found"}), 404
                cur.execute("""
                    SELECT column_name, data_type, is_nullable, column_default
                    FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = %s
                    ORDER BY ordinal_position
                """, (table_name,))
                schema = cur.fetchall()
        return jsonify({"table": table_name, "columns": schema})
    except Exception as e:
        logger.error(f"Admin API schema error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

@app.route("/admin/api/tables/<table_name>/rows")
@admin_required
def admin_api_table_rows(table_name):
    try:
        from src.database.connection import postgres_connect
        import psycopg2.extras
        import psycopg2.sql

        page = max(1, int(request.args.get("page", 1)))
        per_page = min(100, max(1, int(request.args.get("per_page", 50))))
        offset = (page - 1) * per_page

        with postgres_connect() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT table_name FROM information_schema.tables
                    WHERE table_schema = 'public' AND table_name = %s
                """, (table_name,))
                if not cur.fetchone():
                    return jsonify({"error": "Table not found"}), 404

                cur.execute(
                    psycopg2.sql.SQL("SELECT COUNT(*) as cnt FROM {}").format(
                        psycopg2.sql.Identifier(table_name)
                    )
                )
                total = cur.fetchone()["cnt"]

                cur.execute(
                    psycopg2.sql.SQL("SELECT * FROM {} ORDER BY id DESC LIMIT %s OFFSET %s").format(
                        psycopg2.sql.Identifier(table_name)
                    ),
                    (per_page, offset)
                )
                rows = cur.fetchall()

        # Convert non-serializable types
        for row in rows:
            for key, val in row.items():
                if isinstance(val, datetime):
                    row[key] = val.isoformat()

        return jsonify({
            "table": table_name,
            "rows": rows,
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": math.ceil(total / per_page) if total > 0 else 1
        })
    except Exception as e:
        logger.error(f"Admin API rows error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

@app.route("/admin/api/rows/<table_name>/<int:row_id>", methods=["GET"])
@admin_required
def admin_api_get_row(table_name, row_id):
    try:
        from src.database.connection import postgres_connect
        import psycopg2.extras
        import psycopg2.sql

        with postgres_connect() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT table_name FROM information_schema.tables
                    WHERE table_schema = 'public' AND table_name = %s
                """, (table_name,))
                if not cur.fetchone():
                    return jsonify({"error": "Table not found"}), 404

                cur.execute(
                    psycopg2.sql.SQL("SELECT * FROM {} WHERE id = %s").format(
                        psycopg2.sql.Identifier(table_name)
                    ),
                    (row_id,)
                )
                row = cur.fetchone()
                if not row:
                    return jsonify({"error": "Row not found"}), 404

        # Convert non-serializable types
        for key, val in row.items():
            if isinstance(val, datetime):
                row[key] = val.isoformat()

        return jsonify({"table": table_name, "row": row})
    except Exception as e:
        logger.error(f"Admin API get row error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

@app.route("/admin/api/rows/<table_name>/<int:row_id>", methods=["PUT"])
@admin_required
def admin_api_update_row(table_name, row_id):
    try:
        from src.database.connection import postgres_connect
        import psycopg2.extras
        import psycopg2.sql

        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400

        with postgres_connect() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                # Validate table exists
                cur.execute("""
                    SELECT table_name FROM information_schema.tables
                    WHERE table_schema = 'public' AND table_name = %s
                """, (table_name,))
                if not cur.fetchone():
                    return jsonify({"error": "Table not found"}), 404

                # Get valid columns for this table
                cur.execute("""
                    SELECT column_name, data_type
                    FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = %s
                """, (table_name,))
                valid_columns = {row["column_name"]: row["data_type"] for row in cur.fetchall()}

                # Filter to only valid columns (exclude id, created_at, etc.)
                read_only_columns = {'id', 'created_at', 'updated_at', 'date_processed'}
                update_fields = {}
                for key, val in data.items():
                    if key in valid_columns and key not in read_only_columns:
                        # Type coercion
                        col_type = valid_columns[key]
                        if col_type == 'boolean':
                            val = val in (True, 'true', 'True', '1', 1)
                        elif col_type == 'integer' and val != '' and val is not None:
                            try:
                                val = int(val)
                            except (ValueError, TypeError):
                                pass
                        elif val == '':
                            val = None
                        update_fields[key] = val

                if not update_fields:
                    return jsonify({"error": "No valid fields to update"}), 400

                # For the bills table, auto-set last_edited_at and last_edited_by
                if table_name == 'bills':
                    update_fields['last_edited_at'] = datetime.now(timezone.utc).isoformat()
                    update_fields['last_edited_by'] = 'Liv'

                # Build UPDATE query safely
                set_clauses = []
                values = []
                for col, val in update_fields.items():
                    set_clauses.append(
                        psycopg2.sql.SQL("{} = %s").format(psycopg2.sql.Identifier(col))
                    )
                    values.append(val)
                values.append(row_id)

                query = psycopg2.sql.SQL("UPDATE {} SET {} WHERE id = %s").format(
                    psycopg2.sql.Identifier(table_name),
                    psycopg2.sql.SQL(", ").join(set_clauses)
                )
                cur.execute(query, values)

        logger.info(f"Admin updated {table_name} row {row_id}: fields={list(update_fields.keys())}")
        return jsonify({
            "success": True,
            "updated_fields": list(update_fields.keys())
        })
    except Exception as e:
        logger.error(f"Admin API update row error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

@app.route("/admin/api/bills/<int:bill_id>/hide", methods=["POST"])
@admin_required
def admin_api_hide_bill(bill_id):
    """Soft-delete (hide) or unhide a bill. Expects JSON {"hidden": true/false}."""
    try:
        from src.database.connection import postgres_connect
        import psycopg2.extras

        data = request.get_json() or {}
        hidden = data.get("hidden", True)
        if hidden not in (True, False):
            hidden = bool(hidden)

        with postgres_connect() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """UPDATE bills
                       SET hidden = %s,
                           last_edited_at = %s,
                           last_edited_by = 'Liv'
                       WHERE id = %s
                       RETURNING bill_id, hidden""",
                    (hidden, datetime.now(timezone.utc).isoformat(), bill_id),
                )
                row = cur.fetchone()
                if not row:
                    return jsonify({"error": "Bill not found"}), 404

        action = "hidden" if hidden else "unhidden"
        logger.info(f"Admin {action} bill id={bill_id} (bill_id={row['bill_id']})")
        return jsonify({"success": True, "bill_id": row["bill_id"], "hidden": hidden})
    except Exception as e:
        logger.error(f"Admin hide bill error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

@app.errorhandler(404)
def page_not_found(e):
    return render_template("404.html"), 404

@app.errorhandler(500)
def internal_server_error(e):
    return render_template("500.html"), 500

@app.errorhandler(CSRFError)
def handle_csrf_error(e):
    logger.warning(f"CSRF error on {request.path}: {e.description}")
    if request.path.startswith("/api/") or request.path.startswith("/admin/api/"):
        return jsonify({"error": "CSRF validation failed", "details": e.description}), 400
    return render_template("500.html"), 400

def _get_or_create_voter_id():
    """
    Get the voter_id from the request cookie, or generate a new UUID4.
    Returns (voter_id, is_new) tuple.
    """
    voter_id = request.cookies.get("voter_id")
    if voter_id:
        return voter_id, False
    return str(uuid.uuid4()), True


def _set_voter_cookie(response, voter_id):
    """
    Set the voter_id cookie on a response object.
    Uses secure=True only in production environments.
    """
    is_production = (
        os.environ.get("RAILWAY_ENVIRONMENT") is not None
        or os.environ.get("FLASK_ENV") == "production"
        or request.is_secure
    )
    response.set_cookie(
        "voter_id",
        voter_id,
        max_age=63072000,  # 2 years
        httponly=True,
        samesite="Lax",
        secure=is_production,
    )
    return response


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

        # Combined: update poll aggregates + record individual vote in one DB connection
        voter_id, _is_new = _get_or_create_voter_id()
        updated = record_vote_and_update_poll(bill_id, vote_type, voter_id, previous_vote)
        if not updated:
            abort(404, description="Bill not found or vote update failed")

        response = make_response(jsonify({"success": True, "voter_id": voter_id}))
        _set_voter_cookie(response, voter_id)
        return response
    except Exception as e:
        logger.error(f"Error recording vote: {e}", exc_info=True)
        abort(500, description="Internal server error")


@app.route("/api/my-votes")
@limiter.limit("30 per minute")
def get_my_votes():
    """Return all votes for the current voter as a bill_id -> vote_type mapping."""
    try:
        voter_id = request.cookies.get("voter_id")
        if not voter_id:
            return jsonify({"votes": {}})

        vote_records = get_voter_votes(voter_id)
        votes_dict = {v["bill_id"]: v["vote_type"] for v in vote_records}

        response = make_response(jsonify({"votes": votes_dict}))
        _set_voter_cookie(response, voter_id)
        return response
    except Exception as e:
        logger.error(f"Error retrieving voter votes: {e}", exc_info=True)
        abort(500, description="Internal server error")

@app.route("/api/poll-results/<string:bill_id>")
def get_poll_results(bill_id: str):
    try:
        bill = get_bill_by_id(bill_id)
        if not bill:
            abort(404, description="Bill not found")
        yes = int(bill.get("poll_results_yes", 0) or 0)
        no = int(bill.get("poll_results_no", 0) or 0)
        total = yes + no
        results = {
            "yes_votes": yes,
            "no_votes": no,
            "total": total
        }
        return jsonify(results)
    except Exception as e:
        logger.error(f"Error getting poll results for bill '{bill_id}': {e}", exc_info=True)
        abort(500, description="Internal server error")

# --- Tell Your Rep: Constants & Cache ---

# State FIPS code to abbreviation mapping
FIPS_TO_STATE = {
    "01": "AL", "02": "AK", "04": "AZ", "05": "AR", "06": "CA",
    "08": "CO", "09": "CT", "10": "DE", "11": "DC", "12": "FL",
    "13": "GA", "15": "HI", "16": "ID", "17": "IL", "18": "IN",
    "19": "IA", "20": "KS", "21": "KY", "22": "LA", "23": "ME",
    "24": "MD", "25": "MA", "26": "MI", "27": "MN", "28": "MS",
    "29": "MO", "30": "MT", "31": "NE", "32": "NV", "33": "NH",
    "34": "NJ", "35": "NM", "36": "NY", "37": "NC", "38": "ND",
    "39": "OH", "40": "OK", "41": "OR", "42": "PA", "44": "RI",
    "45": "SC", "46": "SD", "47": "TN", "48": "TX", "49": "UT",
    "50": "VT", "51": "VA", "53": "WA", "54": "WV", "55": "WI",
    "56": "WY", "60": "AS", "66": "GU", "69": "MP", "72": "PR",
    "78": "VI",
}

# In-memory rep cache: key = "STATE-DISTRICT" -> { "data": {...}, "timestamp": float }
_rep_cache: Dict[str, Dict[str, Any]] = {}
_rep_cache_lock = threading.Lock()
REP_CACHE_TTL = 86400  # 24 hours
REP_CACHE_MAX_SIZE = 256


def _get_cached_rep(state: str, district: int) -> Optional[Dict]:
    """Return cached rep data if still fresh, else None."""
    key = f"{state}-{district}"
    with _rep_cache_lock:
        entry = _rep_cache.get(key)
    if entry and time.time() - entry["timestamp"] < REP_CACHE_TTL:
        return entry["data"]
    return None


def _evict_rep_cache() -> None:
    """Evict expired entries from _rep_cache; clear entirely if still over limit.

    Must be called while holding _rep_cache_lock.
    """
    now = time.time()
    expired_keys = [
        k for k, v in _rep_cache.items()
        if now - v["timestamp"] >= REP_CACHE_TTL
    ]
    for k in expired_keys:
        del _rep_cache[k]
    # If still over the limit after removing expired entries, clear everything
    if len(_rep_cache) >= REP_CACHE_MAX_SIZE:
        _rep_cache.clear()


def _set_cached_rep(state: str, district: int, data: Dict) -> None:
    """Cache rep data with current timestamp, enforcing a max size limit."""
    key = f"{state}-{district}"
    with _rep_cache_lock:
        if len(_rep_cache) >= REP_CACHE_MAX_SIZE:
            _evict_rep_cache()
        _rep_cache[key] = {"data": data, "timestamp": time.time()}


# --- Tell Your Rep: API Routes ---

@app.route("/api/zip-lookup", methods=["POST"])
@limiter.limit("10 per minute")
@csrf.exempt
def zip_lookup():
    """Look up congressional district(s) from a ZIP code using Census Geocoder."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400

        zip_code = str(data.get("zip", "")).strip()
        if not re.match(r"^\d{5}$", zip_code):
            return jsonify({"error": "Invalid ZIP code. Please enter a 5-digit ZIP code."}), 400

        # Two-step approach:
        # Step 1: Geocode ZIP → lat/lon using Nominatim (OpenStreetMap)
        #   (Census geocoder requires a real street address; bare ZIPs fail)
        # Step 2: Use Census coordinates endpoint → congressional district
        #   (This endpoint reliably returns the correct CD for any lat/lon)

        coordinates = None

        # Geocode ZIP using Nominatim (OpenStreetMap) — works with bare ZIP codes
        nominatim_url = (
            f"https://nominatim.openstreetmap.org/search"
            f"?postalcode={zip_code}&country=US&format=json&limit=1"
        )
        try:
            resp = requests.get(nominatim_url, timeout=5, headers={
                "User-Agent": "TeenCivics/1.0 (civic education platform)"
            })
            resp.raise_for_status()
            nom_data = resp.json()
            if nom_data and len(nom_data) > 0:
                lat = nom_data[0].get("lat")
                lon = nom_data[0].get("lon")
                if lat and lon:
                    coordinates = (float(lon), float(lat))  # Census uses x=lon, y=lat
        except Exception as e:
            logger.warning(f"Nominatim geocode error for ZIP {zip_code}: {e}")

        # Fallback: try Census structured address geocoder
        if not coordinates:
            census_geo_url = (
                "https://geocoding.geo.census.gov/geocoder/locations/address"
                f"?street=1+Main+St&zip={zip_code}"
                "&benchmark=Public_AR_Current&format=json"
            )
            try:
                resp2 = requests.get(census_geo_url, timeout=8)
                resp2.raise_for_status()
                geo_data2 = resp2.json()
                matches2 = geo_data2.get("result", {}).get("addressMatches", [])
                if matches2:
                    coords = matches2[0].get("coordinates", {})
                    if coords.get("x") and coords.get("y"):
                        coordinates = (coords["x"], coords["y"])
            except Exception as e:
                logger.debug(f"Census geocode fallback for ZIP {zip_code}: {e}")

        if not coordinates:
            return jsonify({
                "error": "Could not locate this ZIP code. Please check and try again."
            }), 404

        # Step 2: Use coordinates to get congressional district
        cd_url = (
            f"https://geocoding.geo.census.gov/geocoder/geographies/coordinates"
            f"?x={coordinates[0]}&y={coordinates[1]}"
            f"&benchmark=Public_AR_Current"
            f"&vintage=Current_Current"
            f"&format=json"
        )

        try:
            resp3 = requests.get(cd_url, timeout=8)
            resp3.raise_for_status()
            cd_data = resp3.json()
        except (requests.Timeout, requests.ConnectionError):
            logger.warning(f"Census coordinates API timeout for ZIP {zip_code}")
            return jsonify({
                "error": "The district lookup service is temporarily slow. Please try again in a moment."
            }), 503
        except Exception as e:
            logger.error(f"Census coordinates API error for ZIP {zip_code}: {e}")
            return jsonify({
                "error": "Unable to look up your district. Please try again."
            }), 502

        # Parse coordinates response for congressional district data
        districts = []
        try:
            geographies = cd_data.get("result", {}).get("geographies", {})
            cd_list = []
            for key in geographies:
                if "congressional" in key.lower() or "congress" in key.lower():
                    cd_list = geographies[key]
                    break

            if not cd_list:
                return jsonify({
                    "error": "No congressional district found for this ZIP code. Please try a different ZIP."
                }), 404

            seen_districts = set()
            for cd in cd_list:
                state_fips = cd.get("STATE", cd.get("STATEFP", ""))
                # Extract district number from various possible keys
                geoid = cd.get("GEOID", "")
                district_num = cd.get("CD", cd.get("CDFP", cd.get("CD119FP", "")))
                # GEOID format is SSDD (2-digit state + 2-digit district)
                if not district_num and len(geoid) >= 4:
                    district_num = geoid[2:]  # last 2 digits

                if state_fips and district_num:
                    state_abbr = FIPS_TO_STATE.get(state_fips)
                    if state_abbr:
                        try:
                            dist_int = int(district_num)
                        except (ValueError, TypeError):
                            continue
                        dist_key = f"{state_abbr}-{dist_int}"
                        if dist_key not in seen_districts:
                            seen_districts.add(dist_key)
                            districts.append({
                                "state": state_abbr,
                                "district": dist_int,
                                "weight": 1.0
                            })

        except Exception as e:
            logger.error(f"Error parsing Census response for ZIP {zip_code}: {e}", exc_info=True)

        if not districts:
            return jsonify({
                "error": "Could not determine your congressional district from this ZIP code. Please try a different ZIP."
            }), 404

        # Primary district first (already first from Census)
        if len(districts) > 1:
            # Assign diminishing weights
            for i, d in enumerate(districts):
                d["weight"] = round(1.0 / (i + 1), 2)

        return jsonify({"districts": districts})

    except Exception as e:
        logger.error(f"Error in zip_lookup: {e}", exc_info=True)
        return jsonify({"error": "An unexpected error occurred. Please try again."}), 500


@app.route("/api/rep-lookup", methods=["POST"])
@limiter.limit("10 per minute")
@csrf.exempt
def rep_lookup():
    """Look up a House representative for a state + district using Congress.gov API."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400

        state = str(data.get("state", "")).strip().upper()
        district = data.get("district")

        if not state or len(state) != 2:
            return jsonify({"error": "Invalid state code."}), 400
        try:
            district = int(district)
        except (ValueError, TypeError):
            return jsonify({"error": "Invalid district number."}), 400

        # Check cache first
        cached = _get_cached_rep(state, district)
        if cached:
            return jsonify(cached)

        # Look up via Congress.gov API
        api_key = os.environ.get("CONGRESS_API_KEY")
        if not api_key:
            logger.error("CONGRESS_API_KEY not configured")
            return jsonify({"error": "Representative lookup is temporarily unavailable."}), 503

        # Use per-state endpoint — the generic /member endpoint ignores stateCode/district filters
        congress_url = (
            f"https://api.congress.gov/v3/member/{state}"
            f"?currentMember=true&api_key={api_key}"
            f"&format=json&limit=60"
        )

        try:
            resp = requests.get(congress_url, timeout=5, headers={
                "Accept": "application/json",
                "User-Agent": "TeenCivics/1.0"
            })
            resp.raise_for_status()
            congress_data = resp.json()
        except requests.Timeout:
            logger.warning(f"Congress.gov API timeout for {state}-{district}")
            return jsonify({
                "error": "The representative lookup service is slow. Please try again."
            }), 503
        except Exception as e:
            logger.error(f"Congress.gov API error for {state}-{district}: {e}")
            return jsonify({
                "error": "Unable to look up your representative. Please try again."
            }), 502

        # Parse response — filter to matching state and district
        # (Congress.gov API sometimes returns members from other states/districts)
        STATE_NAMES_TO_ABBR = {
            "Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR",
            "California": "CA", "Colorado": "CO", "Connecticut": "CT", "Delaware": "DE",
            "Florida": "FL", "Georgia": "GA", "Hawaii": "HI", "Idaho": "ID",
            "Illinois": "IL", "Indiana": "IN", "Iowa": "IA", "Kansas": "KS",
            "Kentucky": "KY", "Louisiana": "LA", "Maine": "ME", "Maryland": "MD",
            "Massachusetts": "MA", "Michigan": "MI", "Minnesota": "MN",
            "Mississippi": "MS", "Missouri": "MO", "Montana": "MT", "Nebraska": "NE",
            "Nevada": "NV", "New Hampshire": "NH", "New Jersey": "NJ",
            "New Mexico": "NM", "New York": "NY", "North Carolina": "NC",
            "North Dakota": "ND", "Ohio": "OH", "Oklahoma": "OK", "Oregon": "OR",
            "Pennsylvania": "PA", "Rhode Island": "RI", "South Carolina": "SC",
            "South Dakota": "SD", "Tennessee": "TN", "Texas": "TX", "Utah": "UT",
            "Vermont": "VT", "Virginia": "VA", "Washington": "WA",
            "West Virginia": "WV", "Wisconsin": "WI", "Wyoming": "WY",
            "District of Columbia": "DC", "American Samoa": "AS", "Guam": "GU",
            "Northern Mariana Islands": "MP", "Puerto Rico": "PR",
            "U.S. Virgin Islands": "VI",
        }
        all_members = congress_data.get("members", [])
        # Filter to only members matching the requested state AND district
        members = []
        for m in all_members:
            m_state = STATE_NAMES_TO_ABBR.get(m.get("state", ""), m.get("state", ""))
            m_district = m.get("district")
            if m_state == state and m_district == district:
                members.append(m)
        # If strict filter returned nothing, fall back to unfiltered
        if not members and all_members:
            logger.warning(
                f"Congress.gov API returned {len(all_members)} members for {state}-{district} "
                f"but none matched after filtering. Using first result as fallback."
            )
            members = all_members[:1]
        if not members:
            result = {
                    "name": None,
                    "website": None,
                "email": None,
                "photo_url": None,
                "bioguideId": None,
                "state": state,
                "district": district,
                "found": False,
            }
            _set_cached_rep(state, district, result)
            return jsonify(result)

        member = members[0]
        bioguide_id = member.get("bioguideId", "")
        name = member.get("name", "")
        # Congress API returns "LastName, FirstName" format — normalize
        if "," in name:
            parts = name.split(",", 1)
            name = f"{parts[1].strip()} {parts[0].strip()}"

        # Build photo URL — prefer depiction.imageUrl from API response
        photo_url = None
        depiction = member.get("depiction")
        if depiction and isinstance(depiction, dict):
            photo_url = depiction.get("imageUrl")
        if not photo_url and bioguide_id:
            # Fallback to old bioguide pattern
            first_char = bioguide_id[0].upper()
            photo_url = f"https://bioguide.congress.gov/bioguide/photo/{first_char}/{bioguide_id}.jpg"

        # Get official website URL
        # NOTE: member["url"] is the API self-link, NOT the rep's website
        website = member.get("officialWebsiteUrl", "")
        if not website:
            # Construct House.gov URL from last name as a best-effort fallback
            if name:
                last_name = name.split()[-1].lower().replace("'", "").replace("-", "")
                website = f"https://{last_name}.house.gov"

        result = {
            "name": name,
            "website": website,
            "email": None,  # Congress members generally don't publish email addresses
            "photo_url": photo_url,
            "bioguideId": bioguide_id,
            "state": state,
            "district": district,
            "found": True,
        }

        if bioguide_id:
            try:
                from src.fetchers.contact_form_sync import get_contact_form_url
                contact_form_url = get_contact_form_url(bioguide_id)
                if contact_form_url:
                    result["contactFormUrl"] = contact_form_url
            except Exception as e:
                logger.warning(f"Contact form lookup failed for {bioguide_id}: {e}")

        _set_cached_rep(state, district, result)
        return jsonify(result)

    except Exception as e:
        logger.error(f"Error in rep_lookup: {e}", exc_info=True)
        return jsonify({"error": "An unexpected error occurred. Please try again."}), 500


@app.route("/api/pre-generate-reasoning", methods=["POST"])
@limiter.limit("10 per minute")
@csrf.exempt
def pre_generate_reasoning():
    """Pre-warm the argument cache when a user votes, before they enter their ZIP.

    Delegates to generate_bill_arguments() so both sides are generated in one
    pass and persisted to the DB for future requests.
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400

        bill_id = data.get("bill_id", "").strip()
        vote = data.get("vote", "").strip().lower()

        if not bill_id:
            return jsonify({"error": "Bill ID is required."}), 400
        if vote not in ("yes", "no"):
            return jsonify({"error": "Vote must be 'yes' or 'no'."}), 400

        # Fetch bill from database
        bill = get_bill_by_id(bill_id)
        if not bill:
            return jsonify({"error": "Bill not found."}), 404

        # If arguments already stored, nothing to pre-generate
        if bill.get("argument_support") and bill.get("argument_oppose"):
            return jsonify({"status": "ok"})

        bill_title = bill.get("title", bill_id)
        summary_overview = bill.get("summary_overview", "") or ""
        summary_detailed = bill.get("summary_detailed", "") or ""

        # Generate both sides (canonical path)
        args = generate_bill_arguments(
            bill_title=bill_title,
            summary_overview=summary_overview,
            summary_detailed=summary_detailed,
        )

        # Persist so generate_email() hits the fast DB path
        bill_number = bill.get("bill_id", bill_id)
        if args.get("support") and args.get("oppose"):
            try:
                update_bill_arguments(
                    bill_id=bill_number,
                    argument_support=args["support"],
                    argument_oppose=args["oppose"],
                )
            except Exception as store_err:
                logger.warning(f"Failed to store pre-generated arguments for {bill_number}: {store_err}")

        return jsonify({"status": "ok"})

    except Exception as e:
        logger.error(f"Error in pre_generate_reasoning: {e}", exc_info=True)
        return jsonify({"error": "An unexpected error occurred."}), 500


def _truncate_at_sentence(text: str, max_length: int) -> str:
    """Truncate text at the last sentence boundary before max_length."""
    if len(text) <= max_length:
        return text
    truncated = text[:max_length]
    last_punct = max(truncated.rfind('.'), truncated.rfind('!'), truncated.rfind('?'))
    if last_punct > 0:
        return truncated[:last_punct + 1]
    return truncated.rstrip() + "."


@app.route("/api/generate-email", methods=["POST"])
@limiter.limit("10 per minute")
@csrf.exempt
def generate_email():
    """Generate an email template for contacting a representative about a bill.

    Argument resolution order (lazy-load):
      1. Read stored argument_support / argument_oppose from the DB row.
      2. If missing, generate via generate_bill_arguments(), persist via
         update_bill_arguments(), then use the result.
      3. If generation fails completely, use a generic template.
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400

        bill_id = data.get("bill_id", "").strip()
        vote = data.get("vote", "").strip().lower()
        rep_name = data.get("rep_name", "").strip()
        rep_email = data.get("rep_email")  # Could be null

        if not bill_id:
            return jsonify({"error": "Bill ID is required."}), 400
        if vote not in ("yes", "no"):
            return jsonify({"error": "Vote must be 'yes' or 'no'."}), 400
        if not rep_name:
            return jsonify({"error": "Representative name is required."}), 400

        # Fetch bill from database
        bill = get_bill_by_id(bill_id)
        if not bill:
            return jsonify({"error": "Bill not found."}), 404

        bill_title = bill.get("title", bill_id)
        bill_number = bill.get("bill_id", bill_id)
        summary_overview = bill.get("summary_overview", "") or ""
        summary_detailed = bill.get("summary_detailed", "") or ""

        # Extract last name from rep name for salutation
        rep_last_name = rep_name.split()[-1] if rep_name else "Representative"

        # ── Lazy-load argument text ──────────────────────────────────────
        arg_key = "argument_support" if vote == "yes" else "argument_oppose"
        stored_arg = bill.get(arg_key)

        reasoning = None  # will hold the final "because …" text

        if stored_arg and stored_arg.strip():
            # ✅ Fast path: use pre-computed argument from DB
            reasoning = stored_arg.strip()
            logger.info(f"Using stored {arg_key} for bill {bill_number}")
        else:
            # Check whether argument columns exist on this row
            has_arg_columns = "argument_support" in bill and "argument_oppose" in bill
            if not has_arg_columns:
                logger.warning(
                    f"argument_support/argument_oppose columns absent for bill {bill_number}; "
                    "run scripts/add_argument_columns.py to add them"
                )

            # Generate arguments via argument_generator
            logger.info(f"No stored {arg_key} for bill {bill_number}, generating arguments…")
            try:
                args = generate_bill_arguments(
                    bill_title=bill_title,
                    summary_overview=summary_overview,
                    summary_detailed=summary_detailed,
                )
                if args and args.get("support") and args.get("oppose"):
                    reasoning = args["support"] if vote == "yes" else args["oppose"]
                    # Persist so future requests are instant
                    if has_arg_columns:
                        try:
                            update_bill_arguments(
                                bill_id=bill_number,
                                argument_support=args["support"],
                                argument_oppose=args["oppose"],
                            )
                            logger.info(f"Stored generated arguments for bill {bill_number}")
                        except Exception as store_err:
                            logger.warning(f"Failed to store arguments for bill {bill_number}: {store_err}")
                    else:
                        logger.info(
                            f"Skipping argument storage for bill {bill_number} — columns not yet added"
                        )
            except Exception as gen_err:
                logger.error(f"generate_bill_arguments failed for bill {bill_number}: {gen_err}")

        # ── Fallback: generic template ───────────────────────────────────
        if not reasoning or not reasoning.strip():
            logger.warning(f"All argument generation failed for bill {bill_number}, using generic template")
            if vote == "yes":
                reasoning = (
                    "I SUPPORT this bill. After reviewing the full text and summary of "
                    "this legislation, I believe it addresses an important issue and "
                    "would benefit American communities. I encourage you to support its passage."
                )
            else:
                reasoning = (
                    "I OPPOSE this bill. After reviewing the full text and summary of "
                    "this legislation, I believe the potential costs and unintended "
                    "consequences outweigh the benefits. I encourage you to oppose this "
                    "legislation and pursue better alternatives."
                )

        # Build subject
        vote_label = "Yes" if vote == "yes" else "No"
        subject = f"Constituent Feedback on {bill_title} — Voted {vote_label} | via TeenCivics"

        # Build body (≤500 chars for congressional contact form limits)
        stance = "SUPPORT" if vote == "yes" else "OPPOSE"

        def should_prepend_the(title: str) -> bool:
            if not title:
                return False
            t = title.strip()
            if not t:
                return False
            lower = t.lower()
            if lower.startswith(("the ", "a ", "an ")):
                return False
            # Clause-like or verb-led titles (avoid "the" in front)
            if lower.startswith((
                "to ",
                "recognizing ",
                "expressing ",
                "supporting ",
                "commending ",
                "condemning ",
                "honoring ",
                "celebrating ",
                "providing ",
                "prohibiting ",
                "requiring ",
                "establishing ",
                "amending ",
                "authorizing ",
                "extending ",
                "directing ",
                "repealing ",
                "designating ",
                "encouraging ",
                "urging ",
                "calling ",
                "promoting ",
                "creating ",
                "protecting ",
                "ensuring ",
                "improving ",
                "updating ",
                "revising ",
                "reaffirming ",
                "resolving ",
                "relating ",
                "approving ",
                "modifying ",
                "clarifying ",
                "removing ",
                "restoring ",
                "enhancing ",
            )):
                return False
            return True

        title_for_intro = (bill_title or "").strip()
        if not title_for_intro:
            bill_ref = f"the bill ({bill_number})"
        else:
            bill_ref = f"{title_for_intro} ({bill_number})"
            if should_prepend_the(title_for_intro):
                bill_ref = f"the {bill_ref}"

        # Core template without the "because" clause
        prefix = (
            f"Dear Representative {rep_last_name},\n\n"
            f"As your constituent, I reviewed {bill_ref} "
            f"on TeenCivics (https://teencivics.org), a civic education platform "
            f"that helps young Americans engage with legislation.\n\n"
            f"I {stance} this bill because "
        )

        # ── Dynamic truncation to keep total email ≤ 500 chars ───────
        EMAIL_CHAR_LIMIT = 500
        max_arg_length = max(100, EMAIL_CHAR_LIMIT - len(prefix))

        reason_text = reasoning.strip()

        # Truncate to fit within email character limit
        if len(reason_text) > max_arg_length:
            reason_text = _truncate_at_sentence(reason_text, max_arg_length)

        # Only ensure it ends with punctuation
        if reason_text and reason_text[-1] not in '.!?':
            reason_text = reason_text.rstrip(',;: ') + '.'

        body = prefix + reason_text

        # Build mailto URL if email is available
        mailto_url = None
        if rep_email:
            params = urllib.parse.urlencode({
                "subject": subject,
                "body": body,
            }, quote_via=urllib.parse.quote)
            mailto_url = f"mailto:{rep_email}?{params}"

        return jsonify({
            "subject": subject,
            "body": body,
            "mailto_url": mailto_url,
        })

    except Exception as e:
        logger.error(f"Error in generate_email: {e}", exc_info=True)
        return jsonify({"error": "An unexpected error occurred. Please try again."}), 500


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