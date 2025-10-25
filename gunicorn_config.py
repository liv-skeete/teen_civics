"""
Gunicorn configuration file for TeenCivics production deployment.

This configuration optimizes Gunicorn for production use with appropriate
worker counts, timeouts, and logging settings.
"""

import multiprocessing
import os

# Server socket
bind = "0.0.0.0:" + str(os.environ.get("PORT", 8000))
backlog = 2048

# Worker processes
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "sync"
worker_connections = 1000
timeout = 30
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