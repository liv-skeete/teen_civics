#!/usr/bin/env python3
"""
TeenCivics Flask Web Application
A Congressional App Challenge project that summarizes congressional bills for teenagers.
"""

from dotenv import load_dotenv

# Load environment variables from .env file FIRST
load_dotenv()

import os
import logging
from datetime import datetime
from flask import Flask, render_template, jsonify, request, abort, url_for
from flask_cors import CORS
from markupsafe import Markup, escape

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import database utilities as a module for safer binding
try:
    from src.database import db_utils as DB
except ImportError as e:
    logger.error(f"Database import error: {e}")
    DB = None  # allow app to run with graceful fallbacks

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})

# Configuration
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['TEMPLATES_AUTO_RELOAD'] = True

# Initialize database
try:
    if DB:
        DB.init_db()
        logger.info("Database initialized successfully")
    else:
        logger.warning("Database utils not available; skipping init_db()")
except Exception as e:
    logger.warning(f"Database initialization warning: {e}")

@app.route('/')
def index():
    """Homepage showing the latest bill with poll widget"""
    try:
        latest_bill = DB.get_latest_bill() if DB else None
        if not latest_bill:
            return render_template('index.html', bill=None, error="No bills available yet")
        
        return render_template('index.html', bill=latest_bill)
    except Exception as e:
        logger.error(f"Error loading index: {e}")
        return render_template('index.html', bill=None, error="Error loading bill data")

@app.route('/archive')
def archive():
    """Archive page with paginated bill list and status filtering"""
    try:
        page = request.args.get('page', 1, type=int)
        status_filter = request.args.get('status', 'all')
        
        # Get all bills
        all_bills = DB.get_all_bills() if DB else []
        
        # Apply status filter
        if status_filter != 'all':
            all_bills = [bill for bill in all_bills if bill.get('status') == status_filter]
        
        # Pagination (10 bills per page)
        per_page = 10
        total_pages = (len(all_bills) + per_page - 1) // per_page
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        bills_page = all_bills[start_idx:end_idx]
        
        return render_template('archive.html', 
                             bills=bills_page, 
                             current_page=page,
                             total_pages=total_pages,
                             status_filter=status_filter)
    except Exception as e:
        logger.error(f"Error loading archive: {e}")
        return render_template('archive.html', bills=[], error="Error loading archive")

@app.route('/bills/<slug>')
def bill_detail(slug):
    """Individual bill details page"""
    try:
        bill = DB.get_bill_by_slug(slug) if DB else None
        if not bill:
            abort(404)
        
        return render_template('bill.html', bill=bill)
    except Exception as e:
        logger.error(f"Error loading bill {slug}: {e}")
        abort(404)

@app.route('/resources')
def resources():
    """Educational resources page"""
    return render_template('resources.html')

@app.route('/contact')
def contact():
    """Contact page with ways to reach and give feedback"""
    return render_template('contact.html')

@app.route('/about')
def about():
    """About page with project information and creator bio"""
    # Prefer a real photo if present; otherwise fall back to the SVG placeholder
    candidates = [
        'img/creator.jpg',
        'img/creator.png',
        'img/creator.webp',
        'img/creator.svg',  # final fallback
    ]
    chosen = None
    for rel in candidates:
        abs_path = os.path.join(app.root_path, 'static', rel)
        if os.path.exists(abs_path):
            chosen = url_for('static', filename=rel)
            break
    if not chosen:
        chosen = url_for('static', filename='img/creator.svg')
    return render_template('about.html', creator_photo=chosen)

