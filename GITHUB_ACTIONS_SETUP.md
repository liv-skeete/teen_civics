# GitHub Actions Setup Guide

## Overview

This guide provides instructions for configuring the GitHub Actions workflow for the TeenCivics application. The workflow requires several secrets to be set up in the repository to function correctly.

---

## Issue 1: Missing Required Secrets

### Error Message:
```
❌ Missing required secrets: ['CONGRESS_API_KEY', 'ANTHROPIC_API_KEY', 'TWITTER_API_KEY', 'DATABASE_URL']
```

### Solution:

You need to add these secrets to your GitHub repository:

1.  **Go to Repository Settings:**
    *   Navigate to your repository on GitHub.
    *   Click `Settings` → `Secrets and variables` → `Actions`.
    *   Click `New repository secret`.

2.  **Add Each Secret:**

    *   `CONGRESS_API_KEY`: Your Congress.gov API key.
    *   `ANTHROPIC_API_KEY`: Your Anthropic API key.
    *   `TWITTER_API_KEY`: Your Twitter API key.
    *   `TWITTER_API_SECRET`: Your Twitter API secret.
    *   `TWITTER_ACCESS_TOKEN`: Your Twitter access token.
    *   `TWITTER_ACCESS_SECRET`: Your Twitter access token secret.
    *   `TWITTER_BEARER_TOKEN`: Your Twitter bearer token.
    *   `DATABASE_URL`: Your PostgreSQL connection string from Railway.

---

## Issue 2: PostgreSQL SSL Connection Error

### Error Message:
```
SSL connection has been closed unexpectedly
```

### Root Cause:
The `DATABASE_URL` secret needs to be correctly configured for SSL, which is required by most cloud-hosted PostgreSQL providers, including Railway.

### Solution:

Most modern database providers, including Railway, provide a `DATABASE_URL` that already includes the necessary SSL configuration (`sslmode=require`).

**Correct Format:**
```
postgresql://user:password@host:port/database?sslmode=require
```

**Steps to Verify:**
1.  Go to `Settings` → `Secrets and variables` → `Actions`.
2.  Find the `DATABASE_URL` secret.
3.  Ensure that the connection string includes `sslmode=require`. If not, add it to the end of the URL.

---

## Issue 3: Twitter API Duplicate Content Error

This is expected behavior when a bill has already been tweeted. The application is designed to handle this gracefully by logging the event and moving on to the next bill. No action is needed.

---

## Issue 4: Twitter API Access Level

The application is designed to work with the Free/Basic tier of the Twitter API. No action is needed unless you want to add features that require a higher access level.

---

## Verification Checklist

Before re-running the workflow, verify:

- [ ] All 8 secrets are added to GitHub Actions.
- [ ] The `DATABASE_URL` is correct and includes SSL configuration.
- [ ] Twitter API credentials are valid and active.

---

## Testing the Fix

After adding all secrets:

1.  **Manual Trigger:**
    *   Go to the `Actions` tab in GitHub.
    *   Select "Daily TeenCivics Bill Processing".
    *   Click "Run workflow".

2.  **Watch the Logs:**
    *   Monitor the workflow for any errors.
    *   Look for "Database connection successful" and other success messages.

---

## Summary

The application code is production-ready. The most common cause of workflow failures is incorrect or missing secrets in the GitHub repository settings.