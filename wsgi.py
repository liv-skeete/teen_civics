"""
WSGI entry point for production deployment.

This module provides the WSGI application object for production servers
like Gunicorn to use when serving the TeenCivics Flask application.

Usage with Gunicorn:
    gunicorn --config gunicorn_config.py wsgi:app
"""

from app import app

if __name__ == "__main__":
    app.run()