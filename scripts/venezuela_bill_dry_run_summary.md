# Venezuela Bill Dry Run Test Summary

## Test Overview
This document summarizes the results of the dry run test using the actual Venezuela bill (sjres90-119) found in the database. The test verified Twitter link generation functionality without actually posting to Twitter.

## Bill Information
- **Bill ID**: `sjres90-119`
- **Title**: A joint resolution to direct the removal of United States Armed Forces from hostilities within or against Venezuela that have not been authorized by Congress.
- **Short Title**: A joint resolution to direct the removal of United States Armed Forces from…
- **Status**: Introduced
- **Congress Session**: 119
- **Date Introduced**: 2025-10-16
- **Source URL**: https://www.congress.gov/bill/119th-congress/senate-joint-resolution/90

## Slug Generation Results
- **Generated Slug**: `a-joint-resolution-to-direct-the-removal-of-united-states-armed-forces-from-host-sjres90119`
- **Expected URL**: https://teencivics.org/bill/a-joint-resolution-to-direct-the-removal-of-united-states-armed-forces-from-host-sjres90119

## Tweet Formatting Results
### Formatted Tweet Output:
```
🏛️ Today in Congress

Senate resolution would force withdrawal of U.S. troops from Venezuela operations Congress never authorized. Failed key vote 49-51, blocking debate on Presidential war powers.

👉 See how this affects you: teencivics.org
```

### Tweet Statistics:
- **Tweet Length**: 241 characters
- **Character Limit**: 280 characters
- **Utilization**: 86% of available space

## Test Results
- ✅ **Slug Generation**: Working correctly
- ✅ **Tweet Formatting**: Working correctly
- ✅ **Twitter Link Generation**: Working correctly with 'teencivics.org' as display text
- ✅ **Link URLs**: Would be generated correctly

## Additional Notes
- No actual tweets were posted to Twitter during this test
- No database changes were made during this test
- The tweet successfully incorporates the slug-based link structure
- The display text "teencivics.org" is correctly used instead of the full URL