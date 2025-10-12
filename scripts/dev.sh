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
pip install -r requirements.txt

# Run the Flask application
echo "Starting Flask development server..."
python3 app.py