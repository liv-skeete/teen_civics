# TeenCivics Auth + Gamification + Civi Plan

Living document. Captures decisions made in the 2026-05-18 planning
session and the future feature backlog. Update when scope changes.

---

## Decisions locked in

### Currency
**"Votes"** — single currency. The currency of a politician is votes;
the currency a TeenCivics user earns is also votes. Same word both
places. Clean mental model.

### Login model — robust, defense-in-depth, two paths
Two equal entry points so users pick what feels natural. Both share
the same `users` row + session state. The goal: hard to bot, easy
for real teens.

**Path A — magic link via email (default)**
- Email-only signup; no password to lose, no breach exposure
- Service: **Resend** (free tier covers our scale)
- Token: 32-byte random hex, hashed (SHA-256) before storage
- TTL: 15 min from creation
- Used tokens retained 90 days for audit, then redacted
- Email-verified by definition (you clicked the link)

**Path B — Sign in with Google (alternative)**
- OAuth 2.0 via Google Identity Services
- Library: `Authlib` (mature, Flask-native) OR Google's official
  `google-auth` + `google-auth-oauthlib`. Pick Authlib for simpler
  callback flow.
- Required scopes: `openid email` only — NOT profile, NOT
  contacts, NOT Drive. Just the email + verified flag.
- On callback: verify `id_token`, extract `email` + `email_verified`,
  upsert into `users` table keyed by email.
- If a user previously signed up with magic link, signing in with
  Google later just links the existing account by email match. No
  duplicate users.
- Why Google: covers ~80% of US teens (school Gmail, personal Gmail);
  zero password friction; Google's account-takeover defenses are
  far stronger than anything we'd build.
- Why NOT Apple Sign-In in v1: smaller percentage of teen email
  identity lives there (most teens use Gmail school accounts); adds
  Apple Developer membership ($99/yr) and an extra signing key
  rotation surface; defer.
- Why NOT email+password in v1: storing passwords requires bcrypt +
  reset flow + breach-response infrastructure. Two paths above cover
  the same user without any of that.

**Robustness layers (all of these, not just magic link)**

1. **CAPTCHA on signup AND on vote write** — Cloudflare Turnstile.
   Invisible most of the time. **Browse/read stays open to bots**
   (good for SEO + AI agents indexing civic content); only the
   *write* paths are gated.

2. **Disposable email domain blocklist** — `10minutemail.com`,
   `mailinator.com`, etc. Maintained list in code, refreshable.
   Real teens have real emails (Gmail, school, iCloud).

3. **Per-IP and per-email signup throttling** — 3 magic-link
   requests per email per hour, 5 per IP per hour. Prevents
   email-bombing real users + spam-signup attacks.

