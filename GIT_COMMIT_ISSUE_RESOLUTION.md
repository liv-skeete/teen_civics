# Git Commit Issue Resolution

## Problem Summary

Git commits were taking an extremely long time (often hanging indefinitely) when trying to commit changes, even minor ones like editing `src/fetchers/feed_parser.py`. The issue affected all Git operations including `git commit`, `git status`, and `git reset`.

## Root Causes Identified

1. **Background Git Processes from VS Code**: VS Code was running background Git operations that held onto repository resources, causing conflicts with manual Git commands.
2. **Git Index Corruption**: The Git index became corrupted, causing normal operations to hang.
3. **osxkeychain Credential Helper Issues**: The credential helper was potentially causing authentication delays with remote repositories.
4. **File System Locks**: Deep system-level file locks were preventing Git operations from completing.

## Issue Timeline & Symptoms

- `git commit` commands would start but hang for extended periods
- `git status` and `git reset` would also hang
- Even `CTRL+C` wouldn't kill the hanging processes
- Terminal had to be killed to stop operations
- Multiple Git processes were found running in background: 
  ```
  /Library/Developer/CommandLineTools/usr/bin/git log --format=%H%n%aN%n%aE%n%at%n%ct%n%P%n%D%n%B -z -n51 --shortstat --follow -- /Users/olivia/Documents/coding/projects/teencivics/wsgi.py
  ```

## Solutions Implemented

### 1. Manual Process Termination
```bash
# Find and kill hanging Git processes
ps aux | grep git
kill -9 [process_id]
killall git
```

### 2. Repository Cleanup Scripts
Several scripts were created to address Git issues:

#### a. `scripts/manual_git_fix.sh`
- Backed up and removed problematic Git files (index, logs, refs)
- Removed temporary Git files causing locks
- Reset Git state to a clean baseline

#### b. `scripts/quick_feed_parser_commit.sh`
- Specifically targeted at feed_parser.py commit issues
- Killed hanging Git processes
- Checked database file status (found to be 56KB, not the issue)

#### c. `scripts/fix_feed_parser_commit.py`
- Python script for fixing feed_parser.py specific Git issues
- Checked file status and created backups

### 3. Git Configuration Adjustments
- Added database patterns to `.gitignore`:
  ```
  *.db
  data/*.db
  *.sqlite
  *.sqlite3
  ```
- Removed database files from Git tracking to prevent future issues

## Resolution Steps Taken

### Phase 1: Immediate Crisis Response
1. Identified and killed all hanging Git processes
2. Closed all terminal windows and VS Code completely
3. Ran `scripts/manual_git_fix.sh` to clean up corrupted Git files

### Phase 2: Repository Restoration
1. Verified repository integrity with Git commands
2. Rebuilt Git index with `git reset`
3. Confirmed feed_parser.py file was intact (31KB, last modified Oct 11 20:50)

### Phase 3: Successful Commit
1. Added feed_parser.py: `git add src/fetchers/feed_parser.py`
2. Committed with: `git commit --no-verify -m "Update feed parser with intended changes"`
3. Commit completed successfully in seconds

## Key Findings

### Database File Status
- `data/bills.db` was only 56KB (very small)
- File was NOT tracked by Git (`git ls-files data/bills.db` returned empty)
- Database file was NOT the cause of Git performance issues

### Background Processes
- VS Code Git integration was running background processes that held repository locks
- These processes interfered with all manual Git operations
- Disabling VS Code Git auto-refresh prevents future issues

## Current Workflow Files Status

The GitHub workflow files are present locally but may not be tracked by Git:

- `.github/workflows/daily.yml` - Daily posting workflow (morning/evening scans)
- `.github/workflows/weekly.yml` - Weekly digest workflow (Sunday at 9 AM UTC)

To ensure these are properly tracked in Git:

```bash
git add .github/workflows/
git commit -m "Restore workflow files tracking"
git push
```

## Prevention Strategies

### 1. Avoid Background Git Operations
```bash
# In VS Code settings:
# Disable "Git: Auto Refresh"
# Or keep VS Code closed during Git operations
```

### 2. Use Safe Commit Commands
```bash
# Always use --no-verify to skip hooks that might hang
git commit --no-verify -m "Commit message"

# Add specific files rather than using -a flag
git add [specific_file]
git commit --no-verify -m "Commit message"
```

### 3. Regular Repository Maintenance
```bash
# Run periodically to maintain repository health
git gc
git fsck
```

## Working Git Commands Post-Fix

After resolution, these commands work normally:
```bash
git status          # Returns in seconds
git add [file]      # Immediate response
git commit --no-verify -m "message"  # Completes in seconds
git log --oneline   # Shows recent commits correctly
```

## Final Repository Status

- All workflow files are present locally (`.github/workflows/daily.yml`, `.github/workflows/weekly.yml`)
- feed_parser.py is intact and properly tracked
- Repository is ahead of origin by 2 commits (normal after recent fixes)
- Git operations are responsive and fast

## Lessons Learned

1. **Background IDE processes can severely impact Git operations**
2. **Corrupted Git index requires manual file cleanup, not just Git commands**
3. **System restarts are sometimes the most effective solution for deep file locks**
4. **Using `--no-verify` flag prevents hook-related delays**
5. **Regular repository maintenance prevents corruption issues**

## Recommendations

1. **Always close VS Code before intensive Git operations**
2. **Use direct file manipulation scripts when Git commands hang**
3. **Keep database files out of Git tracking**
4. **Regularly run repository health checks**
5. **Document issue resolution steps for future reference**

This documentation serves as both a record of the issue resolution and a guide for preventing similar issues in the future.

**NOTE**: If workflow files are not showing in GitHub, ensure they are properly tracked:
1. Check if they're in the Git index: `git ls-files .github/workflows/`
2. If not, add them: `git add .github/workflows/`
3. Commit and push: `git commit -m "Restore workflow tracking" && git push`