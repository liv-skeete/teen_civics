# Security Fixes for Database Credentials Exposure

## Issue Summary

Database credentials were accidentally committed to the git repository in the following files:
- `scripts/verify_migration.py`
- `scripts/migrate_data_to_railway.py`

These files contained hardcoded Supabase and Railway database connection strings which posed a security risk.

## Fixes Applied

### 1. Updated Scripts to Use Environment Variables

Both scripts have been modified to read database connection strings from environment variables instead of hardcoding them:

```bash
# Set environment variables before running scripts
export SUPABASE_DB_URL="postgresql://..."
export RAILWAY_DB_URL="postgresql://..."

# Run scripts
python3 scripts/verify_migration.py
python3 scripts/migrate_data_to_railway.py --migrate
```

### 2. Updated .env.example

Added documentation for the new environment variables in `.env.example`:

```env
# For data migration scripts (if migrating from Supabase)
SUPABASE_DB_URL=postgresql://postgres.[project-ref]:[password]@aws-0-[region].pooler.supabase.com:6543/postgres
RAILWAY_DB_URL=postgresql://postgres:[user]:[password]@[railway-host]:[port]/railway
```

### 3. Created Git History Rewrite Script

A script `scripts/secure_git_history.sh` has been created to remove the sensitive files from git history.

## Recommended Security Actions

### 1. Rotate Database Credentials

Change your database passwords for both Supabase and Railway databases immediately:
- [ ] Rotate Supabase database password
- [ ] Rotate Railway database password

### 2. Update Environment Configuration

Update your `.env` file with the new connection strings:

```env
# For data migration scripts (temporary)
SUPABASE_DB_URL=postgresql://postgres.[new-project-ref]:[new-password]@aws-0-[region].pooler.supabase.com:6543/postgres
RAILWAY_DB_URL=postgresql://postgres:[new-user]:[new-password]@[railway-host]:[port]/railway
```

### 3. Rewrite Git History

Run the secure git history script to remove sensitive information from the repository:

```bash
./scripts/secure_git_history.sh
```

This will:
- Create a backup branch
- Remove sensitive files from git history
- Clean up reflogs and garbage collect

### 4. Force Push Changes

After rewriting history, force push to update the remote repository:

```bash
git push origin main --force
```

**Warning:** All collaborators will need to reset their local repositories:

```bash
git fetch origin
git reset --hard origin/main
```

## Future Prevention

### 1. Add to .gitignore

Consider adding sensitive file patterns to `.gitignore`:

```gitignore
# Ignore files with database credentials
*credentials*.py
*migration*temp*.py
```

### 2. Pre-commit Hooks

Set up pre-commit hooks to scan for sensitive information:

```bash
# Install pre-commit
pip install pre-commit

# Add to .pre-commit-config.yaml
repos:
  - repo: https://github.com/Yelp/detect-secrets
    rev: v1.4.0
    hooks:
      - id: detect-secrets
```

### 3. Environment Variable Validation

Add environment variable validation to scripts:

```python
# Always validate environment variables
SUPABASE_DB_URL = os.environ.get('SUPABASE_DB_URL')
if not SUPABASE_DB_URL:
    raise ValueError("SUPABASE_DB_URL environment variable is required")
```

## Verification

After completing all security fixes:

- [ ] Database credentials have been rotated
- [ ] Git history has been cleaned
- [ ] Remote repository has been updated
- [ ] All collaborators have updated their local repositories
- [ ] Scripts work with environment variables
- [ ] No sensitive information remains in the repository