4. **Session security**
   - HttpOnly + Secure + SameSite=Lax session cookies
   - 30-day rolling session, refreshed on use
   - Server-side session ID rotation on tier promotion + on
     suspicious activity (e.g. IP geo change)
   - Logout button = both cookie clear and server-side
     session invalidation (don't trust the cookie alone)

5. **Bot-resistant vote endpoint**
   - Authenticated session required (already)
   - Turnstile token verified per vote
   - Per-user rate limit: 30 votes/min, 200 votes/day
     (real users hit ~5; this catches scripted abuse)
   - Anomaly: if same account votes "yes" on >50 bills in 2 minutes,
     server-side soft-lock the account pending review

6. **Audit logging**
   - Every login attempt logged (email, IP, success/fail, timestamp)
   - Every vote logged with session ID
   - Failed Turnstile attempts logged separately
   - 90-day retention for forensic ability

7. **Account recovery / lockout**
   - 5 failed magic-link attempts in 1 hour = email cooldown 1 hour
   - Admin-side manual unlock procedure for legit users locked out

**What's NOT in v1 auth**
- Email + password (handled by magic-link path)
- Two-factor TOTP (not worth the friction for teen audience yet)
- SMS verification (paid, easy to spoof, privacy-hostile)
- Real-name verification (defeats the point — anonymous civic engagement is the brand)
- Behavioral biometrics (overkill for current scale)
- Apple Sign-In (defer to v2)
- Facebook / X / TikTok login (defer; brand alignment concerns)

### Daily earning cap
**5 votes per day count toward Votes currency.** Users can still
cast votes on more bills — they just don't earn additional Votes
that day. Cap visible in UI ("3/5 today") so users pace themselves.

**Research-informed refinement (per gamification research 2026-05-18):**
- Votes 1-3: full value (1 Vote each)
- Votes 4-5: half value (0.5 Votes each, surfaced as "bonus value")
- Vote 6+: zero currency value, but counted in lifetime aggregator
  (power users can keep going without grinding the economy)
- Same cap for all tiers (don't tier the cap — turns the app into
  a job for power users, punishes new users)

### Bot-resistance via dwell time (anti-spam, anti-bot, pro-quality)
**8-12 second minimum dwell on bill-summary before vote unlocks.**
Silent (no countdown UI). Real users naturally exceed it while
reading. Bots scripting through endpoints don't. Reddit and
Stack Overflow use similar implicit signals. Zero friction for
real users, hard wall for low-effort automation.

### Civi gate
**Civi unavailable until login.** Public nav shows "Civi" link;
clicking redirects to /login if not authenticated. Civi's
implementation is its own body of work — for the auth ship, just
the gate.

### Lifetime aggregator
**Side rail showing total bills voted on lifetime.** Separate from
Votes currency. Survives the daily cap (every vote counts here, not
just the first 5). Frames the user's overall impact.

Format TBD — candidates:
- Simple counter ("You've voted on 47 bills")
- Pokédex-style progress ("47 of 312 bills in this Congress")
- GitHub-style activity heatmap

### Bot policy

**Open**: bill detail pages, archive, about, contact, grants,
resources, sitemap, robots.txt, RSS feed (when shipped). Bots may
freely scrape for civic content indexing and AI training.

**Gated**: signup, login, vote write, account export, Civi chat.
Anything that mutates state or consumes per-user resources requires
authenticated session + Turnstile token.

Rationale: civic education content is a public good and we want it
discoverable. But fake votes destroy data quality (and the eventual
aggregated-data product), so writes are protected.

### What's NOT in scope for v1

- Trivia (deferred to v2 — see backlog)
- Civi conversation rewards (deferred — see backlog)
- Streak bonuses (research first; lean toward not shipping in v1)
- CAPTCHA (defer unless abuse appears on staging)
- Leaderboards (likely never, or opt-in only)
- Demographic onboarding (deferred to v2/data-product work)
- Pre-account vote retroactive Votes (no — clean cut at signup)

---

## Tier ladder

20-tier ladder using real Congressional roles with Junior/Senior
variants. Curve gentle at the bottom (frequent early dopamine hits),
steepens at the top (President is effectively unreachable — a
multi-year achievement).

| Tier | Title | Votes | Time at 5/day |
|---|---|---|---|
| 0 | Coffee Runner | 0 | signup |
| 1 | Mailroom Clerk | 5 | 1 day |
| 2 | Intern | 15 | 3 days |
| 3 | Senior Intern | 30 | 6 days |
| 4 | Legislative Correspondent | 50 | 10 days |
| 5 | Junior Staffer | 80 | 16 days |
| 6 | Staffer | 120 | ~3 weeks |
| 7 | Senior Staffer | 180 | ~5 weeks |
| 8 | Junior Aide | 250 | ~7 weeks |
| 9 | Aide | 350 | ~10 weeks |
| 10 | Senior Aide | 475 | ~3 months |
| 11 | Chief of Staff | 625 | ~4 months |
| 12 | Junior Representative | 800 | ~5 months |
| 13 | Representative | 1000 | ~7 months |
| 14 | Senior Representative | 1250 | ~8 months |
| 15 | Whip | 1550 | ~10 months |
| 16 | Junior Senator | 1900 | ~13 months |
| 17 | Senator | 2300 | ~15 months |
| 18 | Senior Senator | 2750 | ~18 months |
| 19 | Speaker of the House | 3300 | ~22 months |
| 20 | President | 4000 | ~27 months |

(Times scale with 5/day cap. With 2/day cap as original draft, multiply by 2.5x.)

### Tier titles open to redesign

If the user wants different vibes, swap candidates:
- Coffee Runner → Canvasser / Volunteer / Phone Banker / Door Knocker
- Add fun variants: "Bill Drafter," "Pundit," "Lobbyist," "Cabinet Member"
- Could insert a "Cabinet Member" tier between Senator and Speaker

### Same currency, evolving flavor text

NOT split currencies (UX trap — confuses users, complicates the
ledger). Same "Votes" mechanic, but the *language* of earning
evolves by tier:

- Tier 0-2 (Coffee Runner → Intern): "✓ Vote logged"
- Tier 3-6 (Senior Intern → Staffer): "📋 Filed under your name"
- Tier 7-10 (Senior Staffer → Senior Aide): "📬 Memo to the Senator's desk"
- Tier 11-14 (Chief of Staff → Senior Rep): "🏛️ Submitted to the record"
- Tier 15-18 (Whip → Senior Senator): "⚖️ Entered into Committee minutes"
- Tier 19-20 (Speaker → President): "🦅 Signed into law (well, a poll)"

Pure template-string change per tier — trivial implementation, big
flavor payoff.

### Tier-locked perks

Each promotion gives a real (small) feature unlock, not just a number:

- **Coffee Runner** (0): Vote on bills, see results
- **Mailroom Clerk** (1): Can vote (lifetime aggregator visible)
- **Intern** (2): Change display name from default "Intern #1234"
- **Senior Intern** (3): One-line profile bio
- **Legislative Correspondent** (4): Pick a state flag for profile
- **Junior Staffer** (5): Weekly digest email opt-in
- **Staffer** (6): Custom profile color accent
- **Senior Staffer** (7): Profile badge — "Senior Staffer since X"
- **Junior Aide** (8): Priority Civi chat (faster responses, if Civi shipped)
- **Aide** (9): TBD
- **Senior Aide** (10): Veto-this-bill button (cosmetic — shows on profile)
- **Chief of Staff** (11): Early access to new features
- **Junior Rep** (12): Profile tagline (longer bio)
- **Rep** (13): TBD
- **Senior Rep** (14): TBD
- **Whip** (15): TBD
- **Junior Senator** (16): TBD
- **Senator** (17): TBD
- **Senior Senator** (18): TBD
- **Speaker** (19): TBD — speaker-level visible distinction
- **President** (20): TBD — Presidential distinction, very rare

Many TBDs — fine; tiers far up the ladder don't need their perks
specified until users are close to reaching them. Reward design can
be iterative.

---

## Schema (v1)

```sql
-- New tables, applied via Alembic migration
users (
  id              UUID PRIMARY KEY,
  email           TEXT UNIQUE NOT NULL,
  email_verified  BOOLEAN DEFAULT FALSE,
  created_at      TIMESTAMPTZ DEFAULT NOW(),
  deleted_at      TIMESTAMPTZ,                    -- soft delete
  last_login_at   TIMESTAMPTZ,
  voter_id        UUID UNIQUE,                    -- link to anon votes
  display_name    TEXT,                           -- editable at tier 2+
  bio             TEXT,                           -- tier 3+
  state_flag      TEXT,                           -- tier 4+
  profile_color   TEXT,                           -- tier 6+
  total_votes_cast INTEGER DEFAULT 0,             -- lifetime aggregator
  -- Auth path tracking
  signup_method   TEXT NOT NULL,                  -- 'magic_link' | 'google'
  google_sub      TEXT UNIQUE                     -- Google's stable subject ID
                                                  -- (only present if signed in via Google)
)
-- An account created via magic_link can later attach a Google identity
-- by setting google_sub on the matching email row. Same user, two
-- ways to sign in.

magic_links (
  token_hash      TEXT PRIMARY KEY,               -- SHA-256 of token
  user_email      TEXT NOT NULL,
  created_at      TIMESTAMPTZ DEFAULT NOW(),
  expires_at      TIMESTAMPTZ NOT NULL,           -- created_at + 15m
  used_at         TIMESTAMPTZ                     -- null until consumed
)

civitas_ledger (
  id              BIGSERIAL PRIMARY KEY,
  user_id         UUID REFERENCES users(id),
  delta           INTEGER NOT NULL,               -- always positive for v1
  reason          TEXT NOT NULL,                  -- 'vote:hres933-119'
  source_bill_id  TEXT,
  awarded_at      TIMESTAMPTZ DEFAULT NOW()
)
-- Append-only. Never UPDATE / DELETE. Balance = SUM(delta) per user.
-- Daily cap = COUNT(reason LIKE 'vote:%') today ≤ 5
```

`total_votes_cast` on `users` is denormalized for the side-rail UI
(avoid joining `votes` table on every page load). Increment in the
same transaction as `votes` insert.

---

## v1 ship plan

### Session A — auth foundation (magic-link path)
- Alembic baseline (existing schema) + first migration (users, magic_links, civitas_ledger)
- `src/auth/magic_link.py` — token gen, hash, send via Resend
- `src/auth/session.py` — login/logout
- Routes: `/login`, `/login/verify/<token>`, `/logout`, `/profile` (skeleton)
- Templates: `login.html`, `login_check_email.html`, `profile.html`
- Top nav: shows email + tier badge if logged in, "Sign in" otherwise
- No earnings yet — just login works
- Cloudflare Turnstile token validated on `/login` form submit

### Session A.5 — Google OAuth path
- `src/auth/google_oauth.py` — Authlib client, callback handler
- New env vars: `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`
- Routes: `/login/google` (redirect), `/login/google/callback` (handler)
- "Sign in with Google" button on `/login` template
- Same session machinery as Session A — Google login just upserts
  a user row keyed by email, sets `google_sub`
- Email-conflict handling: if a magic-link user signs in with Google
  using the same email, link the existing account (set
  `google_sub`); do not create duplicate

### Session B — gamification layer
- Wire vote → ledger insert (with daily cap enforcement)
- Tier promotion logic (auto-promote on vote insertion if threshold crossed)
- Profile page: tier ladder visualization, current Votes balance, lifetime total
- Side rail: lifetime bills-voted-on counter
- "✓ Vote logged" flavor text by tier
- 8-12 second dwell-time check on bill summary before vote unlocks

### Session C — Civi gate
- Public "Civi" link in nav (currently doesn't exist)
- Click → redirect to /login if unauth
- Copy: "Civi's a friend who pays attention in AP Gov — sign in so she can remember you."

Pre-reqs from security/backup + python audits (must complete first):
- **All S1-S8 security fixes** from `SECURITY_BACKUP_AUDIT_2026-05-18.md`
- **Alembic adopted** (PR 3 in `PYTHON_CLEANUP_PLAN_2026-05-18.md`)
- **Encrypted backups landed** (backup audit B3)
- **Read-only prod role for sync** (backup audit B1)
- **Sync script DB-name guard** (B2 — DONE in current commit)
- **Staging environment confirmed deploying** (currently broken;
  requires Railway dashboard fix from olivia)
- **Privacy policy + ToS drafted**
- **Google Cloud project created**: OAuth consent screen configured,
  test users added, then submitted for verification before going
  public-facing (avoids the "this app isn't verified" warning)

---

## Backlog (v2 / v3 features)

Capture-everything list, not necessarily prioritized.

### Civi character
- Persona: "friend who pays attention in AP Gov, not a condescending teacher"
- Hedra Character-3 for video (per V2_RESEARCH.md)
- Nano Banana 2 for static image consistency
- Initial scope: text chat using Claude API
- Future: voice via ElevenLabs, video via Hedra

### Civi conversation rewards
- Award Votes for "quality conversations" with Civi
- Need anti-Goodhart design — can't just type "yes" 50 times
- Possible: LLM-judged conversation depth (Claude evaluates the
  conversation, awards 1-3 Votes based on engagement quality)
- Cap: maybe 5 Votes/day from Civi too? Or 10 across all sources?

### Trivia / quiz system
- 5-question civic-knowledge quiz
- Each correct answer = 1 Vote (capped daily — TBD)
- General government knowledge (constitution, three branches, etc.)
- Separate from weekly bill quizzes
- Triggered by Civi as a conversation flow

### **Live trivia contests** (added 2026-05-18)
- Users sign up for scheduled multi-player real-time quizzes
- Kahoot-like real-time leaderboard during the contest only
- Prizes: cosmetic profile badge, big Votes bonus (50-200 Votes),
  tier-skip token, merch
- Cadence: monthly to start, weekly if engagement is strong
- Tech: WebSocket-based, or pull every 1-2s for state
- Anti-cheat: same captcha + rate-limit story
- Format: Civi-themed — "Civi's Civic Trivia Hour"

### Lifetime aggregator UI variants
- Simple counter (v1 default)
- Pokédex-style: "X of Y bills this Congress"
- GitHub-style activity heatmap (research said this is a strong
  retention driver)
- Calendar grid by month
- Personal civic-attitude profile ("you've voted Yes 73% of the time
  on healthcare bills")

### Possible v2 mechanics from research
- 7-day streak bonus (research-backed but high churn risk)
- Streak freeze (one free skip per week)
- Backloaded streak rewards (bonuses at 7/30/100 days)
- "Quiet day" mechanic — bonus Votes for returning after a 7+ day gap

### Future earners (beyond votes + trivia)
- Reading time on bill detail page (must scroll, must hit min-time)
- Sharing a bill (hard to verify — needs share-event callback)
- Completing weekly digest read-receipt
- Inviting a friend (one-time, capped)
- Profile completion bonus (one-time)

### Cosmetic / progression
- Custom display name (tier 2+)
- Profile bio (tier 3+)
- State flag badge (tier 4+)
- Profile color accent (tier 6+)
- Animated profile frame (high tier)
- Civic flair (e.g. "I voted Yes on 100+ bills" badges)

### Anti-abuse hardening (when needed)
- Cloudflare Turnstile on signup
- Cloudflare Turnstile on vote actions (only if abuse detected)
- Disposable email domain blocklist
- IP-based signup rate limit
- Browser fingerprint check (avoid the same browser making N accounts)

### Data product / panel (long-term)
- Quarterly "State of Teen Civic Attitudes" report (free, media-friendly)
- Demographic onboarding step (opt-in, after tier 2)
- Sponsored research engagements ($5k-$25k per study)
- Aggregated API for academic / advocacy buyers
- Per V2_RESEARCH.md: stay on Option B (aggregated only),
  honor "no individual data sale" — the trust capital is worth more
  than the marginal revenue

### Account-related v2
- Right-to-export endpoint (`/account/export` returns JSON)
- Right-to-delete (soft-delete + cascade-anonymize)
- Account recovery (lost-email — manual support flow for v1)
- Account-linking — claim an existing voter_id history on signup
- Optional OAuth (Google, Apple) as second auth path
- Settings page: notification opt-in/out, email digest preferences

### Notification infrastructure
- Weekly digest email (opt-in, tier 5+)
- "You've reached [tier]!" promotion email
- Civi message — when Civi has something for the user
- DO NOT BUILD: aggressive push notifications. Research says
  Duolingo-style passive-aggressive notifications damage long-term
  brand even when they work short-term.

### Live community features (far future)
- Discussion threads on bills (high moderation cost — defer)
- User-curated "playlists" of bills
- "Civi clubs" — groups of users co-watching a bill's progression

---

## Anti-recommendations (things we deliberately won't do)

Based on gamification research + civic-product ethics:

1. **No loot boxes or random rewards** — illegal for minors in
   some jurisdictions, ethically gross
2. **No aggressive push notifications** — Duolingo's notorious
   passive-aggressive owl notifications damage long-term brand
3. **No pay-to-skip / pay-to-tier-up mechanics** — incompatible with
   "we don't sell premium features" stance
4. **No public real-name leaderboards** for under-18 users —
   doxxing risk + social toxicity
5. **No energy / hearts systems** that gate engagement (Candy Crush
   model) — proven to backfire for educational products
6. **No streak-loss-equals-zero punishment** — guaranteed churn on
   users who miss a single day
7. **No demographic data sales** — Option B in V2_RESEARCH.md.
   Aggregated reports yes, individual records never.

---

## Open questions

To revisit before implementation:

1. **Day reset timezone** — UTC midnight (simpler, fair) or
   user-local (friendlier)? Lean UTC midnight.
2. **Email service confirm** — Resend OK?
3. **Civi gate exact copy** — draft inline or ask user?
4. **Pre-account votes retroactive Votes** — confirmed: NO
5. **Coffee Runner vs Canvasser** — entry-level title naming
6. **Lifetime aggregator UI shape** — simple counter, Pokédex,
   or heatmap for v1?
7. **Streak shipping in v1** — research says it's the biggest
   retention mechanic but also biggest rage-quit cause. Probably
   defer to v2 with research-informed design (freeze, backloaded rewards)
8. **Civitas/Votes conversation rewards Goodhart** — how to evaluate
   "good conversations" without making the system gameable

---

## Implementation gates

Before any `users` row exists in production, ALL of the following
must be done. These are blockers, not nice-to-haves.

### Security gates (from `SECURITY_BACKUP_AUDIT_2026-05-18.md`)

- [x] **S1** `previous_vote` integrity — server reads truth from DB
- [ ] **S2** ProxyFix middleware so rate limits work per-user, not per-Railway-IP
- [ ] **S3** Either implement or delete `ADMIN_LOGIN_ATTEMPTS` dead code
- [ ] **S4** Cache-Control becomes `private; no-store` when authenticated
- [ ] **S5** Remove `@csrf.exempt` from public APIs; add CSRF tokens in JS
- [ ] **S6** Sign `voter_id` cookie via itsdangerous (or move to Flask session)
- [ ] **S7** Redis-backed rate limiter (shared state across workers)
- [ ] **S8** `SECRET_KEY` mandatory in prod (fatal on absence)
- [ ] **S11** Remove or admin-gate `/debug/env`
- [ ] **S14** Bump `requests` to 2.32.x, `gunicorn` to 23.x
- [ ] **S16** Generic error responses (no `str(e)` leak to JSON)

### Backup gates

- [ ] **B1** Read-only prod role for staging sync
- [x] **B2** Sync script DB-name guard + dry-run default (DONE)
- [ ] **B3** Encrypted backups via age + Cloudflare R2 secondary destination
- [ ] **B6** Healthchecks.io + UptimeRobot monitoring

### Python foundation gates (from `PYTHON_CLEANUP_PLAN_2026-05-18.md`)

- [ ] **PR 3 Alembic adopted** — first three migrations validated;
      baseline matches prod byte-for-byte

### Operational gates

- [ ] **Staging environment confirmed deploying** (currently broken —
      requires Railway dashboard fix from olivia)
- [ ] **Google Cloud project** created + OAuth consent screen verified
      for production use (avoids the "this app isn't verified" warning)
- [ ] **Resend account** activated, sender domain DNS validated
- [ ] **Privacy policy + ToS drafted**, linked from /login
- [ ] **Soft-delete + cascade-anonymize designed** into schema
- [ ] **`/account/export` endpoint scaffolded**
- [ ] **Breach notification template** at `plans/BREACH_NOTIFICATION_TEMPLATE.md`
- [ ] **Disaster recovery runbook** at `plans/DR_RUNBOOK.md`

---

## Open questions

To revisit before implementation:

1. ~~**Day reset timezone**~~ → **DECIDED: UTC midnight**
2. ~~**Email service**~~ → **DECIDED: Resend**
3. **Civi gate exact copy** — draft option included above; final wording TBD
4. ~~**Pre-account votes retroactive Votes**~~ → **DECIDED: no retroactive credit**
5. **Coffee Runner vs Canvasser** — entry-level title naming, open
6. **Lifetime aggregator UI shape** — simple counter, Pokédex, or
   heatmap for v1? Lean Pokédex-style for v1 ("X of Y bills this
   Congress") per research recommendation
7. ~~**Streak shipping in v1**~~ → **DECIDED: defer to v2** with research-informed
   design (free auto-freeze, backloaded rewards, user-initiated pause mode)
8. **Civi conversation rewards Goodhart** — reward quiz *outcomes*
   (correctness on bill the user just voted on) rather than conversation
   length — sidesteps gameability entirely. Defer full design to Civi work.
9. **OAuth-discovered email already has magic-link account** — confirm
   the "auto-link by email match" UX feels right vs. asking the user
   "an account with this email already exists, link them?"

---

## Document history

- 2026-05-18 (morning) — Initial doc. Auth + gamification + Civi v1
  plan drafted. Daily cap set to 5 votes. Live trivia contests added
  to v2/v3 backlog. Tier ladder finalized at 20 tiers.
- 2026-05-18 (afternoon) — Added defense-in-depth layer to auth model
  (Turnstile, dwell-time, anomaly detection). Bot policy clarified:
  open for reads, gated for writes.
- 2026-05-18 (evening, this revision) —
  - Promoted Google OAuth from "defer to v2" to v1 alternative path.
    Two auth paths now: magic-link OR Google. Same user, same tier.
  - `users` schema extended with `signup_method` + `google_sub`.
  - Implementation gates expanded to include all S1-S8 security
    fixes + Alembic adoption + staging deploy fix.
  - Several open questions resolved per gamification research findings.
  - Cross-referenced `PYTHON_CLEANUP_PLAN_2026-05-18.md` for the
    foundation work that must precede auth.

---

## Apple Sign-In — deferred plan (added 2026-05-22)

Skipped from the 2026-05-22 auth build because Apple's OAuth flow requires:
1. An HTTPS callback on a registered domain — `http://localhost` is rejected at the Service ID configuration step, so we cannot end-to-end test on a dev laptop.
2. Apple Developer Program membership ($99/yr).
3. A `.p8` private key, Team ID, Key ID, and a ES256-signed JWT minted as the OAuth `client_secret` (must be re-minted every ≤6 months).

### Implementation outline (when ready)
- Build on the same Authlib registry already wired in `src/auth/oauth.py`; Apple registers as a generic OIDC client with a custom `client_secret` callable.
- Mint the client-secret JWT lazily, caching for ~5 months. Algorithm = ES256, claims = `{iss: team_id, iat, exp, aud: "https://appleid.apple.com", sub: client_id}`. PyJWT can do this; the `.p8` file is loaded once at startup.
- Authorize URL: `https://appleid.apple.com/auth/authorize`. Token URL: `https://appleid.apple.com/auth/token`. JWKS: `https://appleid.apple.com/auth/keys`.
- Apple POSTs the callback (not GET) when `response_mode=form_post` is requested — Flask route must allow `methods=["GET", "POST"]` AND `@csrf.exempt` (the OAuth `state` param carries the CSRF guarantee, like the Google callback already does).
- Apple returns email + name **only on first consent** — persist both in `users` row on the callback's "new user" branch. Subsequent logins yield only `sub`.
- Reference: `rlid/flask-apple-signin` on GitHub shows the Authlib + client-secret-JWT pattern in <100 lines.

### Prereq checklist before coding
- [ ] Apple Developer Program enrollment confirmed.
- [ ] Service ID created with `https://teencivics.org/auth/apple/callback` as Return URL.
- [ ] `.p8` key downloaded, stored in Railway secrets as base64 (not committed).
- [ ] `APPLE_CLIENT_ID`, `APPLE_TEAM_ID`, `APPLE_KEY_ID`, `APPLE_PRIVATE_KEY_PEM` added to Railway environment.

DB columns already in place (`users.apple_sub`) per migration `f88fa0e69ea9`.
