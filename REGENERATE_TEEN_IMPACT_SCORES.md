# Teen Impact Score Regeneration Script

## Overview

This script identifies bills in the database that are missing teen impact scores in their summaries and regenerates them using the current enhanced summarizer.

## Background

The archive page now displays teen impact scores and allows sorting by them. However, some bills in the database may have been processed with an older summary format that doesn't include teen impact scores. This script helps identify and fix those bills.

## Usage

### Basic Usage

Run the script with confirmation prompt:
```bash
python3 regenerate_missing_teen_impact_scores.py
```

### Dry Run Mode

Preview which bills would be updated without making any changes:
```bash
python3 regenerate_missing_teen_impact_scores.py --dry-run
```

### Limit Processing

Process only a specific number of bills (useful for testing):
```bash
python3 regenerate_missing_teen_impact_scores.py --limit 5
```

### Combined Options

Dry run with a limit:
```bash
python3 regenerate_missing_teen_impact_scores.py --dry-run --limit 3
```

## What the Script Does

1. **Fetches all bills** from the database
2. **Identifies bills missing teen impact scores** by checking for the pattern "Teen impact score: X/10" in summary fields
3. **Displays a list** of bills that will be processed
4. **Asks for confirmation** before proceeding (unless in dry-run mode)
5. **Regenerates summaries** for each bill using the current enhanced summarizer
6. **Updates the database** with new summaries (unless in dry-run mode)
7. **Provides detailed logging** and progress tracking
8. **Shows summary statistics** at the end

## Safety Features

- **Dry-run mode**: Preview changes without updating the database
- **Confirmation prompt**: Requires explicit user confirmation before processing
- **Detailed logging**: Shows progress for each bill being processed
- **Error handling**: Continues processing even if individual bills fail
- **Validation**: Checks if new summaries include teen impact scores
- **Idempotent**: Safe to run multiple times

## Output

The script provides detailed output including:

- Number of bills fetched from database
- Number of bills missing teen impact scores
- List of bills to be processed
- Progress for each bill (with emoji indicators)
- Summary statistics (total processed, successful, failed)

### Example Output

```
======================================================================
Teen Impact Score Regeneration Script
======================================================================
🔍 DRY RUN MODE - No database changes will be made

📚 Fetching all bills from database...
✅ Retrieved 15 bills from database

🔍 Identifying bills missing teen impact scores...
Found 13 bills missing teen impact scores

📋 Bills to be processed:
  1. hr2267-119: NICS Data Reporting Act of 2025...
  2. hr38-119: Constitutional Concealed Carry Reciprocity Act of 2025...
  3. hr2184-119: Firearm Due Process Protection Act of 2025...

======================================================================
🚀 Starting regeneration process...
======================================================================

[1/3] Processing hr2267-119
  🔄 Calling summarizer for hr2267-119...
  ✅ New summary for hr2267-119 includes teen impact score
  💾 Updating database for hr2267-119...
  ✅ Successfully updated hr2267-119

======================================================================
📊 Summary Statistics
======================================================================
Total bills processed: 3
✅ Successful: 3
❌ Failed: 0

✅ Regeneration complete!
```

## Requirements

- Python 3.7+
- Access to the database (requires proper environment variables)
- Anthropic API key (for the summarizer)

## Environment Variables

The script requires the same environment variables as the main application:

- `DATABASE_URL` or Supabase credentials
- `ANTHROPIC_API_KEY`

## Notes

- The script processes bills one at a time to avoid overwhelming the API
- Each bill regeneration takes approximately 15-20 seconds
- Bills without full text will still be processed but may have limited summaries
- The script is safe to interrupt (Ctrl+C) - it won't leave the database in an inconsistent state

## Troubleshooting

### "No bills found in database"
- Check that your database connection is configured correctly
- Verify that bills exist in the database

### "New summary still missing teen impact score"
- This is a warning, not an error
- The summarizer may not always include teen impact scores for all bill types
- The summary is still updated with the latest format

### API Rate Limits
- If you hit API rate limits, use the `--limit` flag to process fewer bills at a time
- Wait a few minutes between runs if needed

## Related Files

- [`src/database/db.py`](src/database/db.py) - Database functions
- [`src/processors/summarizer.py`](src/processors/summarizer.py) - Enhanced summarizer
- [`app.py`](app.py) - Teen impact score extraction function