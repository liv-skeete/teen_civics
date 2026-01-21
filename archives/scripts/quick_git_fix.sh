#!/bin/bash
#
# Quick Git fix script for immediate commit issues.
# This script performs the most essential fixes for slow Git commits.

echo "TeenCivics Quick Git Fix"
echo "========================"

# Check if we're in a Git repository
if ! git rev-parse --git-dir > /dev/null 2>&1; then
    echo "Error: Not in a Git repository!"
    exit 1
fi

echo "Repository root: $(git rev-parse --show-toplevel)"

# Check current status
echo
echo "1. Checking Git status..."
git status --porcelain

# Rebuild Git index (most common fix for slow commits)
echo
echo "2. Rebuilding Git index..."
echo "Backing up current index..."
cp .git/index .git/index.backup 2>/dev/null || echo "No index backup needed"

echo "Removing current index..."
rm .git/index 2>/dev/null || echo "No index file to remove"

echo "Rebuilding index..."
git reset

# Quick optimization
echo
echo "3. Quick repository optimization..."
echo "Cleaning up reflog..."
git reflog expire --expire=now --all

echo "Running auto garbage collection..."
git gc --auto

# Check for large files
echo
echo "4. Checking for large tracked files..."
git ls-files data/bills.db > /dev/null 2>&1
if [ $? -eq 0 ]; then
    echo "WARNING: data/bills.db is tracked by Git!"
    echo "This may be causing commit delays."
    echo "Consider: git rm --cached data/bills.db"
fi

# Final instructions
echo
echo "Quick fix complete!"
echo
echo "To commit quickly now, try:"
echo "  git add -A"
echo "  git commit --no-verify -m \"Quick commit\""
echo
echo "If still slow, check large file sizes:"
echo "  ls -lh data/bills.db"