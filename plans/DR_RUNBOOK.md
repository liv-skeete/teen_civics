# Disaster Recovery Runbook

> Last updated: 2026-05-19
> Owner: olivia
> Status: foundation document. Reviewed and exercised at least quarterly.

This runbook covers the operational response when something goes
wrong. **Read this before something breaks.** It's organized by
detection → containment → assessment → restore → notify → postmortem,
matching the standard incident-response phases.

## Quick reference

| Symptom | First action | Section |
|---|---|---|
| Site is fully down | Check Railway dashboard + Cloudflare status | [Section 1](#site-down) |
| Site is up but DB queries fail | Check Postgres add-on status | [Section 2](#db-down) |
| Wrong data appearing on site | Compare hostnames in Railway env vs GH secrets | [Section 3](#data-drift) |
| Suspicious auth activity (auth shipped) | Rotate SECRET_KEY + force logout all | [Section 4](#suspected-breach) |
| Bot abuse spike | Tighten rate limits + enable Turnstile defenses | [Section 5](#bot-abuse) |
| Backup failed silently | Manual `pg_dump` + investigate | [Section 6](#backup-failure) |

---

## Section 0 — Always start here

**Stop. Don't change anything until you've confirmed:**

1. **What env is affected?** Production (`teencivics.org`), staging
   (`teencivics.org/beta`), or both?
2. **When did the symptom start?** Look at the Railway deployments
   tab — was there a recent deploy that correlates?
3. **What did you last change?** GitHub commits in the last 24h?
   Manual Railway env var edits?
4. **Are you sure it's not a Cloudflare edge cache issue?** Hard-refresh.
   Try incognito. Hit the origin URL directly bypassing Cloudflare.

Write down the time you noticed the symptom and the symptom text
verbatim. Past-you 2 hours from now will need this.

---

## Section 1 — Site fully down {#site-down}

### Detect

- UptimeRobot ping fails (once configured)
- Healthchecks.io misses a heartbeat (once configured)
- Manual report from a user

### Contain

- **DO NOT** push more code. Don't try to deploy a fix until you
  understand what broke.
- Check Railway dashboard:
  - Web service → Deployments tab → is the most recent deploy showing
    "FAILED" or "CRASHED"?
  - Web service → Metrics → did CPU/memory spike to limits?
  - Postgres add-on → is it green?
- Check Cloudflare:
  - Status page (cloudflarestatus.com) — major outages happen
  - Account → DNS → is `teencivics.org` still pointing right?

### Assess

If recent deploy failed:
- Railway → web service → Deployments → click failed deploy → View Logs
- Look for the first ERROR line. Usually it's:
  - `ModuleNotFoundError` → missing dep in requirements.txt
  - `psycopg2.OperationalError` → DB connection failing
  - `RuntimeError: FLASK_SECRET_KEY` (post 2026-05-19) → env var
    missing
  - `Application failed to start` → look further up

### Restore

| Cause | Fix |
|---|---|
| Bad deploy | Railway → web service → Deployments → previous successful deploy → **Redeploy** |
| Missing env var | Railway → web service → Variables → add it → Save (auto-redeploy) |
| Out of memory | Railway → web service → Settings → Resources → bump RAM, redeploy |
| Cloudflare DNS misconfigured | Cloudflare → DNS → check A record matches Railway IP |
| Cloudflare outage | Wait. Tweet at @TeenCivics if longer than 30 min. |

### Notify

For a >30 minute outage:
- Tweet from `@TeenCivics` apologizing and confirming you're aware
- If users are logged in (post-auth ship), email subscribers an update
- If a data integrity issue might be involved, hold off on social
  reassurance until you've verified

### Postmortem

Within 24h, write `data/work/{date}-incident.md` covering:
- Timeline (when noticed, when contained, when restored)
- Root cause
- What we'll do to prevent recurrence
- Action items with owners

---

## Section 2 — DB down {#db-down}

### Detect

- `/healthz/db` returns 503
- App throws psycopg2.OperationalError in logs

### Contain

- DO NOT delete or recreate the Postgres add-on. That would lose all
  data.
- DO NOT change the `DATABASE_URL` env var without first confirming
  what DB it currently points at (`hostname` substring).

### Assess

Railway dashboard:
- Postgres add-on → Metrics → connection count exhausted?
- Postgres add-on → Logs → any FATAL or PANIC entries?

If connection pool is exhausted (>100 connections):
- App probably has a connection leak. Restart the web service to
  drain. Investigate `src/database/connection.py` for missing
  `conn.close()` paths.

If FATAL log:
- Likely disk full or OOM in the DB instance. Need to upgrade the
  Railway plan or migrate to a larger Postgres.

### Restore

| Cause | Fix |
|---|---|
| Connection pool exhausted | Restart web service. Investigate leak. |
| Disk full | Railway → Postgres → upgrade plan, or `DELETE` old rows |
| Postgres genuinely crashed | Wait for Railway auto-restart, escalate to Railway support |
| DSN rotated | Get new DSN from Postgres add-on → Connect tab → update web service env var |

### Special case: DB instance is gone / corrupted

This is the bad case. Restore from backup:

```bash
# 1. Provision a new Postgres on Railway
# 2. Get its DSN from the Connect tab
# 3. Pull most recent backup
gh run download --name backup-prod-YYYY-MM-DD  # adjust to actual artifact name

# 4. Restore
pg_restore --clean --if-exists \
  -d "postgresql://...new-postgres-dsn..." \
  backup.dump

# 5. Verify
psql "postgresql://...new-postgres-dsn..." -c "SELECT COUNT(*) FROM bills;"
# Should match expected count from before the incident

# 6. Update Railway web service DATABASE_URL to new DSN
# 7. Wait for redeploy
# 8. Smoke test /healthz/db
```

---

## Section 3 — Data drift / wrong data showing {#data-drift}

This is the lesson from the **2026-05-18 staging incident** — sync
job was writing to an orphaned `hopper` Postgres while the web service
read from `crossover`. Three values must always match:

1. **Railway web service** `DATABASE_URL` env var → hostname X
2. **GitHub Actions secret** `DATABASE_URL` for the same environment
   → hostname X
3. **Local `.env`** for whichever env you're targeting → hostname X

If they don't match, syncs land in one place and reads come from
another. **Fix the mismatch, don't change which DB the web service
reads from** (that's the source of truth — anything else is the
orphan).

### Diagnostic

```sql
-- Connect to each Postgres and run:
SELECT bill_id, date_processed FROM bills ORDER BY date_processed DESC LIMIT 1;
```

The DB the web service reads from will show the date users actually
see on `/`. That's the live one. Sync the others to point at it.

---

## Section 4 — Suspected security breach {#suspected-breach}

(Applies once auth ships and there are real users.)

### Detect

- Anomalous spike in failed magic-link attempts
- Many votes from one user in an impossible time window
- User reports their account "did things they didn't do"
- External notification from researcher or security firm

### Contain

**Move fast on these in order:**

1. **Rotate SECRET_KEY**
   - Railway → web service → Variables → `FLASK_SECRET_KEY` → generate
     new with `python -c "import secrets; print(secrets.token_hex(32))"`
   - This invalidates ALL sessions and ALL signed voter_id cookies
     and ALL pending magic-link tokens. Users get logged out.
   - On the next deploy, the new key takes effect.

2. **Rotate the compromised credential**
   - If it's `DATABASE_URL`: Railway → Postgres → rotate password
   - If it's `CONGRESS_API_KEY` / `VENICE_API_KEY`: rotate at the
     provider portal, update Railway + GitHub secrets
   - If it's a social media token: revoke at the platform, generate new

3. **Disable Railway auto-deploy from main**
   - Railway → Settings → turn off auto-deploy
   - Prevents an attacker who has GitHub access from pushing
     malicious code that deploys to prod

4. **Revoke GitHub access**
   - If the attacker has a GitHub PAT: revoke it
   - Force-reset all collaborator 2FA
   - Review GitHub audit log for the last 30 days

### Assess

- Pull the latest pre-incident backup (from GitHub artifacts)
- `pg_restore --list` to verify integrity
- Compare current prod DB to backup:
  ```sql
  -- Look for suspicious INSERTs
  SELECT * FROM bills WHERE date_processed > '{incident_start_time}';
  SELECT * FROM votes WHERE updated_at > '{incident_start_time}';
  -- (post-auth ship)
  SELECT * FROM users WHERE created_at > '{incident_start_time}';
  SELECT * FROM civitas_ledger WHERE awarded_at > '{incident_start_time}';
  ```

### Restore

If data tampering is confirmed:

- Restore from the most recent pre-incident backup as described
  in Section 2 special case
- Manually re-apply legitimate writes that happened between the
  backup and the incident (this is why audit logs matter)

### Notify

**Required by California SB 1386 / CCPA if user emails were
exposed:** notify affected users within 45 days. We commit to 30
days in the privacy policy.

Use the template at `plans/BREACH_NOTIFICATION_TEMPLATE.md`.

State-specific deadlines may apply (some are shorter — Maryland,
Florida). Lawyer consultation required.

### Postmortem

Within 7 days of restoration, publish a post-incident report (private
to subscribers, or public if olivia chooses). Include:
- What happened
- What data was affected
- What we changed to prevent recurrence
- Whether to notify regulators (state AGs in some states)

---

## Section 5 — Bot abuse spike {#bot-abuse}

### Detect

- Rate limiter rejects spiking in logs
- Vote counts moving impossibly fast
- /signup endpoint hammered (post-auth)
- Cloudflare bot-fight-mode reports unusual traffic

### Contain

Without any code changes:
1. Cloudflare dashboard → Security → enable "Under Attack Mode" or
   raise Bot Fight Mode aggression
2. Cloudflare → Security → WAF → temporarily block the offending
   IP ranges or ASNs

With code (slower):
3. Lower rate limits in `app.py` (e.g. `@limiter.limit("3 per minute")`
   on `/api/vote`) → push to staging → verify → push to main
4. Make Turnstile checks more aggressive (raise threshold or require
   interactive instead of invisible)

### Restore

Once spike subsides:
- Drop the temporary block in Cloudflare (Under Attack Mode is
  bad UX for real users)
- Keep tightened rate limits if the attack reveals our previous
  limits were too generous

### Postmortem

Was this:
- A specific bot operator (block + move on)
- A research scraper (allow but add `Crawl-Delay` to robots.txt)
- Genuine viral traffic (we underspec'd; upgrade limits + infra)

---

## Section 6 — Backup failure {#backup-failure}

### Detect

- `db-backup.yml` workflow shows "failed" in Actions tab
- Healthchecks.io misses the backup heartbeat (once configured)
- `pg_restore --list` on the latest artifact fails

### Contain

Don't panic. A failed backup means we don't have **today's**
backup, but the previous days' backups still exist (30 days
retention).

### Assess

GitHub Actions → db-backup.yml → click failed run → View logs.
Common causes:
- DB connection failed (DB credentials rotated, env var stale)
- Out of disk on the runner (rare; pg_dump > 6GB)
- Auth token expired

### Restore

Fix the cause, then manually trigger the workflow:
- GitHub → Actions → db-backup.yml → Run workflow

Verify the resulting artifact:
```bash
gh run download --name backup-prod-YYYY-MM-DD
pg_restore --list backup.dump | head -20
# Should list relations, indexes — not error out
```

---

## Test schedule

This runbook is useful only if it's been exercised. Schedule:

- **Monthly**: olivia runs through Section 1 mentally, confirms
  Railway dashboard access works, confirms GitHub Actions backup
  artifact is downloadable
- **Quarterly**: olivia restores the most recent backup to a fresh
  Railway Postgres and verifies the restore (without touching prod).
  Document time-to-restore.
- **Annually**: full breach-drill — pretend SECRET_KEY is
  compromised, walk through Section 4 step-by-step, record what was
  smooth vs broken

---

## Inventory: where the credentials live

Document the canonical location for every secret. **Keep this list
current** — if it goes stale during a real incident, you'll spend the
emergency hunting for the password manager URL.

| Secret | Stored in | Rotation procedure |
|---|---|---|
| `FLASK_SECRET_KEY` | Railway env (prod + staging), 1Password vault | Generate new; paste in Railway; old sessions invalidate |
| `DATABASE_URL` (prod) | Railway env, GitHub secret `DATABASE_URL` (prod env) | Rotate password in Railway → Postgres → Connect; sync to GH secret |
| `DATABASE_URL` (staging) | Railway env, GitHub secret `DATABASE_URL` (staging env), local `.env` | Same as above but staging |
| `PROD_DATABASE_URL` | GitHub secret (staging env only, for sync job) | Rotate via Railway prod Postgres + update GH |
| `STAGING_DATABASE_URL` | Local `.env`, scripts only | Same as `DATABASE_URL` staging |
| `CONGRESS_API_KEY` | GitHub secrets (both envs) | api.congress.gov → request new key |
| `VENICE_API_KEY` | GitHub secrets (both envs) | venice.ai dashboard → API keys |
| `TWITTER_*` (5 tokens) | GitHub secrets (prod only) | developer.x.com → app → keys & tokens |
| `BLUESKY_HANDLE` / `BLUESKY_APP_PASSWORD` | GitHub secrets (prod only) | bsky.app → settings → app passwords |
| `FACEBOOK_PAGE_TOKEN` / `FACEBOOK_PAGE_ID` | GitHub secrets (prod only) | developers.facebook.com → app → settings; token never expires (per current Meta config) |
| `THREADS_USER_ID` / `THREADS_ACCESS_TOKEN` | GitHub secrets (prod only) | Threads developer portal |
| `RESEND_API_KEY` (when auth ships) | Railway env (both), GitHub secrets | resend.com → API keys |
| `GOOGLE_OAUTH_CLIENT_*` (when auth ships) | Railway env (both) | console.cloud.google.com → APIs → Credentials |
| 1Password vault master password | olivia's head + 1Password recovery key | If lost, accounts go offline until recovered |

**Maintaining this list is part of the runbook.** When a new credential
is added, update this table in the same commit.

---

## Things this runbook deliberately does NOT cover

- **Legal compliance for individual data requests** — that's its own
  process, handled by the lawyer.
- **Press response** — if something major is in the news, olivia is
  the spokesperson. No statements from automation or contractors.
- **Long-term infrastructure decisions** (Railway vs Neon vs
  self-hosted Postgres) — those are not incident-response work,
  they're roadmap. Defer until calm.

---

## Contributing to this document

If you respond to an incident and any part of this runbook was
wrong, incomplete, or missing: **fix it in the same PR as your
postmortem**. Stale runbooks are worse than no runbook.
