# Python Cleanup Roadmap — 2026-05-18

Living plan from the second-pass Python deep audit. Builds on the
first audit (consolidated in `SECURITY_BACKUP_AUDIT_2026-05-18.md`).
Goal: 4 sequenced PRs over ~7 sessions / 2-3 weeks, ~1,500 net lines
removed, building the foundation needed before user auth ships.

**Status: planning doc only. No code changes have been made yet.**

---

## Order of operations

| PR | Title | Diff | Effort | Risk |
|---|---|---|---|---|
| **1** | Dead code & imports | ~−800 / +20 | ~2 hrs | LOW |
| **2** | Env-var centralization | ~+250 / −180 | ~4 hrs | MEDIUM |
| **3** | Alembic baseline | ~+400, later −1500 | ~3 hrs + follow-up | MEDIUM-HIGH |
| **4** | `db.py` module split | ~+2000 / −1950 (net 0) | ~5 hrs | HIGH |

Ship in this order strictly. Each PR is independently revertable.
PR 1 buys safety. PR 2 buys clarity. PR 3 unblocks user-account work.
PR 4 finishes the foundation.

---

## PR 1 — Dead code removal

**Effort:** ~2 hours / 1 session
**Risk:** LOW — pure deletion of unreferenced code, verified by grep.

### Files to delete (entire file)

| Path | Why |
|---|---|
| `scripts/facebook_publisher.py` (89 lines) | Duplicate of `src/publishers/facebook_publisher.py`; zero workflow references |
| `src/weekly_digest.py` (55 lines) | TODO-only placeholder. Only reference is commented-out cron in `weekly.yml:71` |
| `.github/workflows/weekly.yml` | Disabled cron (`schedule:` commented at lines 4-5), calls only the dead script above |
| `scripts/inspect_latest_bill.py` | No references anywhere |
| `scripts/staging_diagnostic.py` | No references |
| `scripts/staging_reset_preview.py` | No references |
| `scripts/staging_argument_report.py` | No references |
| `src/database/db_utils.py` | Only one caller (`scripts/list_bills.py:9`) which can import directly from `src.database.db`. Also has a bug at line 38 (`get_bills_by_date_range` in `__all__` but not imported) |

### Functions to delete (inside surviving files)

| File:line | Function | Why |
|---|---|---|
| `src/database/db.py:1714-1733` | `update_bill_teen_impact_score` | Defined, zero callers |
| `src/fetchers/feed_parser.py:756` | `fetch_recent_bills` | Defined, zero callers |
| `src/database/db.py:95-114` | `bill_exists` (only if also dropping `db_utils.py`) | Only used via re-export, no real caller |
| `src/database/db.py:365-381` | `search_bills_by_title` | Only re-export, no callers (app uses `search_tweeted_bills`) |
| `src/database/db.py:547-553` | `fts_available` | Vestigial SQLite-era stub; test refs only |

### Minor cleanups

- `src/orchestrator.py:49, 59` — redundant `import re` (already imported at module top via `feed_parser`)
- `src/database/db.py:1482` — stale "Duplicate mark_bill_as_problematic removed" comment with no associated code

### Unused imports in `app.py:120` block (5 symbols)

Per the first audit: `get_all_bills`, `get_all_tweeted_bills`,
`update_poll_results`, `search_tweeted_bills`,
`count_search_tweeted_bills`, `summarize_title`. Verify and remove.

### Tests to run before merge

- `pytest tests/`
- `python -m py_compile` on every remaining file
- Manually trigger `daily` workflow on staging once

**Net: ~800 lines deleted.**

---

## PR 2 — Env-var centralization

**Effort:** ~4 hours / 1-2 sessions
**Risk:** MEDIUM — touches every publisher, summarizer, orchestrator.
Easy to miss a default value.

### Background

40 `os.getenv` / `os.environ.get` calls live outside `src/config.py`.
~25 of them should be folded into `Config` dataclasses. The other ~15
legitimately stay (test fixtures, gunicorn lifecycle, per-DB script
targeting, runtime introspection).

