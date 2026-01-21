# Dual-Scan Daily Workflow Implementation

## Overview

This document describes the implementation of a dual-scan daily workflow for bill posting, designed to maximize engagement (morning posts) while ensuring coverage (evening fallback).

## Implementation Summary

### 1. New GitHub Actions Workflow

**File:** `.github/workflows/daily.yml`

- **Morning Scan:** 9:00 AM EDT (13:00 UTC)
  - Runs at `cron: '0 13 * * *'`
  - During EST (winter), runs at 8:00 AM ET
  - Primary scan for maximum engagement

- **Evening Scan:** 10:30 PM EDT (02:30 UTC next day)
  - Runs at `cron: '30 2 * * *'`
  - During EST (winter), runs at 9:30 PM ET
  - Fallback scan to catch late-arriving bills

### 2. Duplicate Prevention Logic

**New Function:** `has_posted_today()` in `src/database/db.py`

```python
def has_posted_today() -> bool:
    """
    Check if any bill has been posted to Twitter/X in the last 24 hours.
    Uses the updated_at timestamp which is set when tweet_posted is updated to TRUE.
    
    Returns:
        bool: True if a tweet was posted in the last 24 hours, False otherwise
    """
```

**Key Features:**
- Queries database for any bills posted in last 24 hours
- Uses PostgreSQL's `INTERVAL '24 hours'` for precise time checking
- Logs clearly when skipping due to already posted today
- Fails open (returns False on error) to allow posting

### 3. Orchestrator Updates

**File:** `src/orchestrator.py`

**Changes:**
1. Added scan type detection (MORNING/EVENING/MANUAL) based on current ET time
2. Added duplicate prevention check at start of main() function
3. Imports `has_posted_today` from database module
4. Skips processing if a bill was already posted in last 24 hours

**Logic Flow:**
```
1. Determine scan type (MORNING/EVENING/MANUAL)
2. Initialize database
3. Check has_posted_today()
   - If True: Skip processing, exit with success
   - If False: Continue with normal workflow
4. Fetch bills, process, and post
```

## How It Works

### Scenario 1: Morning Scan Finds and Posts Bill
1. Morning scan runs at 9:00 AM EDT
2. `has_posted_today()` returns False (no recent posts)
3. Orchestrator fetches bills from Congress.gov
4. Finds new bill, processes, and posts to Twitter
5. Database `updated_at` timestamp set to current time
6. Evening scan runs at 10:30 PM EDT
7. `has_posted_today()` returns True (bill posted < 24h ago)
8. Evening scan exits early - **no duplicate post**

### Scenario 2: Morning Finds Nothing, Evening Posts
1. Morning scan runs at 9:00 AM EDT
2. `has_posted_today()` returns False
3. No bills in "Bills Received Today" feed
4. Morning scan exits (nothing to post)
5. Bill arrives on Congress.gov later in the day
6. Evening scan runs at 10:30 PM EDT
7. `has_posted_today()` returns False (no posts in last 24h)
8. Evening scan finds bill, processes, and posts
9. **Bill successfully posted despite late arrival**

### Scenario 3: Both Scans Find Nothing
1. Morning scan: No bills, exits
2. Evening scan: No bills, exits
3. No posts made (correct behavior)

## Timezone Handling

### DST Awareness
- Cron schedules run in UTC (no DST adjustment)
- During EDT (Mar-Nov): Schedules align with intended ET times
- During EST (Nov-Mar): Schedules run 1 hour earlier in ET
  - Morning: 8:00 AM EST instead of 9:00 AM
  - Evening: 9:30 PM EST instead of 10:30 PM

### Why This Is Acceptable
- Congress is most active during EDT (when in session)
- Winter schedule still provides good coverage
- Duplicate prevention works regardless of timezone

## Database Schema

The implementation relies on existing database fields:

```sql
CREATE TABLE bills (
    ...
    tweet_posted BOOLEAN DEFAULT FALSE,
    tweet_url TEXT,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    ...
)
```

- `updated_at` is automatically updated when `tweet_posted` changes to TRUE
- Trigger ensures `updated_at` is always current
- Query uses `updated_at >= NOW() - INTERVAL '24 hours'` for precision

## Testing

### Test Files Created
1. `test_timezone_conversions.py` - Verifies UTC/ET conversions
2. `test_dual_scan_workflow.py` - Comprehensive workflow testing

### Test Results
All tests passed:
- ✅ `has_posted_today()` function works correctly
- ✅ Scan type detection accurate for all times
- ✅ Duplicate prevention logic sound
- ✅ Timezone handling correct

## Deployment

### To Enable Dual-Scan Workflow

1. **Commit the changes:**
   ```bash
   git add .github/workflows/daily.yml
   git add src/orchestrator.py
   git add src/database/db.py
   git commit -m "Implement dual-scan daily workflow with duplicate prevention"
   ```

2. **Push to GitHub:**
   ```bash
   git push origin main
   ```

3. **Verify in GitHub Actions:**
   - Go to repository → Actions tab
   - Should see "Daily TeenCivics Bill Posting" workflow
   - Can manually trigger with "Run workflow" button

### To Disable Old Weekly Workflow (Optional)

If you want to disable the old weekly workflow:
1. Rename `.github/workflows/weekly.yml` to `.github/workflows/weekly.yml.disabled`
2. Or delete the file entirely

## Monitoring

### Check Workflow Runs
- GitHub Actions tab shows all runs
- Each run logs:
  - Scan type (MORNING/EVENING/MANUAL)
  - Current time in both UTC and ET
  - Whether duplicate prevention triggered
  - Bill processing results

### Check Database
Query to see recent posts:
```sql
SELECT bill_id, tweet_posted, updated_at 
FROM bills 
WHERE tweet_posted = TRUE 
ORDER BY updated_at DESC 
LIMIT 10;
```

## Benefits

1. **Maximum Engagement:** Morning posts catch peak Twitter activity
2. **Complete Coverage:** Evening scan catches late-arriving bills
3. **No Duplicates:** Automatic prevention of posting same bill twice
4. **Resilient:** Works even if one scan fails
5. **Transparent:** Clear logging of scan type and decisions

## Limitations

1. **DST Shifts:** Cron times shift by 1 hour during EST (winter)
   - Acceptable because Congress is less active in winter
   - Could be fixed with two separate cron schedules if needed

2. **24-Hour Window:** Uses 24-hour window for duplicate prevention
   - Prevents posting same bill on consecutive days
   - Appropriate for daily workflow

3. **Single Bill Per Day:** Only posts one bill per day
   - By design - maintains quality over quantity
   - Could be modified if needed

## Future Enhancements

Potential improvements:
1. Add separate cron schedules for EST vs EDT
2. Add metrics tracking (posts per scan type)
3. Add alerting for consecutive failed scans
4. Add dry-run mode testing in CI/CD

## Conclusion

The dual-scan workflow is production-ready and provides:
- ✅ Reliable daily bill posting
- ✅ Duplicate prevention
- ✅ Fallback coverage
- ✅ Clear logging and monitoring
- ✅ Tested and verified implementation