# Pre-Venice Migration Backup

**Backup Created:** 2026-01-21
**Purpose:** Preserve Anthropic API configuration before migrating to Venice AI

## Backed Up Files

| File | Purpose |
|------|---------|
| `summarizer.py` | Main AI summarization logic using Anthropic |
| `config.py` | Configuration including Anthropic API settings |
| `orchestrator.py` | Main workflow including Substack integration |
| `.env.example` | Environment variable template |
| `requirements.txt` | Python dependencies including anthropic SDK |
| `daily.yml` | GitHub Actions daily workflow |
| `weekly.yml` | GitHub Actions weekly workflow |
| `test-orchestrator.yml` | GitHub Actions test workflow |
| `manage.py` | Management scripts that use the API |

## Migration Details

- **From:** Anthropic API (direct)
- **To:** Venice AI (OpenAI-compatible endpoint)
- **New Model:** `claude-sonnet-45`
- **Venice Endpoint:** `https://api.venice.ai/api/v1`

## Why This Backup Exists

The site was running successfully with Anthropic API. This backup allows:
1. Quick rollback if Venice migration has issues
2. Reference for debugging migration problems
3. Documentation of the working pre-migration state

## Rollback Instructions

To rollback to Anthropic API:
1. Copy all files from this backup folder to their original locations
2. Ensure `ANTHROPIC_API_KEY` is set in environment
3. Update GitHub Secrets if needed
4. Redeploy

## Files Not Backed Up (but important)

- `.env` - Contains actual API keys (never commit to git)
- Database - Remains unchanged in migration
