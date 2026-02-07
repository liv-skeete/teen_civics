"""
Gunicorn configuration file for TeenCivics production deployment.

This configuration optimizes Gunicorn for production use with appropriate
worker counts, timeouts, and logging settings.

Configured for Railway.app deployment with 512MB memory constraints.
"""

import os

# Server socket
bind = "0.0.0.0:" + str(os.environ.get("PORT", 8000))
backlog = 2048

# Worker processes - optimized for Railway's memory limits
# Railway free tier: 512MB RAM, 1 vCPU
# 2 workers keeps memory usage under limit while handling concurrent requests
workers = 2
worker_class = "sync"
worker_connections = 1000
timeout = 120  # Increased for AI summarization calls
keepalive = 2

# Restart workers after this many requests to prevent memory leaks
max_requests = 1000
max_requests_jitter = 50

# Logging
accesslog = "-"  # Log to stdout
errorlog = "-"   # Log to stderr
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s"'

# Process naming
proc_name = "teencivics"

# Server mechanics
daemon = False
pidfile = None
umask = 0
user = None
group = None
tmp_upload_dir = None

# SSL (if needed, configure here)
# keyfile = None
# certfile = None