# Backup and Disaster Recovery Plan for TeenCivics

**Last Updated:** 2026-01-21  
**Status:** Active Implementation

---

## Quick Reference

### Weekend Setup Checklist

Complete these items this weekend to have a solid backup and monitoring setup:

- [ ] **Enable Railway Backups** - Go to Railway Dashboard → Database → Backups tab → Enable Daily + Monthly
- [ ] **Set up Railway Monitors** - Dashboard → Observability → Add monitors for CPU >80%, Disk >80%, 5xx errors
- [ ] **Sign up for UptimeRobot** - Free tier at uptimerobot.com, add `https://teencivics.org`
- [ ] **Test db-backup workflow** - Go to GitHub Actions → Daily Database Backup → Run workflow manually
- [ ] **Verify backup artifact** - After workflow runs, download the artifact and check file size is reasonable
- [ ] **Test local restore** (optional) - Download backup, try `pg_restore` locally to verify integrity

---

## Table of Contents

1. [Current Infrastructure](#current-infrastructure)
2. [Railway Backup Configuration](#railway-backup-configuration)
3. [Offsite Backup Strategy](#offsite-backup-strategy)
4. [Disaster Recovery Procedures](#disaster-recovery-procedures)
5. [Monitoring Setup](#monitoring-setup)
6. [Security Hardening](#security-hardening)
7. [Runbooks](#runbooks)

---

## Current Infrastructure

| Component | Provider | Details |
|-----------|----------|---------|
| Web Hosting | Railway (Hobbyist Plan) | Flask + Gunicorn |
| Database | Railway PostgreSQL | Managed PostgreSQL instance |
| Source Control | GitHub | Private repository |
| CI/CD | GitHub Actions | Daily bill fetching + backups |
| Domain/CDN | Cloudflare | DNS, SSL, edge caching |
| AI Processing | Venice AI | Bill summarization |

---

## Railway Backup Configuration

### Railway Hobbyist Plan Backup Schedule

Railway's Hobbyist paid plan includes automatic database backups with the following retention:

| Backup Type | Frequency | Retention Period |
|-------------|-----------|------------------|
| Daily Backups | Every 24 hours | 6 days |
| Weekly Backups | Every 7 days | 1 month |
| Monthly Backups | Every 30 days | 3 months |

### Enabling Railway Backups

**Important:** Backups must be enabled manually in the Railway dashboard.

1. Log in to Railway Dashboard
2. Select your project → Select PostgreSQL database
3. Click the **Backups** tab
4. Enable desired backup types (recommend: Daily + Monthly)
5. Backups will begin on the next scheduled interval

### Restoring from Railway Backup

1. Go to Railway Dashboard → Database → Backups tab
2. Find the backup you want to restore
3. Click the three-dot menu → Select "Restore"
4. Confirm the restore operation
5. Railway will restore the database to that point in time

**Note:** Restoration overwrites the current database. Consider creating a manual backup first if you have recent data you want to preserve.

---

## Offsite Backup Strategy

### GitHub Actions Daily Backup

We use a GitHub Actions workflow that runs `pg_dump` daily and stores backups as GitHub Artifacts. This provides an offsite backup independent of Railway.

**Workflow:** [`.github/workflows/db-backup.yml`](.github/workflows/db-backup.yml)

**Features:**
- Runs daily at 2 AM UTC
- Manual trigger available via `workflow_dispatch`
- Backups stored as GitHub Artifacts (30-day retention)
- Uses existing `DATABASE_URL` secret from Railway

### Backup Retention Summary

| Tier | Location | Retention | Frequency |
|------|----------|-----------|-----------|
| Railway Daily | Railway | 6 days | Daily |
| Railway Weekly | Railway | 1 month | Weekly |
| Railway Monthly | Railway | 3 months | Monthly |
| GitHub Artifact | GitHub | 30 days | Daily |

### Manual Backup Procedure

For ad-hoc backups (before major changes or migrations):

```bash
# Option 1: Using DATABASE_URL directly
pg_dump "$DATABASE_URL" -F c -f backup-$(date +%Y-%m-%d).dump

# Option 2: Using Railway CLI
railway link
railway run pg_dump -F c -f backup-$(date +%Y-%m-%d).dump
```

### Restoring from GitHub Artifact Backup

1. Go to GitHub → Actions → Daily Database Backup
2. Click on the workflow run containing your desired backup
3. Download the artifact (backup-*.dump file)
4. Restore locally or to a new database:

```bash
# To restore to a local database for testing
createdb teencivics_restored
pg_restore -d teencivics_restored backup-2026-01-21.dump

# To restore to Railway (replace existing data)
pg_restore -d "$DATABASE_URL" --clean --if-exists backup-2026-01-21.dump
```

---

## Disaster Recovery Procedures

### Recovery Time Objectives (RTO)

| Scenario | Target RTO | Notes |
|----------|------------|-------|
| Application crash | 5 minutes | Railway auto-restarts |
| Database corruption | 30 minutes | Restore from backup |
| Railway temporary outage | 1-2 hours | Wait for Railway recovery |
| Need to migrate platforms | 2-4 hours | Deploy to Fly.io/Render |

### Recovery Point Objectives (RPO)

| Data Type | RPO | Notes |
|-----------|-----|-------|
| Database content | 24 hours | Daily backup frequency |
| Source code | Near-zero | Every git push |
| Configuration | Near-zero | Version controlled |

### Scenario 1: Database Corruption

1. **Assess the damage** - Check what data is affected
2. **Choose restore point:**
   - Railway backup (fastest, if recent enough)
   - GitHub Artifact backup (if Railway backup too old)
3. **Restore:**
   - Railway: Dashboard → Backups → Restore
   - GitHub: Download artifact → `pg_restore` command

### Scenario 2: Railway Extended Outage

If Railway is down for more than 4 hours:

1. **Prepare alternate deployment** to Fly.io:
   ```bash
   # Install Fly CLI
   curl -L https://fly.io/install.sh | sh
   flyctl auth login
   
   # Launch app
   flyctl launch --name teencivics
   flyctl postgres create --name teencivics-db
   flyctl postgres attach teencivics-db
   
   # Restore database from GitHub artifact backup
   flyctl proxy 5432 -a teencivics-db &
   pg_restore -h localhost -p 5432 -U postgres -d teencivics backup.dump
   
   # Deploy
   flyctl deploy
   ```

2. **Update Cloudflare DNS** to point to Fly.io

### Scenario 3: GitHub Repository Compromised

1. Clone from your local machine (you have a copy)
2. Or restore from any local developer's machine
3. Create new GitHub repository
4. Push code and reconfigure secrets

---

## Monitoring Setup

### Railway Built-in Monitoring

Railway provides metrics for your deployment. Set up monitors in:
**Dashboard → Observability → Monitors**

Recommended monitors:
- CPU usage > 80% → Alert
- Disk usage > 80% → Alert
- 5xx error rate > 5% → Alert

### UptimeRobot (Free Tier)

1. Sign up at [uptimerobot.com](https://uptimerobot.com)
2. Create new HTTP(s) monitor
3. URL: `https://teencivics.org`
4. Monitoring interval: 5 minutes (free tier)
5. Configure email alerts

### GitHub Actions Notifications

The workflows already have failure detection. GitHub sends email notifications on workflow failures by default.

---

## Security Hardening

### Current Security Implementation

The application already implements these security measures in [`app.py`](app.py:102):

✅ **Security Headers:**
- `Content-Security-Policy` - Controls resource loading
- `X-Content-Type-Options: nosniff` - Prevents MIME sniffing
- `X-Frame-Options: SAMEORIGIN` - Clickjacking protection
- `X-XSS-Protection: 1; mode=block` - XSS filter
- `Strict-Transport-Security` - Forces HTTPS (production only)

✅ **Application Security:**
- CSRF protection via Flask-WTF
- Rate limiting (200/day, 50/hour per IP)
- Secure session cookies (HttpOnly, Secure, SameSite)
- Input escaping via Jinja2 autoescape

### Security Scanning

We use GitHub Actions for automated security scanning:

**Workflow:** [`.github/workflows/security-scan.yml`](.github/workflows/security-scan.yml)

- **Bandit** - Python code security analysis
- **pip-audit** - Dependency vulnerability scanning
- Runs on every push/PR and weekly

### Cloudflare Protection

Enable in Cloudflare dashboard:
- ✅ DDoS Protection (enabled by default)
- Bot Fight Mode (Settings → Security → Bots)
- Security Level: Medium or High
- Browser Integrity Check: Enable

---

## Runbooks

### Runbook: Site Not Loading

```
1. CHECK: Is it really down?
   → Test from mobile data or different network
   → Check https://downforeveryoneorjustme.com/teencivics.org

2. CHECK: Railway status
   → Log in to Railway dashboard
   → Check deployment status (green = healthy)
   → Check logs for errors

3. ACTION: If deployment failed
   → Check recent commits for issues
   → Revert if needed: git revert HEAD && git push

4. CHECK: Database status
   → Railway Dashboard → Database → Check connection status
   → If database issues, consider restore from backup
```

### Runbook: Database Issues

```
1. CHECK: Can app connect to database?
   → Railway logs: Look for "connection refused" errors

2. ACTION: If connection issues
   → Verify DATABASE_URL is correct in Railway variables
   → Restart deployment in Railway dashboard

3. ACTION: If data corruption suspected
   → Document what data appears corrupt
   → DO NOT perform writes
   → Restore from backup (Railway or GitHub artifact)
```

### Runbook: Daily Workflow Failing

```
1. CHECK: GitHub Actions → See which step failed

2. COMMON ISSUES:
   a) "pg_dump failed"
      → Check DATABASE_URL secret is valid
      → Verify Railway database is running

   b) "Rate limit exceeded" (Venice/Congress API)
      → Wait for rate limit reset
      → Check API quota in respective dashboards

   c) "Twitter posting failed"
      → Verify Twitter API tokens are valid
      → Check Twitter Developer Portal

3. ACTION: Re-run workflow manually
   → GitHub Actions → Select workflow → Run workflow
```

---

## Secrets Reference

All secrets are stored in GitHub Secrets and Railway Variables. Document names only in [`.env.example`](.env.example).

| Secret | Purpose |
|--------|---------|
| DATABASE_URL | PostgreSQL connection string |
| VENICE_API_KEY | AI summarization |
| CONGRESS_API_KEY | Congress.gov API access |
| TWITTER_* (5 keys) | Twitter/X posting |
| SECRET_KEY | Flask session signing |

---

## Document History

| Version | Date | Changes |
|---------|------|---------|
| 2.0 | 2026-01-21 | Updated with accurate Railway backup info, simplified workflows |
| 1.0 | 2026-01-21 | Initial draft |
