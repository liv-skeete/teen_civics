# Git Commands to Deploy New Workflow

## Step 1: Check Current Status
```bash
git status
```

## Step 2: Add All Changes
```bash
git add .
```

## Step 3: Commit with Message
```bash
git commit -F COMMIT_MESSAGE.txt
```

Or use a shorter commit message:
```bash
git commit -m "Implement feed-based workflow with full text validation

- Add feed parser for Congress.gov Bill Texts Received Today
- Update database schema with text tracking fields
- Enhance congress fetcher with feed support
- Update orchestrator with text validation
- Change GitHub Actions schedule to 8 AM ET
- Add comprehensive tests
- Fix duplicate tweet prevention bug
- Add missing dependencies (lxml, PyMuPDF)"
```

## Step 4: Push to GitHub
```bash
git push origin main
```

## Step 5: Verify Deployment
1. Go to GitHub Actions: https://github.com/liv-skeete/teen_civics/actions
2. Watch the workflow run with the new code
3. Check logs to confirm feed-based processing is working

## Files That Will Be Committed

### New Files:
- `src/fetchers/feed_parser.py` - Feed parser for Congress.gov
- `scripts/migrate_database_schema.py` - Database migration script
- `tests/test_feed_parser.py` - Comprehensive test suite
- `COMMIT_MESSAGE.txt` - This commit message
- `GIT_COMMANDS.md` - These instructions

### Modified Files:
- `src/fetchers/congress_fetcher.py` - Enhanced with feed support
- `src/orchestrator.py` - Updated with text validation
- `src/database/db.py` - Updated insert_bill() for new fields
- `.github/workflows/daily.yml` - Changed schedule to 11:00 UTC
- `requirements.txt` - Added lxml and PyMuPDF

## Expected Outcome

After pushing, the next GitHub Actions run will:
1. Use the new feed-based workflow
2. Only process bills with full text available
3. Validate text before summarization (min 100 chars)
4. Have better duplicate prevention
5. Run at 11:00 UTC (8:00 AM ET) daily

## Troubleshooting

If the workflow still fails with duplicate content:
- This is expected if the same bill was already posted
- The new workflow will skip already-posted bills
- Wait for the next day's run with new bills

If you see "403 Forbidden" from Congress.gov:
- The feed parser includes User-Agent headers to prevent this
- Should work in GitHub Actions environment

If you see Twitter API errors:
- The free tier allows 500 writes/month
- Duplicate content errors are normal for already-posted bills
- The workflow will continue to the next bill