### New dataclasses to add to `src/config.py` (~lines 95-115)

```python
@dataclass(frozen=True)
class ThreadsConfig:
    user_id: str
    access_token: str

@dataclass(frozen=True)
class BlueskyConfig:
    handle: str
    app_password: str

@dataclass(frozen=True)
class FacebookConfig:
    page_id: str
    page_token: str

@dataclass(frozen=True)
class OrchestratorConfig:
    enrichment_timeout_seconds: int = 120
    replenish_target: int = 10
    replenish_time_budget_seconds: int = 1080
    daily_bills_frozen: bool = False
    retry_problematic_only: bool = False
    retry_problematic_limit: int = 10
    strict_posting: bool = True
```

### Existing classes to extend

- **`VeniceConfig`** — add `summarizer_model`, `summarizer_fallback`,
  `argument_model`, `argument_fallback` (consolidate 4 reads in
  `summarizer.py:20-37` + `argument_generator.py:15-16`)
- **`FlaskConfig`** — add `url_prefix`, `secret_key`, `admin_password`
  (consolidate `app.py:70, 93-97, 696`)
- **`DatabaseConfig`** — add `app_name` (consolidate
  `connection.py:118, 157`)

### Files updated to read from `get_config()`

- `src/fetchers/congress_fetcher.py:29`
- `src/fetchers/feed_parser.py:211, 394, 617`
- `src/publishers/twitter_publisher.py:25-29` (5 reads → 1)
- `src/publishers/threads_publisher.py:24, 25, 46, 47, 60, 61`
- `src/publishers/bluesky_publisher.py:24-25`
- `src/publishers/facebook_publisher.py:23-24, 40-41, 54-55`
- `src/processors/summarizer.py:20, 23, 24, 37`
- `src/processors/argument_generator.py:15-16`
- `src/orchestrator.py:136, 141, 144, 286, 302, 303, 1022`
- `app.py:70, 93-97, 696`
- `scripts/backfill_sponsor_data.py:36`
- `scripts/backfill_bill_status.py:76`
- `scripts/backfill_problematic_bills.py:79`
- `scripts/manage.py:146`

### Files that legitimately stay direct env reads

- `tests/conftest.py:33` (fixture sentinel)
- `gunicorn_config.py:14` (runs before `src/` importable)
- `scripts/sync_prod_to_staging.py`, `verify_staging.py`,
  `cleanup_limbo_bills.py`, `problematic_recheck_periodic.py`,
  `problematic_recheck_audit.py` (per-DB targeting; each picks
  different `DATABASE_URL` / `PROD_DATABASE_URL` /
  `STAGING_DATABASE_URL`)
- `scripts/fb_token_exchange.py:39-41` (one-shot CLI)
- `app.py:635, 638, 1338, 1339, 2088, 2097` (runtime introspection —
  `RAILWAY_ENVIRONMENT`, `FLASK_ENV`, `PYTHONPATH`)

### Tests to run before merge

- Full `pytest`
- Dry-run orchestrator locally with each new config section validated
- Manual smoke of `/admin` login (validates `ADMIN_PASSWORD`
  migration)
- Staging workflow run end-to-end

**Net: ~+70 lines (mostly the new config dataclasses).**

---

## PR 3 — Alembic baseline

**Effort:** ~3 hours / 1 session, plus a later session to delete the
ad-hoc migration scripts.
**Risk:** MEDIUM-HIGH — baseline must match prod byte-for-byte or
future migrations corrupt data.

### Current state of schema management

- **`src/database/connection.py:414-574`** `init_db_tables()` —
  `CREATE TABLE IF NOT EXISTS` + inline `ALTER TABLE ADD COLUMN`
  checks. Runs on every connection-pool bootstrap.
- **15+ `scripts/add_*.py`** one-shot migrations. Historical record,
  not idempotent.
- Three tables: `bills`, `votes`, `rep_contact_forms`. Plus the
  `update_updated_at_column()` trigger function.

### Baseline strategy

