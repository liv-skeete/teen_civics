# Database Connection Issue - Resolution Guide

## Problem Summary

The TeenCivics Flask application was failing to connect to the PostgreSQL database with the error:
```
ERROR - Error retrieving latest tweeted bill: PostgreSQL database is required but not configured.
```

## Root Causes Identified

### 1. **Environment Variables Not Being Loaded** (FIXED ✅)
**Issue**: The `.env` file was not being loaded before the database modules were imported in `app.py`.

**Solution**: Added `load_env()` call at the top of `app.py` before any database imports:
```python
# CRITICAL: Load environment variables BEFORE importing database modules
from src.load_env import load_env
load_env()
```

### 2. **Environment Variables Read at Import Time** (FIXED ✅)
**Issue**: `src/database/connection.py` was reading environment variables at module import time (when the file was first loaded), before `load_env()` could be called.

**Solution**: Modified `get_connection_string()` to read environment variables at runtime instead of at import time.

### 3. **Invalid Database Credentials** (REQUIRES USER ACTION ⚠️)
**Issue**: The DATABASE_URL in the `.env` file points to a Supabase database that returns:
```
FATAL: Tenant or user not found
```

This means either:
- The Supabase project has been deleted or paused
- The credentials are incorrect
- The database user/password has changed

**Solution Required**: You need to update the DATABASE_URL in your `.env` file with valid credentials.

## How to Fix the Database Credentials

### Option 1: Get New Supabase Credentials

1. Go to your Supabase project dashboard: https://supabase.com/dashboard
2. Navigate to: **Project Settings** → **Database** → **Connection string**
3. Copy the connection string (it should look like):
   ```
   postgresql://postgres.[project-ref]:[password]@aws-0-[region].pooler.supabase.com:6543/postgres
   ```
4. Update the `DATABASE_URL` in your `.env` file with this new connection string

### Option 2: Create a New Supabase Project

If your old project no longer exists:

1. Go to https://supabase.com and create a new project
2. Wait for the project to be provisioned (takes ~2 minutes)
3. Get the connection string from **Project Settings** → **Database**
4. Update your `.env` file with the new DATABASE_URL
5. Run the database initialization:
   ```bash
   python3 -c "from src.database.db import init_db; init_db()"
   ```

### Option 3: Use a Different PostgreSQL Database

If you want to use a different PostgreSQL provider:

1. Set up a PostgreSQL database with your provider
2. Get the connection string in this format:
   ```
   postgresql://username:password@host:port/database_name
   ```
3. Update the `DATABASE_URL` in your `.env` file

## Testing the Connection

After updating your credentials, test the connection:

```bash
python3 test_db_connection.py
```

You should see:
```
1. DATABASE_URL in environment: True
2. Connection string retrieved: True
3. PostgreSQL available: True
4. Database type: postgres
5. Testing database query (get_latest_tweeted_bill)...
   ✓ Success! Retrieved bill: [bill_id]
```

## Code Changes Made

### 1. `app.py`
- Added `load_env()` call before database imports
- Added diagnostic logging to confirm DATABASE_URL is loaded

### 2. `src/database/connection.py`
- Removed module-level environment variable reads
- Modified `get_connection_string()` to read env vars at runtime
- Improved error messages in `is_postgres_available()`
- Enhanced `get_database_type()` error messages

### 3. `.env.example`
- Added DATABASE_URL example with format documentation

## Current Status

✅ **Fixed**: Environment loading issue - `.env` file is now properly loaded
✅ **Fixed**: Timing issue - environment variables are now read at runtime
⚠️ **Requires Action**: Database credentials need to be updated by the user

The application code is now working correctly. The only remaining issue is that the DATABASE_URL credentials in the `.env` file are invalid and need to be updated with valid Supabase (or other PostgreSQL) credentials.