@app.route('/api/vote', methods=['POST'])
def vote():
    """API endpoint for poll voting (supports changing vote)."""
    try:
        data = request.get_json(silent=True) or {}
        bill_id = data.get('bill_id')
        vote_value = (data.get('vote') or '').strip().lower()
        previous_vote = data.get('previous_vote')
        previous_vote = (previous_vote or '').strip().lower() if previous_vote is not None else None

        # Validate inputs: Only 'yes' and 'no' are supported by the app layer
        if not bill_id or vote_value not in ('yes', 'no'):
            return jsonify({'error': 'Invalid vote data'}), 400
        if previous_vote not in (None, 'yes', 'no'):
            return jsonify({'error': 'Invalid previous_vote'}), 400

        # Perform update (atomic change handled in DB layer)
        updated = DB.update_poll_results(bill_id, vote_value, previous_vote) if DB else False
        if not updated:
            return jsonify({'error': 'Bill not found or update failed'}), 404

        # Fetch updated tallies to return with response
        bill = DB.get_bill_by_id(bill_id) if DB else None
        if not bill:
            return jsonify({'error': 'Bill not found after update'}), 404

        yes = int(bill.get('poll_results_yes', 0) or 0)
        no = int(bill.get('poll_results_no', 0) or 0)
        results = {
            'yes': yes,
            'no': no,
            'total': yes + no,
        }

        # Message reflects whether this was a change or new record
        if previous_vote is None:
            msg = f"Recorded new vote {vote_value} for bill {bill_id}"
        elif previous_vote == vote_value:
            # Idempotent no-op; DB layer logs and returns True
            msg = f"No change; vote already {vote_value} for bill {bill_id}"
        else:
            msg = f"Changed vote for bill {bill_id}: {previous_vote}->{vote_value}"

        return jsonify({'success': True, 'message': msg, 'results': results}), 200
    except Exception as e:
        logger.error(f"Error processing vote: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/poll-results/<bill_id>')
def poll_results(bill_id):
    """API endpoint to get poll results for a specific bill"""
    try:
        bill = DB.get_bill_by_id(bill_id) if DB else None
        if not bill:
            return jsonify({'error': 'Bill not found'}), 404

        yes = bill.get('poll_results_yes', 0) or 0
        no = bill.get('poll_results_no', 0) or 0
        total = int(yes) + int(no)

        results = {
            'yes': int(yes),
            'no': int(no),
            'total': total,
        }

        return jsonify(results)
    except Exception as e:
        logger.error(f"Error getting poll results: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.errorhandler(404)
def not_found(error):
    """Custom 404 error page"""
    return render_template('404.html'), 404

@app.context_processor
def inject_current_year():
    """Inject current year into all templates"""
    return {'current_year': datetime.now().year}

@app.template_filter('format_date')
def format_date_filter(date_string):
    """Convert datetime string to just the date portion (YYYY-MM-DD)"""
    if not date_string:
        return 'N/A'
    try:
        # Handle both full datetime and date-only strings
        if 'T' in date_string:
            dt = datetime.fromisoformat(date_string.replace('Z', '+00:00'))
            return dt.strftime('%Y-%m-%d')
        else:
            return date_string
    except (ValueError, TypeError):
        return date_string

@app.template_filter('shorten_title')
def shorten_title_filter(title, max_length=80):
    """Shorten a title to a reasonable length"""
    if not title or len(title) <= max_length:
        return title
    
    # Try to break at sentence boundaries first
    sentences = title.split(';')
    if len(sentences) > 1 and len(sentences[0].strip()) <= max_length:
        return sentences[0].strip()
    
    # Otherwise truncate at word boundaries
    words = title.split()
    shortened = []
    current_length = 0
    
    for word in words:
        if current_length + len(word) + 1 > max_length:
            break
        shortened.append(word)
        current_length += len(word) + 1
    
    return ' '.join(shortened) + ('...' if len(words) > len(shortened) else '')

@app.template_filter('generate_congress_url')
def generate_congress_url_filter(bill_id, congress_session):
    """Generate a robust congress.gov URL from a bill_id and congress_session."""
    if not bill_id or not congress_session:
        return '#'
    try:
        import re
        bid = str(bill_id).strip().lower()
        
        # Map bill type abbreviations to congress.gov path segments
        # Check longest patterns first to avoid "hr" matching "hres"
        type_patterns = [
            ('hconres', 'house-concurrent-resolution'),
            ('hjres', 'house-joint-resolution'),
            ('hres', 'house-resolution'),
            ('hr', 'house-bill'),
            ('sconres', 'senate-concurrent-resolution'),
            ('sjres', 'senate-joint-resolution'),
            ('sres', 'senate-resolution'),
            ('s', 'senate-bill'),
        ]
        
        bill_type = None
        bill_number = None
        full_type = None
        
        for pattern, congress_type in type_patterns:
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
    """
    Convert structured plain text summary (with emoji headers and bullets) into clean HTML.

    Improvements:
    - Inserts virtual line breaks before emoji section headers and bullet symbols when content
      is delivered as one long line (so headers don't bold the entire paragraph).
    - Converts inline bullets (… • A • B • C) into <ul><li>…</li></ul>.
    - Supports simple hyphen sub-bullets inside a bullet using ' - ' as delimiter.
    - Ensures lists are opened/closed correctly and blank lines collapse safely.
    """
    if not text:
        return Markup("")

    import re
    s = str(text).replace("\r\n", "\n").replace("\r", "\n")

    # Normalize: ensure known emoji header tokens and bullets start on their own lines
    header_tokens = [
        "🔎 Overview",
        "🔑 Key Provisions",
        "⚖️ Policy Riders or Key Rules/Changes",
        "⚖️ Policy Riders or Key Rules",
        "📌 Procedural/Administrative Notes",
        "👉 In short",
        "📋 House Resolution Procedures",
        "📋 Senate Resolution Procedures",
        "📋 House Bill Legislative Process",
        "📋 Senate Bill Legislative Process",
        "🏛️ Legislative Status Context",
    ]
    for ht in header_tokens:
        s = re.sub(rf'(?<!^)\s*{re.escape(ht)}', "\n" + ht, s)
    # Normalize bullets to start on their own lines
    s = re.sub(r'\s*•\s*', '\n• ', s)

    lines = [ln.strip() for ln in s.split("\n")]

    html_parts: list[str] = []
    in_list_stack: list[bool] = []

    def open_list():
        html_parts.append("<ul>")
        in_list_stack.append(True)

    def close_all_lists():
        while in_list_stack:
            html_parts.append("</ul>")
            in_list_stack.pop()

    def emit_bullets_from_text(t: str):
        """
        Split text on '•' and render bullets. Sub-bullets split on ' - ' become nested <ul>.
        """
        tt = re.sub(r"[ \t]+", " ", (t or "").strip())
        if not tt:
            return

        parts = [p.strip() for p in tt.split('•') if p.strip() != ""]
        if not parts:
            return

        # If first part looks like a sentence and the rest are bullets, emit as paragraph then list
        preface = ""
        if not tt.startswith('•') and len(parts) > 1:
            preface = parts[0]
            bullets = parts[1:]
        else:
            bullets = parts

        if preface:
            html_parts.append(f"<p>{escape(preface)}</p>")

        if bullets:
            open_list()
            for bt in bullets:
                subparts = [sp.strip() for sp in re.split(r"\s+-\s+", bt) if sp.strip()]
                if not subparts:
                    continue
                main = subparts[0]
                html_parts.append(f"<li>{escape(main)}")
                if len(subparts) > 1:
                    html_parts.append("<ul>")
                    for sp in subparts[1:]:
                        html_parts.append(f"<li>{escape(sp)}</li>")
                    html_parts.append("</ul>")
                html_parts.append("</li>")
            close_all_lists()

    known_headers = [
        "🔎 Overview",
        "🔑 Key Provisions",
        "⚖️ Policy Riders or Key Rules",
        "⚖️ Policy Riders or Key Rules/Changes",
        "📌 Procedural/Administrative Notes",
        "👉 In short",
        "📋 House Resolution Procedures",
        "📋 Senate Resolution Procedures",
        "📋 House Bill Legislative Process",
        "📋 Senate Bill Legislative Process",
        "🏛️ Legislative Status Context",
    ]
    header_body_re = re.compile(r'^([🔎🔑⚖️📌👉📋🏛️][^:]*?)(?::\s*|\s+)?(.*)$')

    for ln in lines:
        if not ln:
            close_all_lists()
            continue

        # Section header anywhere at the start of the line
        if ln.startswith(("🔎", "🔑", "⚖️", "📌", "👉", "📋", "🏛️")):
            close_all_lists()
            header = None
            body = ""
            for kh in known_headers:
                if ln.startswith(kh):
                    header = kh
                    body = ln[len(kh):].strip()
                    break
            if header is None:
                m = header_body_re.match(ln)
                if m:
                    header = m.group(1).strip()
                    body = m.group(2).strip()
                else:
                    header = ln.strip()
                    body = ""
            html_parts.append(f"<h4>{escape(header)}</h4>")
            if body:
                # body might contain inline bullets after normalization
                if '•' in body:
                    emit_bullets_from_text(body)
                else:
                    html_parts.append(f"<p>{escape(body)}</p>")
            continue

        # Non-header: either bullets or a plain paragraph
        if '•' in ln:
            emit_bullets_from_text(ln)
        else:
            close_all_lists()
            html_parts.append(f"<p>{escape(ln)}</p>")

    close_all_lists()
    return Markup("".join(html_parts))

if __name__ == '__main__':
    # Development server (disable reloader to avoid multiple processes)
    port = int(os.environ.get('PORT', os.environ.get('FLASK_RUN_PORT', 5050)))
    app.run(host='0.0.0.0', port=port, debug=True, use_reloader=False)