1. Add `alembic==1.13.*` to `requirements.txt`. Run
   `alembic init migrations/`.
2. Point `sqlalchemy.url` at `os.getenv("DATABASE_URL")` in
   `migrations/env.py`. No ORM models needed — use raw SQL
   `op.execute()` in migrations.
3. **Write `0001_baseline.py` by hand** (not autogen) that recreates
   current schema exactly. Copy from `init_db_tables()`.
4. In every env (local, staging, prod), run
   `alembic stamp 0001_baseline` — marks DB as already at baseline
   without executing the SQL.

### Coexistence with `init_db_tables()` during transition

- `init_db_tables()` stays as the **bootstrap-only** path for brand-new
  environments (CI test DB, fresh local dev).
- On prod/staging, `init_db_tables()` becomes effectively a no-op
  because all tables already exist.
- Document the new rule: **"If you're adding a column, write an
  Alembic migration. Do NOT touch `init_db_tables`."**
- After 2-3 months of Alembic-only schema changes, delete
  `init_db_tables` entirely and use `alembic upgrade head`.

### First three migrations to ship

1. **`0001_baseline`** — full current schema, manually authored
2. **`0002_drop_deprecated_columns`** — drop columns flagged by
   `scripts/schema_cleanup_migration.py` if any still exist; drop the
   legacy `tweet_posted` migration branch in `connection.py:491-492`
3. **`0003_users_magic_links_civitas_ledger`** — scaffolding-only
   proof migration for upcoming auth tables. Confirms forward +
   downgrade work. Don't run on prod until auth ships.

### Validation gate

Before merge:
```sh
pg_dump --schema-only $PROD_DB > prod_schema.sql
alembic upgrade head  # on a fresh test DB
pg_dump --schema-only $TEST_DB > test_schema.sql
diff prod_schema.sql test_schema.sql
# Must be byte-identical (modulo cosmetic ordering)
```

### Tests to run before merge

- `alembic upgrade head` on fresh DB matches `init_db_tables()` output
- `alembic stamp head` on prod-snapshot of staging produces clean
  `alembic current`
- `pytest` still green

### Follow-up cleanup (PR 3.5 or 3-followup)

Once baseline is stamped in prod:

