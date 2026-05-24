# TeenCivics Security + Backup Audit — 2026-05-18

Two parallel deep audits run in preparation for adding user auth +
gamification + a potential aggregated-data product. Below is the
consolidated findings list + the prioritized remediation plan.

**Status: audits complete. No fixes applied yet — this is the planning doc.**

## Critical findings (act before auth ships)

### B1 — Prod credentials exposed to staging environment
**Source:** `.github/workflows/daily.yml:205-209`
**Risk:** Lateral compromise. Anyone who can write to the staging
GitHub Environment, modify a workflow on `main`, or run an arbitrary
workflow targeting staging can exfiltrate `PROD_DATABASE_URL`.

**Fix:** Restructure the sync job to use a read-only Postgres role
(SELECT grants only on `bills`, `rep_contact_forms`) instead of the
read-write prod URL. Store that read-only DSN in the staging env. The
read-write `PROD_DATABASE_URL` should never be available to any job
running under `environment: staging`.

### B2 — Destructive sync script has no DB-name guard or dry-run
**Source:** `scripts/sync_prod_to_staging.py:111, 159`
**Risk:** If `PROD_DATABASE_URL` and `DATABASE_URL` ever get swapped
(env var order, copy-paste error, manual local run with reversed
env), the script DELETEs all prod rows in `bills` and
`rep_contact_forms` then INSERTs staging data over them. Only safety
check is `prod_url == staging_url`, which doesn't catch swap.

**Fix:**
1. Add a DB-name check: parse the DSN, require `staging` substring
   in the target DB name, abort if missing
2. Add `--dry-run` flag, make it the default; require `--apply` to
   write
3. Add an explicit "TARGET DB: ..." line in script output and
   `--confirm STAGING` arg for paranoid mode

### B3 — Backups are single-tier, untested, unencrypted
**Source:** `.github/workflows/db-backup.yml:67-71`, `plans/BACKUP_AND_RECOVERY.md:14-19`
**Risk:** Only backup is a 30-day GitHub Actions artifact with no
encryption (anyone with `actions:read` can pull every dump — and
soon every user email once auth ships). No automated restore drill.
Railway managed snapshots may or may not be enabled (checklist
unchecked).

**Fix:**
1. Verify Railway snapshots are enabled in dashboard
2. Add age-encryption to backup pipeline:
   `pg_dump … | age -r <pubkey> > backup.age` before artifact upload
3. Add a second destination: push encrypted dump to Cloudflare R2
   (~$1/mo) with object-lock for 1yr — ransomware-resistant
4. Add a monthly automated restore drill that `pg_restore --list`
   smoke-tests the latest backup. Fail loudly if it errors

## High findings (must fix before user accounts)

### B4 — No migration framework
**Source:** `scripts/add_*.py` (15+ ad-hoc files), `src/database/connection.py:414-574`
**Risk:** Schema changes are roll-forward-only with no rollback,
no version tracking, no transaction wrapping. `users`, `magic_links`,
`civitas_ledger` will need constraints, indexes, foreign keys, and
corrective migrations later. Cannot safely evolve without this.

**Fix:** Adopt Alembic. Add to `requirements.txt`,
`alembic init migrations/`, baseline existing schema, write every
future change as a versioned migration. Keep `init_db_tables()` only
for `bills` bootstrap in fresh environments.

### B5 — Sync job not parameterized for new tables
**Source:** `scripts/sync_prod_to_staging.py:170-171`
**Risk:** Once `users` and `civitas_ledger` exist, either (a) adding
them to the sync list nukes test users every night, or (b) leaving
them out lets staging drift from prod in ways that mask bugs.

**Fix:** Decide sync policy per table. `users` and `civitas_ledger`
should NOT sync — staging gets its own test users. Document the
allowlist explicitly in the script and add an assertion that the
allowlist matches expected tables.

### B6 — No alerting on backup or pipeline failures
**Source:** `.github/workflows/*.yml` — all "Notify on failure" steps
just `echo` to Actions logs
**Risk:** Silent failure mode. If `db-backup.yml` fails for two
weeks (e.g. rotated DB credential), nobody notices.

**Fix:**
1. Add Healthchecks.io heartbeat ping from `daily.yml` and
   `db-backup.yml` success steps. Free tier handles this.
2. Configure Healthchecks.io alert to email + (optionally) Slack
   webhook when heartbeat is missed
3. Add UptimeRobot 5-min ping on `/healthz` (free)

### B7 — Voter data already PII-adjacent
**Source:** `votes` table in `src/database/db.py:1801-1830`
**Risk:** Once `votes.voter_id` is linked to `users.id`, you have
identifiable per-teen voting history in unencrypted backups.

