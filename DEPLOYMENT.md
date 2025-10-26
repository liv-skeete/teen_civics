# AWS Lightsail Deployment Guide (Legacy)

> **NOTE**: This guide covers the legacy deployment method to AWS Lightsail. The project is now deployed to Railway.app. For current deployment instructions, see [DEPLOYMENT_RAILWAY.md](DEPLOYMENT_RAILWAY.md).

This guide covers deploying TeenCivics to AWS Lightsail with Gunicorn and Nginx.

## Prerequisites

- AWS account with Lightsail access
- Domain name (optional, but recommended)
- SSH key pair for server access

## AWS Lightsail Setup

### 1. Create Lightsail Instance

1. Log into AWS Lightsail console
2. Click "Create instance"
3. Select:
   - Platform: Linux/Unix
   - Blueprint: OS Only → Ubuntu 22.04 LTS
   - Instance plan: At least $5/month (1 GB RAM, 1 vCPU)
4. Name your instance (e.g., `teencivics-prod`)
5. Click "Create instance"

### 2. Configure Networking

1. In the Lightsail console, go to your instance's "Networking" tab
2. Add firewall rules:
   - SSH (port 22) - Already configured
   - HTTP (port 80) - Click "Add rule"
   - HTTPS (port 443) - Click "Add rule"

### 3. Assign Static IP (Recommended)

1. Go to "Networking" tab
2. Click "Create static IP"
3. Attach it to your instance
4. Note the IP address for DNS configuration

## Server Configuration

### 1. Connect to Server

```bash
ssh ubuntu@YOUR_STATIC_IP
```

### 2. Update System

```bash
sudo apt update
sudo apt upgrade -y
```

### 3. Install Dependencies

```bash
# Install Python and pip
sudo apt install python3 python3-pip python3-venv -y

# Install PostgreSQL
sudo apt install postgresql postgresql-contrib -y

# Install Nginx
sudo apt install nginx -y

# Install Git
sudo apt install git -y
```

### 4. Configure PostgreSQL

```bash
# Switch to postgres user
sudo -u postgres psql

# In PostgreSQL prompt:
CREATE DATABASE teencivics;
CREATE USER teencivics_user WITH PASSWORD 'your_secure_password';
GRANT ALL PRIVILEGES ON DATABASE teencivics TO teencivics_user;
\q
```

### 5. Clone Repository

```bash
cd /var/www
sudo mkdir teencivics
sudo chown ubuntu:ubuntu teencivics
cd teencivics
git clone https://github.com/liv-skeete/teen_civics.git .
```

### 6. Set Up Python Environment

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
pip install gunicorn
```

### 7. Configure Environment Variables

```bash
# Create .env file
nano .env
```

Add your configuration:

```env
# Database
DATABASE_URL=postgresql://teencivics_user:your_secure_password@localhost/teencivics

# API Keys
CONGRESS_API_KEY=your_congress_api_key
ANTHROPIC_API_KEY=your_anthropic_api_key

# Twitter/X API
TWITTER_CONSUMER_KEY=your_consumer_key
TWITTER_CONSUMER_SECRET=your_consumer_secret
TWITTER_ACCESS_TOKEN=your_access_token
TWITTER_ACCESS_TOKEN_SECRET=your_access_token_secret

# Flask
FLASK_ENV=production
SECRET_KEY=your_random_secret_key_here
```

Save and exit (Ctrl+X, Y, Enter).

### 8. Initialize Database

```bash
# Activate virtual environment if not already active
source venv/bin/activate

# Run the app once to initialize database
python app.py
# Press Ctrl+C after it starts
```

## Gunicorn Configuration

### 1. Test Gunicorn

```bash
gunicorn --bind 0.0.0.0:8000 wsgi:app
```

Visit `http://YOUR_IP:8000` to verify it works. Press Ctrl+C to stop.

### 2. Create Systemd Service

```bash
sudo nano /etc/systemd/system/teencivics.service
```

Add the following:

```ini
[Unit]
Description=TeenCivics Gunicorn Application
After=network.target

[Service]
User=ubuntu
Group=www-data
WorkingDirectory=/var/www/teencivics
Environment="PATH=/var/www/teencivics/venv/bin"
ExecStart=/var/www/teencivics/venv/bin/gunicorn --config gunicorn_config.py wsgi:app

[Install]
WantedBy=multi-user.target
```

### 3. Enable and Start Service

```bash
sudo systemctl daemon-reload
sudo systemctl start teencivics
sudo systemctl enable teencivics
sudo systemctl status teencivics
```

