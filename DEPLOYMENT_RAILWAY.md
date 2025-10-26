# Railway.app Deployment Guide

This guide covers deploying TeenCivics to Railway.app, the current production environment.

## Prerequisites

- Railway.app account
- GitHub account with repository access
- Domain name (optional, but recommended for custom domain)
- API keys for Congress.gov, Anthropic, and Twitter/X

## Railway Setup

### 1. Connect GitHub Repository

1. Log into Railway.app
2. Click "New Project"
3. Select "Deploy from GitHub repo"
4. Choose your TeenCivics repository
5. Select the branch (typically `main`)

### 2. Configure Environment Variables

Railway will automatically detect the `Procfile` and `requirements.txt`. You need to add environment variables:

In Railway → Project → Settings → Variables, add:

```env
# Database
DATABASE_URL=your_postgresql_connection_string

# API Keys
CONGRESS_API_KEY=your_congress_api_key
ANTHROPIC_API_KEY=your_anthropic_api_key

# Twitter/X API
TWITTER_API_KEY=your_twitter_api_key
TWITTER_API_SECRET=your_twitter_api_secret
TWITTER_ACCESS_TOKEN=your_twitter_access_token
TWITTER_ACCESS_SECRET=your_twitter_access_token_secret
TWITTER_BEARER_TOKEN=your_twitter_bearer_token

# Flask Security
SECRET_KEY=your_random_secret_key_here

# Optional: Analytics
GA_MEASUREMENT_ID=your_google_analytics_id
```

### 3. Configure Railway.json

The repository includes a `railway.json` configuration file that optimizes deployment:

```json
{
  "$schema": "https://railway.com/railway.schema.json",
  "build": {
    "builder": "RAILPACK"
  },
  "deploy": {
    "runtime": "V2",
    "numReplicas": 1,
    "sleepApplication": false,
    "useLegacyStacker": false,
    "multiRegionConfig": {
      "us-west2": {
        "numReplicas": 1
      }
    },
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 10
  }
}
```

## Gunicorn Configuration

The application uses a production-optimized Gunicorn configuration (`gunicorn_config.py`):

- **Workers**: 2 (optimized for Railway's 512MB RAM limit)
- **Timeout**: 120 seconds (accommodates Anthropic API calls)
- **Max Requests**: 1000 with jitter (prevents memory leaks)
- **Preloading**: Enabled for faster startup

## Custom Domain with Cloudflare

### 1. Configure Domain in Railway

1. Go to Railway → Project → Settings → Domains
2. Add your custom domain (e.g., `teencivics.org`)
3. Railway will provide DNS records to add

### 2. Configure Cloudflare

1. Add the domain to Cloudflare
2. Point Cloudflare's nameservers to your domain registrar
3. Configure SSL/TLS encryption mode to "Full" (not Full (Strict))

## GitHub Actions Integration

The repository includes automated workflows:

- **Daily workflow** (`.github/workflows/daily.yml`): Runs orchestrator twice daily
- **Database connectivity check**: Validates database before processing
- **Secret scanning**: Prevents credential leaks
- **Retry logic**: Automatic retries on transient failures

## Monitoring and Logging

### Railway Built-in Features

- **Live logs**: View real-time application logs in Railway dashboard
- **Metrics**: CPU, memory, and request metrics
- **Alerts**: Configure notification rules for downtime or performance issues

### Custom Logging

The application uses structured logging with:

```python
import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
```

View logs in Railway dashboard or via CLI:

```bash
railway logs
```

## Database Management

### PostgreSQL on Railway

Railway provides managed PostgreSQL databases with:

- Automatic backups
- SSL connections (configured in `src/database/connection.py`)
- Connection pooling (built-in with `psycopg2`)

### Schema Migrations

Database schema is automatically initialized by `src/database/connection.py`. For schema updates:

1. Modify `init_db_tables()` function
2. Deploy to Railway
3. Run migration script if needed

## Scaling and Performance

### Current Configuration

- **Instance**: 512MB RAM, 1 vCPU (Railway free tier)
- **Workers**: 2 Gunicorn workers
- **Memory**: Optimized with request recycling

### Performance Optimizations

1. **Database Connection Pooling**: Reuses connections efficiently
2. **HTTP Caching**: Configured in Flask security headers
3. **Gunicorn Preloading**: Reduces memory footprint
4. **Request Recycling**: Workers restart after 1000 requests

### Scaling Options

To scale beyond free tier limits:

1. Upgrade Railway plan for more resources
2. Increase Gunicorn workers in `gunicorn_config.py`
3. Add Redis for session caching (optional)
4. Configure CDN for static assets

## Security Best Practices

### Railway Security Features

- **Environment Variables**: Automatically masked in logs
- **Private Networking**: Database connections over private network
- **Automatic HTTPS**: SSL termination at Railway edge

### Application Security

1. **Secrets Management**: Never commit `.env` files
2. **CSRF Protection**: Enabled for all forms
3. **Rate Limiting**: 200 requests/day, 50/hour per IP
4. **Security Headers**: X-Frame-Options, CSP, etc.
5. **Input Sanitization**: All user inputs escaped in templates

## Maintenance and Updates

### Automatic Updates

Railway automatically builds and deploys on GitHub push to main branch.

### Manual Deployment

```bash
# Install Railway CLI
npm install -g @railway/cli

# Login
railway login

# Deploy from local changes
railway up
```

### Database Backups

Railway automatically backs up PostgreSQL databases. For manual backups:

```bash
railway shell
# In container:
pg_dump $DATABASE_URL > backup_$(date +%Y%m%d).sql
```

## Troubleshooting

### Common Issues

1. **Deployment Failures**
   - Check build logs in Railway dashboard
   - Verify all required environment variables are set
   - Ensure `requirements.txt` is up to date

2. **Database Connection Errors**
   - Verify `DATABASE_URL` is correctly configured
   - Check Railway PostgreSQL instance status
   - Ensure SSL is enabled in connection string

3. **Memory Issues**
   - Reduce Gunicorn workers
   - Optimize database queries
   - Consider upgrading Railway plan

4. **API Rate Limiting**
   - Implement exponential backoff
   - Cache API responses where appropriate
   - Monitor API usage in vendor dashboards

### Debugging Steps

1. **Check Railway Logs**
   ```bash
   railway logs
   ```

2. **Verify Environment**
   ```bash
   railway shell
   env | grep -E "(DATABASE|API)"
   ```

3. **Test Database Connection**
   ```bash
   railway shell
   python -c "from src.database.connection import postgres_connect; print('Database connected successfully')"
   ```

## Cost Management

### Railway Pricing

- **Free Tier**: 512MB RAM, 1 vCPU, 1GB disk
- **Usage-Based**: Pay for additional resources

### API Costs

- **Congress.gov API**: Free (no rate limits)
- **Anthropic API**: Usage-based pricing for Claude
- **Twitter API**: Free for posting (rate limits apply)

### Cost Optimization

1. **Database**: Use Railway managed PostgreSQL (included in free tier)
2. **Compute**: Optimize Gunicorn workers for memory usage
3. **Caching**: Implement Redis for session caching (optional)
4. **Monitoring**: Use Railway's built-in metrics

## Support Resources

- **Railway Documentation**: https://docs.railway.com
- **GitHub Repository**: https://github.com/liv-skeete/teen_civics
- **Email Support**: liv@di.st
- **Twitter**: @TeenCivics