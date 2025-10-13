#!/bin/bash
#
# Development server startup script for TeenCivics Flask app.
#
# This script ensures all dependencies are installed and then starts
# the Flask development server. It uses python3.
#

# Navigate to the project root directory
cd "$(dirname "$0")/.."

# Activate virtual environment if it exists
if [ -d "venv" ]; then
  echo "Activating virtual environment..."
  source venv/bin/activate
fi

# Install/update dependencies
echo "Installing/updating dependencies from requirements.txt..."
python3 -m pip install -r requirements.txt

# Check if DEV_BROWSER is set to install browser testing dependencies
if [ "$DEV_BROWSER" = "1" ]; then
    echo "Installing development dependencies from requirements-dev.txt..."
    python3 -m pip install -r requirements-dev.txt
    # Install greenlet with pre-compiled wheel for macOS compatibility
    python3 -m pip install --only-binary=:all: greenlet>=3.0.3
    # Install Playwright browser binaries
    python3 -m playwright install --with-deps
fi

# Run the Flask application
echo "Starting Flask development server..."
python3 app.py