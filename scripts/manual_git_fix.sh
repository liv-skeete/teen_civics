#!/bin/bash
#
# Manual Git fix script that bypasses Git commands entirely.
# This script fixes Git issues by directly manipulating files.

echo "TeenCivics Manual Git Fix"
echo "========================="
echo "This script fixes Git issues by directly manipulating files."
echo "Use this when normal Git commands hang or fail."

# Check if we're in a Git repository by looking for .git directory
if [ ! -d ".git" ]; then
    echo "Error: .git directory not found!"
    echo "Make sure you're running this from the repository root."
    exit 1
fi

echo "Found .git directory."

# Backup and remove problematic files
echo
echo "1. Backing up and removing problematic Git files..."

# Backup current index
if [ -f ".git/index" ]; then
    echo "Backing up .git/index..."
    cp ".git/index" ".git/index.backup.manual" 2>/dev/null || echo "Could not backup index"
    echo "Removing .git/index..."
    rm -f ".git/index"
fi

# Backup and remove index.lock if it exists
if [ -f ".git/index.lock" ]; then
    echo "Removing .git/index.lock..."
    rm -f ".git/index.lock"
fi

# Backup and clean reflog directory
if [ -d ".git/logs" ]; then
    echo "Backing up .git/logs..."
    cp -r ".git/logs" ".git/logs.backup.manual" 2>/dev/null || echo "Could not backup logs"
    echo "Removing .git/logs/HEAD..."
    rm -f ".git/logs/HEAD"
fi

# Backup and clean refs directory
if [ -d ".git/refs" ]; then
    echo "Backing up .git/refs..."
    cp -r ".git/refs" ".git/refs.backup.manual" 2>/dev/null || echo "Could not backup refs"
fi

echo
echo "2. Removing temporary Git files..."

# Remove any Git temporary files
rm -f ".git"/*.lock 2>/dev/null
rm -f ".git"/*/*.lock 2>/dev/null

echo
echo "3. Manual fix steps completed!"

echo
echo "To restore basic Git functionality:"
echo "  1. Close all terminal windows and VS Code"
echo "  2. Reopen a new terminal"
echo "  3. Navigate to your repository"
echo "  4. Run: git reset"
echo "  5. Run: git status"

echo
echo "To check if data/bills.db is tracked (and causing issues):"
echo "  After Git is working again, run: git ls-files data/bills.db"
echo "  If it shows output, run: git rm --cached data/bills.db"

echo
echo "If problems persist, try removing the database file from tracking:"
echo "  1. Backup data/bills.db somewhere safe"
echo "  2. Delete data/bills.db"
echo "  3. Run: git reset"
echo "  4. Run: git status"
echo "  5. Commit the deletion: git commit -m \"Remove database file\""
echo "  6. Restore your database file from backup"