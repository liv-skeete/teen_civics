#!/bin/bash
#
# Quick commit script specifically for feed_parser.py
# This bypasses hanging Git commands by working directly with files

echo "TeenCivics Quick Feed Parser Commit"
echo "==================================="

# Check if we're in a Git repository
if [ ! -d ".git" ]; then
    echo "Error: Not in a Git repository!"
    exit 1
fi

# Check if feed_parser.py exists
if [ ! -f "src/fetchers/feed_parser.py" ]; then
    echo "Error: src/fetchers/feed_parser.py not found!"
    exit 1
fi

echo "Found repository and feed_parser.py"

# Kill any hanging Git processes (this might not work but worth trying)
echo
echo "Attempting to kill hanging Git processes..."
pkill -f git 2>/dev/null || echo "No Git processes found or could not kill"

# Remove most common hanging files
echo
echo "Removing files that commonly cause Git to hang..."
rm -f ".git/index.lock" 2>/dev/null || echo "No index.lock found"
rm -f ".git/HEAD.lock" 2>/dev/null || echo "No HEAD.lock found"
rm -f ".git/logs/HEAD.lock" 2>/dev/null || echo "No logs/HEAD.lock found"

# Show file status
echo
echo "Checking feed_parser.py status:"
ls -lah "src/fetchers/feed_parser.py"

# Create a backup of your changes
echo
echo "Creating backup of feed_parser.py changes..."
cp "src/fetchers/feed_parser.py" "/tmp/feed_parser_backup.py" 2>/dev/null && echo "Backup created at /tmp/feed_parser_backup.py" || echo "Could not create backup"

# Show database file status (likely culprit)
if [ -f "data/bills.db" ]; then
    echo
    echo "Database file status (likely causing issues):"
    ls -lah "data/bills.db"
    db_size=$(du -m "data/bills.db" 2>/dev/null | cut -f1)
    if [ "$db_size" -gt "10" ] 2>/dev/null; then
        echo "WARNING: Database file is ${db_size}MB - this is likely causing Git to hang!"
    fi
fi

echo
echo "Manual fix steps completed!"
echo
echo "CRITICAL: Close ALL terminal windows and VS Code NOW!"
echo "Then:"
echo "  1. Reopen ONE new terminal"
echo "  2. Navigate to your repository"
echo "  3. Run: git add src/fetchers/feed_parser.py"
echo "  4. Run: git commit -m \"Update feed parser\""
echo
echo "If Git commands still hang:"
echo "  1. Run: ./scripts/manual_git_fix.sh"
echo "  2. Try the git commands again"
echo
echo "If the database file is tracked (check with 'git ls-files data/bills.db'):"
echo "  1. Backup data/bills.db somewhere safe"
echo "  2. Run: git rm --cached data/bills.db"
echo "  3. Commit: git commit -m \"Remove database file from tracking\""
echo "  4. Restore your database from backup"