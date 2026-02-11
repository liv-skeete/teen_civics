"""
Gunicorn configuration file for TeenCivics production deployment.

This configuration uses gthread workers for resilient I/O handling.
Each worker spawns multiple threads so a blocked DB call doesn't starve
the entire process.

Configured for Railway.app deployment with 512MB memory constraints.
"""

import os

# Server socket
bind = "0.0.0.0:" + str(os.environ.get("PORT", 8000))
backlog = 2048

# Worker processes — 3 workers × 4 threads = 12 concurrent request slots
# gthread lets each worker handle multiple requests via threads, preventing
# a single blocked DB/AI call from starving the app.
workers = 3
worker_class = "gthread"
threads = 4
worker_connections = 1000
timeout = 30  # Kill stuck workers after 30s (well within Cloudflare's 15s gateway timeout)
graceful_timeout = 15  # Allow 15s for in-flight requests during shutdown/restart
keepalive = 2

# Restart workers after this many requests to prevent memory leaks.
# Jitter spreads recycling so workers don't all restart simultaneously.
max_requests = 2000
max_requests_jitter = 200

# Preload the app before forking workers (saves memory via copy-on-write)
preload_app = True

# Logging
accesslog = "-"  # Log to stdout
errorlog = "-"   # Log to stderr
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s"'

# Security — trust proxy headers from all sources (Railway's internal routing)
forwarded_allow_ips = "*"

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