Delete these 11 ad-hoc migration scripts (they're now obsolete):
- `scripts/add_admin_tracking_columns.py`
- `scripts/add_archive_performance_indexes.py`
- `scripts/add_argument_columns.py`
- `scripts/add_hidden_column.py`
- `scripts/add_recheck_tracking_columns.py`
- `scripts/add_sponsor_columns.py`
- `scripts/add_subject_tags_column.py`
- `scripts/add_votes_table.py`
- `scripts/create_rep_contact_forms_table.py`
- `scripts/schema_cleanup_migration.py`
- `scripts/update_fts_for_sponsor.py`

**Removes ~1,500 lines of historical migration scripts** that are
now redundant.

---

## PR 4 — `src/database/db.py` module split

**Effort:** ~5 hours / 2 sessions
**Risk:** HIGH — every importer in `app.py:120-135`, `orchestrator.py:33-41`,
all tests, all `scripts/` needs path updates.

### Why split

`db.py` is 1,950 lines. Cleanly cleaves along domain seams. Splitting
makes adding gamification (users, magic_links, civitas_ledger) much
easier because we'd add a new module rather than bloat the monolith.

### Target structure

```
src/database/
  __init__.py
  db.py          (~50 lines — thin re-export shim for backward compat)
  _common.py     (~120 lines — shared internals)
  bills_read.py  (~350 lines)
  bills_write.py (~280 lines)
  search.py      (~520 lines)
  problematic.py (~210 lines)
  votes.py       (~150 lines)
  connection.py  (unchanged — already separate)
```

### Per-module contents

**`_common.py`** (the leaf — everything imports from here):
- `db_connect` (db.py:79-86)
- `simulate_safe` (35-44) + `_SIMULATE` flag
- Regex / column constants: `BILL_ID_REGEX`, `ARCHIVE_COLUMNS`,
  `NOT_HIDDEN`, `NOT_PROBLEMATIC`, `HAS_STATUS`, `PUBLIC_FILTER` (47-65)
- `normalize_bill_id` (296-326)
- `deterministic_shorten_title` (328-345)
- `get_current_congress` (67-77)
- `generate_website_slug` (1385-1412)

**`bills_read.py`**:
- `bill_exists`, `bill_already_posted`, `has_posted_today`,
  `get_all_bills`, `search_bills_by_title`, `get_bill_by_id`,
  `get_latest_bill`, `get_latest_tweeted_bill`, `get_bill_by_slug`,
  `get_all_tweeted_bills` (lines 95-165, 348-543)

**`bills_write.py`**:
- `insert_bill`, `update_tweet_info`, `update_bill_title`,
  `update_bill_summaries`, `update_bill_arguments`,
  `update_bill_full_text`, `update_bill_sponsor`,
  `get_bills_without_sponsor` (168-294, 1591-1798)

**`search.py`** (self-contained, no cross-domain calls):
- `fts_available`, `parse_search_query`, `build_fts_query`,
  `build_status_filter`, `build_order_clause`,
  `parse_date_range_from_query`, `build_date_filter`,
  `_search_tweeted_bills_like`, `search_tweeted_bills`,
  `_count_search_tweeted_bills_like`, `count_search_tweeted_bills`,
  `search_and_count_bills` (547-1235)

**`problematic.py`**:
- `select_and_lock_unposted_bill`, `get_unposted_count`,
  `get_post_ready_count`, `get_problematic_count`,
  `mark_bill_as_problematic`, `get_all_problematic_bills`,
  `unmark_bill_as_problematic`, `mark_recheck_attempted` (1238-1587)
- Imports `generate_website_slug` from `_common`

**`votes.py`**:
- `update_poll_results`, `record_individual_vote`,
  `record_vote_and_update_poll`, `get_voter_votes` (462-521, 1801-1950)

### Approach: bottom-up, one domain at a time

Order:
1. `_common` first (no behavior change, just extract). Run tests.
2. `search` (zero cross-domain calls). Run tests.
3. `votes`. Run tests.
4. `problematic`. Run tests.
5. `bills_read` + `bills_write` last (the most-imported, save until
   the rest is stable).

Each extraction is a separate commit on the PR branch. If something
breaks at step 3, we revert step 3 only.

### Backward compat

Keep `src/database/db.py` as a re-export shim during transition:

```python
# src/database/db.py — re-export shim during the split.
# Existing imports work unchanged. Migrate callers to specific
# modules over time, then delete this file.
from src.database._common import *      # noqa: F401,F403
from src.database.bills_read import *   # noqa: F401,F403
from src.database.bills_write import *  # noqa: F401,F403
from src.database.search import *       # noqa: F401,F403
from src.database.problematic import *  # noqa: F401,F403
from src.database.votes import *        # noqa: F401,F403
```

### Tests to run before merge

- Full `pytest`
- Every CLI script in `scripts/` runs `--help` cleanly
- Orchestrator dry-run on staging
- Archive search / vote endpoints exercised manually
- Verify import cycles via `python -c "import src.database.db"` from a
  fresh interpreter

---

## Pre-flight gate

Before starting any of these PRs:

- [ ] Security fixes (S1-S8 from `SECURITY_BACKUP_AUDIT_2026-05-18.md`)
      committed to staging and verified
- [ ] Backup hardening (B1-B6) at least documented; B2 sync-script
      safety landed (DONE)
- [ ] Staging environment confirmed deploying (currently broken per
      live audit — pending Railway dashboard fix from olivia)

After auth ships, schedule a Wave 6 schema audit (see existing task
list) to identify redundant columns and missing indexes — that work
runs through Alembic migrations after PR 3 is in.

---

## Document history

- 2026-05-18 — Initial doc. Five sections of audit + roadmap captured
  from background agent. Ready for execution once pre-flight gates
  resolve.