**Fix:** Don't expose `votes.voter_id` in the backup pipeline once
it's linkable to users. Either: encrypt `voter_id` at rest, or
include it in the age-encrypted layer (B3) so backups are protected
end-to-end.

## Medium / lower

### B8 — `.env.example` is stale; no canonical secret inventory
**Source:** `.env.example` lists 3 vars; workflow `secrets.` refs show 17+
**Fix:** Update `.env.example` to canonical list. Add a
`plans/SECRETS_INVENTORY.md` documenting which provider owns each.

### B9 — No PITR (point-in-time recovery)
**Source:** `BACKUP_AND_RECOVERY.md:164-168`, RPO = 24h
**Risk:** Vote tampering or accidental UPDATE is recoverable only to
the previous 02:00 UTC snapshot. Up to a day of votes/civitas lost.
**Fix:** Enable Railway PITR if available on plan; otherwise consider
Neon or Supabase which include it. Target RPO ≤ 1 hour for ledger
rows after auth ships.

### B10 — No code-deploy soak / staging gate before prod
**Source:** Railway auto-deploys `main` on push
**Risk:** Bad merge ships to prod instantly with no audit step.
**Fix (future):** Add a manual approval gate in Railway settings
before prod deploys. Or require a 24h soak on staging before main
auto-deploys. Lower priority but worth doing once auth ships.

### B11 — `init_db_tables()` redefines triggers on every cold start
**Source:** `src/database/connection.py:522-538`
**Risk:** Hostile path that triggers init_db can redefine triggers.
**Fix:** Move trigger creation to Alembic migration; run init_db_tables
only on first-boot (check for `bills` table existence first).

### B12 — Backup window collides with daily posting window
**Source:** `db-backup.yml` runs 02:00 UTC = same as `daily.yml`
evening posting scan
**Fix:** Shift backup to 04:00 UTC (post-posting, pre-morning scan).

### B13 — Domain ownership / registrar 2FA not documented
**Fix:** Add a `plans/INCIDENT_RECOVERY.md` documenting registrar
account, 2FA recovery codes location, domain auto-renew status.

## Recommendations for adding user auth + civitas tables

### Day 1 setup (before first signup)

1. **Alembic adopted** — every new table is a migration
2. **PITR enabled or migration to Neon/Supabase scheduled** —
   ledger rows need ≤1 hour RPO
3. **Encrypted backups landed** — age + R2 secondary destination
4. **Read-only prod role for sync job** — B1 fix
5. **Sync allowlist documented** — `users` and `civitas_ledger`
   NOT in it
6. **Healthchecks.io + UptimeRobot pinging** — B6 fix
7. **Privacy policy + ToS drafted** — required before collecting
   email. Mention 30-day backup expiry, right-to-delete, right-to-export

### Schema patterns

```sql
users (
  id UUID PRIMARY KEY,
  email TEXT UNIQUE NOT NULL,
  email_verified BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  deleted_at TIMESTAMPTZ,  -- soft delete for GDPR
  last_login_at TIMESTAMPTZ,
  voter_id UUID UNIQUE,  -- link to anon vote history
  display_name TEXT
)

magic_links (
  token_hash TEXT PRIMARY KEY,  -- SHA-256 of token, never raw
  user_email TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  expires_at TIMESTAMPTZ NOT NULL,
  used_at TIMESTAMPTZ
)
-- Sweep: DELETE WHERE used_at IS NULL AND expires_at < NOW() - INTERVAL '7 days'

civitas_ledger (
  id BIGSERIAL PRIMARY KEY,
  user_id UUID REFERENCES users(id),
  delta INTEGER NOT NULL,  -- always positive for vote awards
  reason TEXT NOT NULL,    -- e.g. 'vote:hres933-119'
  source_bill_id TEXT,
  awarded_at TIMESTAMPTZ DEFAULT NOW()
)
-- Materialized: current_balance = SUM(delta) WHERE user_id = ?
-- Daily cap: COUNT(reason LIKE 'vote:%') WHERE awarded_at::date = today ≤ 2
```

Append-only ledger. Never UPDATE / DELETE. Balance is computed.

### GDPR data deletion

- Soft-delete `users` with `deleted_at`
- Cascade-anonymize: `votes.voter_id → NULL`, `civitas_ledger.user_id → NULL`
- Aggregate rows survive (for the eventual data product), but tied to no user
- Document 30-day backup expiry in privacy policy so deleted users age out

### Right-to-export

