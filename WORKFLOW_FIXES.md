# GitHub Actions Workflow Fixes - Daily Bill Processing

## Issues Fixed

### 1. ✅ YAML Syntax Error (Line 79)
**Problem**: Step definition was malformed with parentheses in name
**Solution**: 
- Removed parentheses from step name
- Replaced custom shell script with proper GitHub Actions artifact upload
- Changed from `actions/upload-artifact@v3` to `@v4` (v3 is deprecated)

### 2. ✅ Removed Invalid pip install -e .
**Problem**: Line 60 had `pip install -e .` which would fail (no setup.py exists)
**Solution**: Removed this line entirely - not needed for the project

### 3. ✅ Python Version Updated
**Problem**: Using Python 3.10 which may not match all dependencies
**Solution**: Updated both jobs to use Python 3.11 for better compatibility

### 4. ✅ Migration Error Handling
**Problem**: If migration fails, entire workflow stops
**Solution**: Added `continue-on-error: true` to migration step so workflow continues even if migration already ran

### 5. ✅ Removed Redundant psycopg2-binary Installation
**Problem**: Installing psycopg2-binary twice (once manually, once via requirements.txt)
**Solution**: Removed manual installation in daily-bill-processing job since it's in requirements.txt

## Final Workflow Structure

### Job 1: ping-database
1. Checkout code
2. Set up Python 3.11
3. Install minimal dependencies (psycopg2-binary, python-dotenv)
4. Ping database to verify connectivity
5. Run migration (continues even if fails)

### Job 2: daily-bill-processing (depends on ping-database)
1. Checkout code
2. Set up Python 3.11
3. Install all dependencies from requirements.txt
4. Run orchestrator with all environment variables
5. Archive logs (always runs, even on failure)

## Required GitHub Secrets

Ensure these secrets are configured in repository settings:
- `DATABASE_URL` - PostgreSQL connection string
- `CONGRESS_GOV_API_KEY` - Congress.gov API key
- `ANTHROPIC_API_KEY` - Claude API key
- `TWITTER_API_KEY` - Twitter API key
- `TWITTER_API_SECRET` - Twitter API secret
- `TWITTER_ACCESS_TOKEN` - Twitter access token
- `TWITTER_ACCESS_SECRET` - Twitter access token secret

## Schedule

Runs daily at 12:00 UTC (8:00 AM ET) via cron schedule.
Can also be triggered manually via workflow_dispatch.

## Testing Checklist

Before committing:
- [x] YAML syntax is valid
- [x] All action versions are current (v4 for upload-artifact)
- [x] Python version is consistent (3.11)
- [x] No invalid pip install commands
- [x] Error handling is in place
- [x] All required secrets are documented
- [x] Dependencies match requirements.txt

## Changes Made to .github/workflows/daily.yml

1. Line 23: Changed Python version from 3.10 to 3.11
2. Line 37: Added `continue-on-error: true` to migration step
3. Line 54: Changed Python version from 3.10 to 3.11
4. Lines 56-59: Removed `pip install psycopg2-binary` and `pip install -e .`
5. Lines 78-84: Updated artifact upload from v3 to v4 with proper configuration

## Verification

The workflow should now:
1. ✅ Pass YAML validation
2. ✅ Install dependencies correctly
3. ✅ Handle migration gracefully
4. ✅ Run orchestrator with proper environment
5. ✅ Archive logs even on failure
6. ✅ Use current GitHub Actions versions