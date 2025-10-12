# Security Policy: Secrets Handling

This repository follows a strict "No secrets in source" policy. Credentials and tokens must never be committed to the codebase or printed in logs.

## What counts as a secret
- Database URLs and connection strings (e.g., postgresql://user:password@host:port/dbname)
- API keys, OAuth client secrets, access tokens, refresh tokens
- Private keys, certificates, signing secrets
- Any value that would require rotation if exposed

## Approved patterns
- Store secrets in environment variables (.env for local dev; CI/CD secrets in the platform)
- Load them at runtime using src/load_env.load_env()
- Keep an up-to-date .env.example with variable names and safe placeholders only

## Local development
- Copy .env.example to .env and fill in your own values
- Ensure .env is ignored by git (see .gitignore)
- Do not share .env over chat, email, or commit history

## CI/CD
- Store secrets in GitHub Actions Secrets (Settings > Secrets and variables > Actions)
- Reference them in workflows as ${{ secrets.NAME }} and pass them as env vars
- Never echo secrets or write them to logs

## Prohibited patterns (do not do these)
- Hardcoding connection strings or credentials in source files
- Setting os.environ[...] in code with literal secrets
- Printing secrets, even in debug logs

## Code example (approved)

```python
from load_env import load_env
load_env()
```

## Incident response if a secret leaks
- Rotate the leaked secret immediately (database credentials, API keys, etc.)
- Invalidate any exposed tokens
- Purge the secret from commit history if possible, then force-push if safe
- Update CI/CD and .env files with the rotated values
- Audit access logs for misuse

## Reviewer checklist (PRs)
- No occurrences of connection strings with username:password@ in code or docs
- No os.environ assignments with literal secrets
- No secrets in tests or fixtures
- .env.example updated if new variables are introduced
- Optional regexes to search for: "postgresql://", "://[^/]+:[^@]+@", "AKIA", "BEGIN PRIVATE KEY", "SUPABASE_DB_PASSWORD"

## Recommended automation
- Enable pre-commit with detect-secrets or gitleaks to block commits containing secrets
- Run a periodic repo scan in CI for secrets

## Contact
If you suspect a leak, stop work and rotate the secret immediately. Then open a security issue or contact the maintainer.