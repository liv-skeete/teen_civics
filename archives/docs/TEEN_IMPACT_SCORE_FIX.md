# Teen Impact Score Fix

## Problem
The summarizer was not consistently generating teen impact scores in the required format "Teen impact score: X/10 (description)". The regeneration script detected this issue when checking existing bill summaries.

## Solution
Updated the AI prompt in [`src/processors/summarizer.py`](src/processors/summarizer.py) to explicitly require teen impact scores in the exact format.

## Changes Made

### 1. Updated Prompt Requirements (Lines 120-127)
**Before:**
```
- Teen impact score: [Score from 1-10 based on: direct impact on education/employment/healthcare/tech access (weight: 40%), indirect impact through family/community (weight: 30%), long-term implications for their generation (weight: 30%)]
```

**After:**
```
- **MANDATORY** Teen impact score: MUST use exact format 'Teen impact score: X/10 (brief description)'
  * X must be a number from 1-10
  * Score based on: direct impact on education/employment/healthcare/tech access (40%), indirect impact through family/community (30%), long-term implications for their generation (30%)
  * Examples: 'Teen impact score: 3/10 (minimal direct impact)', 'Teen impact score: 8/10 (affects college affordability)'
  * This field is REQUIRED - do NOT omit it
```

### 2. Updated Examples (Lines 157-170)
**Before:**
```
- Teen impact score: 3/10
- Teen impact score: 8/10
```

**After:**
```
- Teen impact score: 3/10 (minimal direct impact on teens' daily lives)
- Teen impact score: 8/10 (directly affects college affordability and debt burden)
```

## Verification

Tested with two bills from the database:

### Test 1: Black Vulture Relief Act (hr2462-119)
✅ Generated: "Teen impact score: 2/10 (minimal direct impact on teen population)"

### Test 2: Tax Court Improvement Act (hr5349-119)
✅ Generated: "Teen impact score: 3/10 (limited direct impact, but affects family tax matters)"

## Format Requirements

The teen impact score MUST appear in the "👥 Who does this affect?" section with this exact format:
```
Teen impact score: X/10 (description)
```

Where:
- X is a number from 1-10
- Description briefly explains the impact level
- The format is mandatory and cannot be omitted

## Next Steps

The regeneration script can now be run to update all existing bills with properly formatted teen impact scores. The updated prompt ensures all future bill summaries will include this field in the correct format.