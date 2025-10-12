#!/bin/bash
#
# Script to restart the development server and clear template cache
#

echo "Stopping any running Flask processes..."
pkill -f "python3 app.py" || true
pkill -f "flask run" || true

echo "Waiting for processes to stop..."
sleep 2

echo "Starting fresh development server..."
cd "$(dirname "$0")"
./scripts/dev.sh