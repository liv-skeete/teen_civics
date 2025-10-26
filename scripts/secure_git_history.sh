#!/bin/bash
# Script to securely rewrite git history to remove sensitive database credentials
# WARNING: This will change commit history and require force pushing to remote

echo "⚠️  WARNING: This script will rewrite git history!"
echo "⚠️  This will change commit hashes and require force pushing to remote repositories."
echo ""
echo "This script will remove the following files from git history:"
echo "  - scripts/verify_migration.py (old version with hardcoded credentials)"
echo "  - scripts/migrate_data_to_railway.py (old version with hardcoded credentials)"
echo ""
read -p "Do you want to proceed? (yes/no): " confirm

if [[ $confirm != "yes" ]]; then
    echo "Operation cancelled."
    exit 1
fi

echo "Creating backup of current branch..."
git branch backup-before-rewrite-$(date +%s)

echo "Rewriting git history to remove sensitive files..."

# Use git filter-branch to remove the files from history
# This is a destructive operation that rewrites history
git filter-branch --force --index-filter \
'git rm --cached --ignore-unmatch scripts/verify_migration.py scripts/migrate_data_to_railway.py' \
--prune-empty --tag-name-filter cat -- --all

echo "Cleaning up..."
rm -rf .git/refs/original/

echo "Expiring reflog and garbage collecting..."
git reflog expire --expire=now --all
git gc --aggressive --prune=now

echo "✅ Git history rewrite complete!"
echo ""
echo "⚠️  Next steps:"
echo "  1. Update your Railway database password for security."
echo "  2. Update your .env file with the new DATABASE_URL."
echo "  3. Test your scripts with the DATABASE_URL environment variable."
echo ""
echo "⚠️  To push changes to remote repository:"
echo "  git push origin main --force"
echo ""
echo "⚠️  NOTE: After pushing with --force, all collaborators must run:"
echo "  git fetch origin"
echo "  git reset --hard origin/main"