- Build `/account/export` endpoint same week as signup
- Returns JSON: `users` row + `votes` rows + `civitas_ledger` rows for that user

## Disaster recovery runbook outline

To be developed into a full `plans/DR_RUNBOOK.md` before auth ships.
Stages:

0. **Detect** — currently absent, needs Healthchecks.io + UptimeRobot
1. **Contain** — rotate secrets, disable Railway auto-deploy, revoke
   GitHub PAT
2. **Assess** — pull GitHub backup artifact, decrypt with age,
   `pg_restore --list` verify, diff suspicious writes
3. **Restore** — spin new Railway Postgres, `pg_restore --clean`,
   update `DATABASE_URL`, smoke-test `/healthz`
4. **Notify** — California SB 1386 / CCPA requires user notification
   within 45 days if email was in breach. Template lives at
   `plans/BREACH_NOTIFICATION_TEMPLATE.md` (TODO before auth ships)
5. **Postmortem** — `data/work/{date}-incident.md` with timeline,
   root cause, audit log diff

## Suggested order of operations

Going from least disruptive to most:

**Wave A — workflow + config (no code changes)** — 1-2 hours
- B12: shift backup window to 04:00 UTC
- B6: add Healthchecks.io heartbeats
- B6: add UptimeRobot ping
- B13: document registrar, 2FA, domain owner in `INCIDENT_RECOVERY.md`
- B8: update `.env.example`, write `SECRETS_INVENTORY.md`

**Wave B — backup hardening** — 2-3 hours
- B3: age-encryption in backup pipeline
- B3: Cloudflare R2 secondary destination
- B3: monthly automated restore-smoke job
- B9: verify Railway snapshots / PITR; document or escalate

**Wave C — prod/staging isolation** — half day
- B1: create read-only prod role; restructure sync job
- B2: add DB-name guard + `--dry-run` default to sync script
- B10: add Railway manual approval gate

**Wave D — migration framework** — 1 day
- B4: adopt Alembic
- B11: move triggers to migration

**Wave E — pre-auth checklist**
- Privacy policy + ToS drafted
- Soft-delete + cascade-anonymize designed into schema
- GDPR export endpoint scaffolded
- Breach notification template written

Only after Wave A-E is the platform ready for `users` table to exist.

## Security audit findings (added 2026-05-18)

The parallel security audit returned. Findings consolidated by
severity.

### Critical (act before next prod deploy)

**S1 — Vote tallies trivially manipulable via `previous_vote`.**
**Source:** `app.py:1361, 1378`; `src/database/db.py:1855-1866`.
**Risk:** The `/api/vote` endpoint accepts a `previous_vote` value
from the client and blindly decrements `poll_results_yes` or
`poll_results_no` based on it. An attacker scripting fresh cookies
with `{vote_type: "no", previous_vote: "yes"}` can move the poll
counter in any direction at will. **This destroys the integrity of
the eventual aggregated-data product.**
**Fix:** Read the voter's *actual* prior vote from the `votes` table
server-side. Never trust client-supplied `previous_vote`. Land
before the data product launches; ideally before next deploy.

**S2 — Rate limiter buckets every user under one Railway proxy IP.**
**Source:** `app.py:111` uses `get_remote_address` which returns
`request.remote_addr`. Railway sits behind a proxy and there's no
`ProxyFix` middleware. `gunicorn_config.py:43` `forwarded_allow_ips
= "*"` only affects access-log fields, not Flask's `remote_addr`.
**Risk:** Every request from every user appears to come from one of
a handful of Railway proxy IPs. The "5/min" admin login limit, the
"10/min" vote limit, and the IP-keyed `ADMIN_LOGIN_ATTEMPTS` are all
*shared globally* across the userbase. A single attacker can spend
the pool first; a single attacker can lock out the rest.
**Fix:** Wrap `app.wsgi_app` with
`werkzeug.middleware.proxy_fix.ProxyFix(x_for=1, x_proto=1)`.
**Land before any new rate limit promises matter** (i.e. before
auth signup limits).

**S3 — Admin lockout is dead code.**
**Source:** `app.py:698, 703-714, 808-818`.
**Risk:** The `ADMIN_LOGIN_ATTEMPTS` dict is declared and
`_prune_login_attempts()` runs on every POST, but no failed-attempt
timestamp is ever *written* into it. The only thing protecting
`ADMIN_PASSWORD` from brute-force is `@limiter.limit("5 per
minute")` — which is shared globally (per S2) and per-worker
(`memory://`), giving effective ~15/min for the whole userbase.
**Fix:** Append `time.time()` to `ADMIN_LOGIN_ATTEMPTS[ip]` on the
failure branch and block when the window count exceeds N. OR delete
the dead structure and rely on per-IP limiter once S2 is fixed.