## Nginx Configuration

### 1. Create Nginx Configuration

```bash
sudo nano /etc/nginx/sites-available/teencivics
```

Add the following:

```nginx
server {
    listen 80;
    server_name your_domain.com www.your_domain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /static {
        alias /var/www/teencivics/static;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }
}
```

### 2. Enable Site

```bash
sudo ln -s /etc/nginx/sites-available/teencivics /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

## SSL/HTTPS Setup (Recommended)

### 1. Install Certbot

```bash
sudo apt install certbot python3-certbot-nginx -y
```

### 2. Obtain SSL Certificate

```bash
sudo certbot --nginx -d your_domain.com -d www.your_domain.com
```

Follow the prompts. Certbot will automatically configure Nginx for HTTPS.

### 3. Test Auto-Renewal

```bash
sudo certbot renew --dry-run
```

## GitHub Actions Automation

### 1. Configure GitHub Secrets

In your GitHub repository, go to Settings → Secrets and variables → Actions, and add:

- `CONGRESS_API_KEY`
- `ANTHROPIC_API_KEY`
- `TWITTER_CONSUMER_KEY`
- `TWITTER_CONSUMER_SECRET`
- `TWITTER_ACCESS_TOKEN`
- `TWITTER_ACCESS_TOKEN_SECRET`
- `DATABASE_URL`

### 2. Workflows

The repository includes two workflows:

- **Daily workflow** (`.github/workflows/daily.yml`): Runs orchestrator daily to fetch and post bills
- **Weekly workflow** (`.github/workflows/weekly.yml`): Sends weekly digest (planned feature)

These run automatically via GitHub Actions and don't require server cron jobs.

## Monitoring and Maintenance

### View Application Logs

```bash
# Gunicorn logs
sudo journalctl -u teencivics -f

# Nginx access logs
sudo tail -f /var/log/nginx/access.log

# Nginx error logs
sudo tail -f /var/log/nginx/error.log
```

### Restart Services

```bash
# Restart Gunicorn
sudo systemctl restart teencivics

# Restart Nginx
sudo systemctl restart nginx
```

### Update Application

```bash
cd /var/www/teencivics
git pull origin main
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart teencivics
```

### Database Backup

```bash
# Create backup
sudo -u postgres pg_dump teencivics > backup_$(date +%Y%m%d).sql

# Restore from backup
sudo -u postgres psql teencivics < backup_20240101.sql
```

## Troubleshooting

### Application Won't Start

1. Check logs: `sudo journalctl -u teencivics -n 50`
2. Verify environment variables in `.env`
3. Ensure database is running: `sudo systemctl status postgresql`
4. Check file permissions: `ls -la /var/www/teencivics`

### 502 Bad Gateway

1. Verify Gunicorn is running: `sudo systemctl status teencivics`
2. Check Gunicorn is listening: `sudo netstat -tlnp | grep 8000`
3. Review Nginx config: `sudo nginx -t`

### Database Connection Issues

1. Verify PostgreSQL is running: `sudo systemctl status postgresql`
2. Test connection: `psql -U teencivics_user -d teencivics -h localhost`
3. Check `DATABASE_URL` in `.env`

### High Memory Usage

1. Adjust Gunicorn workers in `gunicorn_config.py`
2. Consider upgrading Lightsail instance
3. Monitor with: `htop` or `free -h`

## Security Best Practices

1. **Keep system updated**: `sudo apt update && sudo apt upgrade`
2. **Use strong passwords** for database and SSH
3. **Enable firewall**: Only allow necessary ports
4. **Regular backups**: Automate database backups
5. **Monitor logs**: Check for suspicious activity
6. **Keep secrets secure**: Never commit `.env` to git
7. **Use HTTPS**: Always use SSL certificates in production

## Performance Optimization

1. **Enable Nginx caching** for static files
2. **Use CDN** for static assets (optional)
3. **Database indexing**: Ensure proper indexes on frequently queried columns
4. **Gunicorn workers**: Adjust based on CPU cores (2-4 × CPU cores + 1)
5. **Connection pooling**: Already configured in `src/database/connection.py`

## Cost Estimation

- **Lightsail instance**: $5-10/month (depending on size)
- **Domain name**: $10-15/year
- **API costs**: Variable (Congress.gov is free, Anthropic has usage-based pricing)

Total estimated cost: ~$10-20/month plus API usage.

## Support

For issues or questions:
- GitHub Issues: https://github.com/liv-skeete/teen_civics/issues
- Email: liv@di.st
- Twitter: @TeenCivics