# Privacy Policy — DRAFT (NOT LEGAL ADVICE)

> **Status: pre-launch draft.** olivia must have this reviewed by a lawyer
> before going live to users. The text below is a starting point pulled
> from common patterns for civics-education products targeting US teen
> audiences. State-specific addenda (California CCPA, Connecticut CTDPA,
> Colorado CPA, Texas TDPSA) and federal COPPA compliance language are
> NOT exhaustively covered here.

**Effective date**: TBD on launch

## Plain-language summary

TeenCivics helps teenagers in the United States read about
Congressional bills and vote in non-binding community polls. We collect
the minimum information needed to make the site work. **We don't sell
your data**, we don't show ads, and we don't share your identity with
political organizations or advertisers.

If you sign up for an account, we keep your email and a record of which
bills you voted on. You can delete that whenever you want.

## What we collect

### Anonymous visitors (no account)
- **A random voter ID cookie** so we can show you the bills you've
  already voted on, without knowing who you are. The cookie is
  cryptographically signed. We can't link it to your real identity.
- **Your IP address** (transient) for security: rate-limiting,
  abuse prevention, and basic site analytics. We don't store IP
  addresses in our database long-term.
- **Browser cookies** for site functionality (theme preference,
  session state). No third-party advertising cookies.

### Account holders (signed up via email or Google)
Everything above, plus:
- **Your email address** (used to log you in)
- **Your bill votes** linked to your account
- **Your tier progress** (currency balance, achievements)
- **Login records** (timestamps, success/failure — for security audit
  trail; auto-deleted after 90 days)

### What we DO NOT collect
- Real name (unless you put it in your optional display name)
- Phone number
- Physical address
- Date of birth (except confirming you're 13+; see COPPA section)
- Browsing history outside teencivics.org
- Location beyond IP-derived country/region
- Anything from your Google account beyond your email address (we
  request only the `openid email` scope)

## How we use your information

- **To make the site work**: show you bills, record your votes,
  remember your preferences
- **To award gamification points**: count votes toward your tier
- **For security**: detect abuse, prevent vote stuffing,
  investigate compromised accounts
- **For analytics**: understand what bills get the most engagement
  (aggregated, never per-user)
- **To send you the weekly digest** (if you've opted in)

We DO NOT use your information for:
- Targeted advertising (we don't run ads)
- Selling to data brokers
- Sharing with political campaigns or PACs
- Building a profile of your political beliefs for any purpose other
  than the on-site features you opted into

## Who we share data with

- **Our hosting providers**: Railway (web app), the Postgres database
  hosted on Railway, Resend (email delivery), Cloudflare (CDN + DDoS
  protection)
- **Service providers we need to make features work**: Anthropic /
  Venice (to generate bill summaries — they see bill text, not your
  identity), Congress.gov (we read public bill data from them)
- **Law enforcement**: only if compelled by subpoena or court order.
  We commit to publishing a transparency report if/when this happens.

## Aggregated, anonymized publishing

We may publish aggregated, anonymized statistics about how the
TeenCivics community has voted on bills — for example,
"73% of TeenCivics teens supported HR-1234." This data is never
linked to any individual account. We may also share aggregated
breakdowns with academic researchers or media in the format of a
quarterly "State of Teen Civic Attitudes" report.

We do NOT and will not sell individual records or row-level data.

## Your rights

If you have an account, you can:
- **Export your data**: visit `/account/export` to download your
  votes, tier, and account info as JSON
- **Delete your account**: visit `/account/delete`. We soft-delete
  immediately (your data stops being readable). Anonymization in
  backups completes within 30 days as backups age out.
- **Edit your profile**: display name, bio, preferences
- **Opt out of emails**: every email we send has an unsubscribe link

Even without an account, you can:
- **Clear your voter ID cookie**: delete the `voter_id` cookie in
  your browser. Your vote history attached to that ID stays in our
  DB but is no longer linked to you.

To exercise any right, email **contact@teencivics.org**.

## Cookies

We use:
- `voter_id` (signed cookie, 2 years): tracks anonymous votes
- Session cookie (HttpOnly, expires on browser close): logged-in
  state if you signed up
- `theme` (1 year): light/dark mode preference

We do NOT use:
- Advertising cookies
- Third-party analytics that follow you off-site (we use a privacy-
  respecting first-party analytics setup if any)

## Children's privacy (COPPA)

TeenCivics is targeted at users **13 and older**. We do not knowingly
collect personal information from children under 13. If we learn that
we have collected information from a child under 13 without verified
parental consent, we will delete it as soon as we are made aware.

If you are a parent and believe your under-13 child has signed up,
email contact@teencivics.org.

If you are between 13 and 17, in some states (California, Colorado,
Connecticut, Texas, others) you have additional rights — we honor
those across the board, regardless of which state you live in.

## Data security

- All connections are HTTPS-only
- Passwords are not used (magic-link or Google sign-in instead)
- Cookies are signed cryptographically (`itsdangerous` over SECRET_KEY)
- Backups are encrypted at rest
- We follow the security commitments in our SECURITY.md

If we ever experience a data breach, we will notify affected users via
email within 30 days, and within shorter timeframes where state law
requires (California: 45 days max). See `plans/BREACH_NOTIFICATION_TEMPLATE.md`
for the format.

## Changes to this policy

We will email registered users 30 days before any material change to
this policy. Non-material updates (clarifying language, fixing typos)
take effect immediately and are noted at the bottom of this page.

## Contact

Questions, requests, or concerns: **contact@teencivics.org**

---

**For olivia (internal): Items the lawyer must rule on before launch:**

1. Whether the COPPA section is sufficient given we don't verify age
   beyond a self-attestation checkbox. Some advisors recommend an
   age gate with verified parental consent for under-13. Others
   accept the "we don't knowingly serve under 13" + delete-on-notice
   pattern.
2. Whether "aggregated, anonymized" data publishing requires any
   additional opt-in language under state laws (Colorado opt-out is
   the strictest, Maryland 2025 is also tight on this).
3. Whether sharing email with Resend triggers a "service provider"
   vs "third party" classification under CCPA — affects how we
   word the data-sharing section.
4. Whether our retention period (90 days for login logs, indefinite
   for votes pending account deletion, 30-day backup expiry) is
   defensible. Some recommend tighter caps on logs.
5. Whether we need an explicit "Do Not Sell My Personal Information"
   link on every page (California requirement; arguable since we
   don't sell, but some lawyers say put it anyway).
6. Whether the transparency-report commitment is wise (locks us into
   ongoing work).