### High (must fix before adding user accounts)

**S4 — `Cache-Control: public, max-age=60` will leak per-user pages.**
**Source:** `app.py:172` — the fallback Cache-Control header I
added today for social-media link previews.
**Risk:** Today: safe (no authenticated pages exist). The instant
magic-link auth ships, any page rendered for a logged-in user
(showing username, account state, gamification balance) will leak
into Cloudflare/browser caches. User A's profile page could be
served to User B.
**Fix:** Change to `private, max-age=60` AND short-circuit to
`no-store` when `g.user_id` is set. Land before merging auth.

**S5 — CSRF exempted on every public API.**
**Source:** `app.py:1355, 1494, 1645, 1806, 1878`.
**Risk:** Today: protected by SameSite=Lax on `voter_id` (blocks
cross-site fetch). Tomorrow: combined with S1, an attacker page can
get a logged-in user to alter any poll.
**Fix:** Remove `@csrf.exempt` from `/api/vote`, `/api/generate-email`,
the auth endpoints. Add `<meta name="csrf-token">` to `base.html` and
have `script-2026-02-21-v3.js:113` and
`tell-rep-2026-02-21-v3.js:527` send the token in fetch headers (the
admin pattern at `templates/admin/bills.html:147-155` is the model).
Land in the same PR as auth.

**S6 — `voter_id` cookie is an unsigned UUID4.**
**Source:** `app.py:1326-1349`.
**Risk:** Knowing someone else's voter_id today lets you call
`/api/my-votes` and retrieve their full vote history, plus cast or
change votes attributed to them. Currently un-guessable. The
moment that ID is joined to a `users.id` it becomes a
session-equivalent bearer token with no signature, no rotation, two-year
max_age.
**Fix:** Sign the cookie via `itsdangerous` (Flask already loads
`SECRET_KEY`). Or migrate to Flask sessions for authenticated users
and treat `voter_id` as a transient pre-account ID only.

**S7 — `memory://` limiter storage per-worker.**
**Source:** `app.py:113`; 3 Gunicorn workers per `gunicorn_config.py:20`.
**Risk:** Each worker has its own counter. Effective limit per IP is
~3× stated. Combined with S2, real limits are off by ~3× in either
direction.
**Fix:** Point `storage_uri` at Railway's Redis add-on. Code comment
at `app.py:107-108` already calls this out. Land before signup
opens.

**S8 — SECRET_KEY silently regenerated per process boot if env unset.**
**Source:** `app.py:92-98`.
**Risk:** Today: warning only. Tomorrow: with magic links, a SECRET_KEY
rotation invalidates every magic link in flight. With `preload_app`
all workers share one key on boot, but a worker crash + cold restart
can land workers on disagreeing keys.
**Fix:** Make absence of `SECRET_KEY`/`FLASK_SECRET_KEY` *fatal* in
production (gate on `RAILWAY_ENVIRONMENT`). Not a warning.

### Medium (good hardening, before more prominent)

**S9 — SQL f-string interpolation patterns (verified safe today, fragile pattern).**
**Source:** `src/database/db.py:408, 429, 454, 530, 789, 794, 837, 842, 873, 904, 932, 941, 986, 1014, 1038, 1062, 1087, 1117, 1134, 1151, 1175, 1200`.
**Risk:** Every f-string SQL site I checked interpolates only
module-level constants (PUBLIC_FILTER, ARCHIVE_COLUMNS, etc.). All
user values flow through psycopg2 `%(...)s` binding. No injection
present. But the pattern is fragile — a contributor will copy the
f-string and slot in a request value.
**Fix:** Refactor to `psycopg2.sql.SQL` composition (already used at
`app.py:883, 941, 1121, 1128, 1170, 1251`). Defense in depth.

**S10 — LIKE wildcard injection / ReDoS surface.**
**Source:** `src/database/db.py:777, 977`.
**Risk:** User search `q` is parameterized as `f'%{term}%'`, but
wildcards `%` and `_` inside the user term aren't stripped. A query
of `%_%_%_%` produces an extremely broad pattern. The `len(token)
>= 2` filter + 10-token cap at `db.py:564` bound the damage.
**Fix:** Strip `%` and `_` from user tokens, or rely solely on the
FTS path (LIKE is fallback).

