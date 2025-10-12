# Git Commit Performance Fixes

This document explains how to fix slow Git commit performance in the TeenCivics repository.

## Problem

Git commits are taking a long time to complete, even for minor changes. This is typically caused by:

1. Large tracked files (especially `data/bills.db`)
2. Corrupted Git index
3. Repository optimization issues

## Automated Solutions

### 1. Git Optimization Script

Run the optimization script to fix common Git performance issues:

```bash
python scripts/fix_git_commits.py
```

This script will:
- Rebuild the Git index
- Run Git maintenance commands
- Check for large files
- Update `.gitignore` with proper database patterns

### 2. Repository Cleanup Script

For more thorough cleanup, run:

```bash
python scripts/cleanup_repository.py
```

This script will:
- Remove unnecessary files
- Optimize Git storage
- Find and report large files
- Clean up Git reflog

## Manual Solutions

If the automated scripts don't resolve the issue, try these manual steps:

### 1. Rebuild Git Index

```bash
# Backup current index
cp .git/index .git/index.backup

# Remove and rebuild index
rm .git/index
git reset
```

### 2. Run Git Maintenance

```bash
# Garbage collection
git gc

# File system check
git fsck

# Repack objects
git repack -ad
```

### 3. Commit Without Hooks

Skip pre-commit hooks that might be slowing things down:

```bash
git commit --no-verify -m "Your commit message"
```

### 4. Handle Large Files

If `data/bills.db` is tracked and causing issues:

```bash
# Check if file is tracked
git ls-files data/bills.db

# If tracked, remove from index (but keep file)
git rm --cached data/bills.db

# Commit the removal
git commit -m "Remove database file from tracking"
```

## Long-term Solutions

### 1. Use Git LFS for Large Files

For large database files, consider using Git LFS:

```bash
# Install Git LFS (if not already installed)
git lfs install

# Track database files with LFS
git lfs track "*.db"

# Add the .gitattributes file
git add .gitattributes

# Add and commit the database file
git add data/bills.db
git commit -m "Track database file with Git LFS"
```

### 2. Database Migration Strategy

Instead of tracking the entire database file, consider:

1. Using migration scripts to recreate database state
2. Tracking only the migration scripts in Git
3. Generating test data as part of the build process

## Prevention

To prevent future Git performance issues:

1. Regularly run the optimization scripts
2. Monitor file sizes in commits
3. Use appropriate `.gitignore` patterns
4. Consider shallow clones for CI/CD environments
5. Periodically prune old commits if appropriate

## Quick Fix for Immediate Commits

If you need to commit right now:

```bash
# Stage all changes
git add -A

# Commit without verification (skipping hooks)
git commit --no-verify -m "Quick commit message"
```

This bypasses any slow pre-commit hooks that might be causing delays.

## Additional Resources

- [Git Performance Tips](https://github.blog/2019-04-10-introducing-github-package-registry-git-large-file-storage-lfs-improvements-and-more/)
- [Git LFS Documentation](https://git-lfs.github.com/)
- [Git Maintenance Best Practices](https://git-scm.com/book/en/v2/Git-Internals-Maintenance-and-Data-Recovery)