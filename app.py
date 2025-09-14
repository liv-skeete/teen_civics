#!/usr/bin/env python3
"""
TeenCivics Flask Web Application
A Congressional App Challenge project that summarizes congressional bills for teenagers.
"""

import os
import logging
from datetime import datetime
from flask import Flask, render_template, jsonify, request, abort
from flask_cors import CORS

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import database utilities
try:
    from src.database.db_utils import (
        init_db,
        get_latest_bill,
        get_bill_by_slug,
        get_all_bills,
        get_bill_by_id,
        update_poll_results,
    )
except ImportError as e:
    logger.error(f"Database import error: {e}")
    # Fallback for development - we'll handle this gracefully

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})

# Configuration
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['TEMPLATES_AUTO_RELOAD'] = True

# Initialize database
try:
    init_db()
    logger.info("Database initialized successfully")
except Exception as e:
    logger.warning(f"Database initialization warning: {e}")

@app.route('/')
def index():
    """Homepage showing the latest bill with poll widget"""
    try:
        latest_bill = get_latest_bill()
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
        all_bills = get_all_bills()
        
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
        bill = get_bill_by_slug(slug)
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

@app.route('/api/vote', methods=['POST'])
def vote():
    """API endpoint for poll voting"""
    try:
        data = request.get_json(silent=True) or {}
        bill_id = data.get('bill_id')
        vote_value = data.get('vote')
        previous_vote = data.get('previous_vote')

        # Only support 'yes' and 'no' for v1 (DB tracks poll_results_yes/no)
        if not bill_id or vote_value not in ('yes', 'no'):
            return jsonify({'error': 'Invalid vote data'}), 400

        # Update poll results in database; returns False if bill not found or error
        updated = update_poll_results(bill_id, vote_value, previous_vote)
        if not updated:
            return jsonify({'error': 'Bill not found or update failed'}), 404

        return jsonify({'success': True, 'message': 'Vote recorded'})
    except Exception as e:
        logger.error(f"Error processing vote: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/poll-results/<bill_id>')
def poll_results(bill_id):
    """API endpoint to get poll results for a specific bill"""
    try:
        bill = get_bill_by_id(bill_id)
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

if __name__ == '__main__':
    # Development server
    app.run(host='0.0.0.0', port=5000, debug=True)