**S11 — `/debug/env` leaks DSN previews.**
**Source:** `app.py:617-642`.
**Risk:** Gated by `app.config["DEBUG"]`. If `FLASK_DEBUG=1` ever
lands in Railway env, the first 30 + last 20 chars of `DATABASE_URL`
become public. Enough to identify host.
**Fix:** Remove the route OR gate on separate `DEBUG_ROUTES` env OR
require admin auth.

**S12 — CSP allows `'unsafe-inline'` on script-src and style-src.**
**Source:** `app.py:151-152`.
**Risk:** Necessary today for inline GA / Cloudflare snippets. Major
XSS-amplification surface.
**Fix:** Move inline scripts to nonce-based (use `g.req_id` as nonce
or a fresh secret per request) and drop `'unsafe-inline'` from
`script-src`. Biggest XSS reduction available without template rewrite.

**S13 — pip-audit and bandit run with `continue-on-error: true`.**
**Source:** `.github/workflows/security-scan.yml:30, 33`.
**Risk:** Security workflow is effectively informational. New CVEs
on pinned deps don't fail builds.
**Fix:** Remove `continue-on-error` from `pip-audit`. Pin a CVE
allowlist file so it fails loudly when new vulns drop.

**S14 — Outdated pinned dependencies.**
**Source:** `requirements.txt`.
**Risk:** `requests==2.31.0` (2.32 fixed CVE-2024-35195 verify-flag
bypass); `gunicorn==21.2.0` (22.0 fixed CVE-2024-1135 request
smuggling); `SQLAlchemy==1.4.46` (if bundled but unused, drop).
**Fix:** Bump requests to 2.32.x, gunicorn to 23.x, audit SQLAlchemy
usage. Flask 3.0.0, Flask-WTF 1.2.1, Flask-Limiter 3.5.0 are current.

**S15 — Admin write endpoints have no rate limit.**
**Source:** `app.py:1041, 1190, 1271`.
**Risk:** Gated by `@admin_required`, but a compromised admin
session can flood Congress.gov / external services via these.
**Fix:** Add `@limiter.limit("30 per minute")` to admin writes.

**S16 — Logger error handlers return `str(e)` in JSON responses.**
**Source:** `app.py:409, 642, 1051, 1071, 1097, 1151, 1188, 1269`.
**Risk:** psycopg2 exceptions can include connection-state and
table-structure detail. Information leakage to attackers.
**Fix:** Replace with generic messages + `req_id` for support
correlation.

### Low (defense in depth)

All XSS sinks audited and verified safe:
- `Markup` only in `format_detailed_html_filter` which escapes content
- `|safe` filters in templates apply after `|e`
- `innerHTML` in JS always wraps interpolated values in `_escHtml()`
- `redirect(url_for('bills', **request.args))` at `app.py:466` is safe
- No SSRF — all `requests.get` calls hit hardcoded hosts
- No path traversal — `send_from_directory` uses hardcoded filenames

Cosmetic:
- `X-XSS-Protection: 1; mode=block` (deprecated, ignored)
- Default session cookie name "session" advertises Flask — rename via
  `SESSION_COOKIE_NAME`
- LLM input (Venice/Anthropic) comes from Congress.gov text, not
  user input — prompt injection risk is bounded to public bill text

## Pre-auth security gate

Before the first `users` row exists in production, the following
**must** be done (combined with the backup checklist above):

- [ ] **S1** Fix `previous_vote` trust (read server-side)
- [ ] **S2** Install ProxyFix middleware (or rate limits are global)
- [ ] **S3** Either implement or delete `ADMIN_LOGIN_ATTEMPTS`
- [ ] **S4** Cache-Control rewrite (no-store for authenticated)
- [ ] **S5** Remove `@csrf.exempt` from public APIs; add tokens in JS
- [ ] **S6** Sign `voter_id` cookie or move to Flask session
- [ ] **S7** Redis-backed rate limiter (shared state)
- [ ] **S8** SECRET_KEY mandatory in prod (fatal on absence)
- [ ] **S11** Remove or admin-gate `/debug/env`
- [ ] **S14** Bump requests + gunicorn versions
- [ ] **S16** Generic error responses (no `str(e)` leak)

S9 (SQL refactor), S10 (LIKE wildcard stripping), S12 (CSP nonces),
S13 (CI security gate), S15 (admin rate limit) can ship in the
follow-up hardening pass.

## What this DOESN'T cover

- Specific Alembic baseline strategy — needs follow-up
- Exact age key custody (1Password vault? hardware key?) — needs
  follow-up
- Per-state breach notification timelines for the future ToS
- Penetration testing (different exercise; consider after auth ships)
