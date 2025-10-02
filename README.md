# TeenCivics

TeenCivics makes government accessible for young people by posting daily plain‑English summaries of congressional bills from Congress.gov.

## Features

- Fetch data from Congress.gov API for the most recent bills
- Summarize content using Claude AI for easy understanding  
- Post updates to X/Twitter using Tweepy
- Store processed data in PostgreSQL database for tracking and deduplication
- Automate daily and weekly posting with GitHub Actions
- Website showing only tweeted bills as single source of truth

## Project Structure

```
teen_civics/
├── .github/workflows/    # GitHub Actions workflows
├── src/                  # Source code
│   ├── config.py         # Centralized configuration management
│   ├── load_env.py       # Environment variable loading
│   ├── orchestrator.py   # Main orchestration logic
│   ├── fetchers/         # Data fetching modules (Congress.gov)
│   ├── processors/       # Data processing and summarization
│   ├── publishers/       # Social media publishing
│   └── database/         # Database management
├── scripts/              # Utility scripts
├── data/                 # Data storage (legacy SQLite, now using PostgreSQL)
├── tests/                # Comprehensive test suites
├── static/               # Static web assets (CSS, JS, images)
├── templates/            # Flask HTML templates
├── .env.example          # Environment variables template
├── requirements.txt      # Production dependencies
├── requirements-dev.txt  # Development dependencies
└── README.md             # Project documentation
```

## Setup Instructions

1. **Clone the repository**
   ```bash
   git clone https://github.com/liv-skeete/teen_civics.git
   cd teen_civics
   ```

2. **Create a virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   
   # For development (includes testing and linting tools)
   pip install -r requirements-dev.txt
   ```

4. **Configure environment variables**
   ```bash
   cp .env.example .env
   ```
   Edit `.env` and add your API keys (see [Configuration](#configuration) section below for details):
   - `CONGRESS_API_KEY` - Get from [Congress.gov API](https://api.congress.gov/)
   - `ANTHROPIC_API_KEY` - Get from [Anthropic Console](https://console.anthropic.com/)
   - `TWITTER_API_KEY`, `TWITTER_API_SECRET`, `TWITTER_ACCESS_TOKEN`, `TWITTER_ACCESS_SECRET` - Get from [Twitter Developer Portal](https://developer.twitter.com/)
   - `DATABASE_URL` - PostgreSQL connection string (e.g., from [Supabase](https://supabase.com/))

5. **Initialize the database**
   ```bash
   # The database schema will be created automatically on first run
   # Or use the migration script if needed
   python scripts/migrate_to_postgresql.py
   ```

6. **Run the web application**
   ```bash
   python app.py
   # Visit http://localhost:5000 in your browser
   ```

7. **Run the orchestrator** (for processing and posting bills)
   ```bash
   python src/orchestrator.py
   ```

## Configuration

The project uses a centralized configuration system in [`src/config.py`](src/config.py) that loads and validates all settings from environment variables.

### Configuration Sections

- **DatabaseConfig**: PostgreSQL or SQLite database connection
- **CongressAPIConfig**: Congress.gov API credentials
- **AnthropicConfig**: Claude AI API credentials
- **TwitterConfig**: Twitter/X API credentials
- **FlaskConfig**: Web application settings (debug, port, host)
- **LoggingConfig**: Logging level and format

### Using Configuration in Code

```python
from src.config import get_config

config = get_config()

# Access configuration sections
db_url = config.database.url
api_key = config.congress_api.api_key

# Validate all configuration
if config.validate_all():
    print("All configuration is valid!")
```

### Configuration Validation

The configuration system automatically validates all required settings on startup and logs warnings for any missing credentials. You can also manually validate:

```python
config = get_config()
config.validate_all()  # Returns True if all required config is present
```

## GitHub Actions

### Daily Workflow
- Runs every day at 17:00 UTC
- Fetches recent bills from Congress.gov and processes the first unposted bill
- Uses atomic, idempotent database updates to prevent duplicate tweets
- If top bill is already tweeted, exits gracefully without posting
- Maintains concurrency protection to prevent parallel runs

### Weekly Workflow
- Runs every Sunday at 9:00 AM UTC
- Processes weekly digest content

## Database Features

The PostgreSQL database serves as the single source of truth and provides:

- **Atomic, idempotent tweet updates**: Guaranteed no duplicate tweets with `UPDATE ... WHERE tweet_posted = FALSE RETURNING`
- **Tweeted-only content filtering**: Homepage and archive show only bills that have been successfully tweeted
- **Bill deduplication**: Scans Congress.gov bills and skips any already marked as tweeted
- **Composite indexing**: Optimized queries for homepage (`tweet_posted, date_processed DESC`)
- **Storage of both short tweet summaries and long-form explanations**
- **Support for website integration with slug-based URLs**
- **Poll tracking for user engagement**

## System Architecture

### PostgreSQL as Single Source of Truth
- All website content comes directly from the database
- Homepage shows the most recently tweeted bill via `get_latest_tweeted_bill()`
- Archive shows all tweeted bills via `get_all_tweeted_bills()`
- No untweeted content is displayed to users

### Orchestrator Duplicate Prevention
1. Fetches 5 most recent bills from Congress.gov
2. Scans bills in order, skipping any already tweeted
3. Processes the first unposted bill found
4. Falls back to database unposted bills if API bills are all tweeted
5. Uses atomic updates with verification to ensure tweet status is properly set
6. Marks bills as problematic if verification fails to prevent future selection

### Atomic Tweet Updates
The `update_tweet_info()` function ensures:
- Updates only occur if `tweet_posted = FALSE`
- Returns success for idempotent calls (already tweeted with same URL)
- Returns failure for URL mismatches or missing bills
- Prevents race conditions and duplicate tweets

## Development

### Running Tests

```bash
# Install development dependencies
pip install -r requirements-dev.txt

# Run all tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html

# Run specific test file
pytest tests/test_orchestrator.py
```

### Code Quality

```bash
# Format code with black
black src/ tests/

# Lint with flake8
flake8 src/ tests/

# Type checking with mypy
mypy src/
```

### Development Scripts

The [`scripts/`](scripts/) directory contains utility scripts:

- [`dev.sh`](scripts/dev.sh) - Development environment setup
- [`migrate_to_postgresql.py`](scripts/migrate_to_postgresql.py) - Database migration
- [`reprocess_bill_summaries.py`](scripts/reprocess_bill_summaries.py) - Reprocess summaries
- [`cleanup_summaries.py`](scripts/cleanup_summaries.py) - Clean up database

## Troubleshooting

### Database Connection Issues

If you encounter database connection errors:

1. Verify your `DATABASE_URL` is set correctly in `.env`
2. Check that your PostgreSQL server is running
3. Ensure your database credentials are correct
4. See [`DATABASE_SETUP.md`](DATABASE_SETUP.md) for detailed setup instructions

### Environment Variable Loading

If environment variables aren't loading:

1. Ensure `.env` file exists in the project root
2. Check that [`src/load_env.py`](src/load_env.py) is being called before configuration
3. Verify `.env` file format (no spaces around `=`)

### API Rate Limits

- **Congress.gov API**: 5,000 requests per hour
- **Anthropic API**: Varies by plan
- **Twitter API**: Varies by tier (Free, Basic, Pro)

If you hit rate limits, the application will log warnings and may need to retry later.

### Common Issues

**Issue**: `ModuleNotFoundError: No module named 'src'`  
**Solution**: Ensure you're running commands from the project root directory

**Issue**: Database schema errors  
**Solution**: Run the migration script: `python scripts/migrate_to_postgresql.py`

**Issue**: Twitter posting fails  
**Solution**: Verify all Twitter API credentials are set and your app has write permissions

## Contributing

We welcome contributions! Please see [`CONTRIBUTING.md`](CONTRIBUTING.md) for detailed guidelines.

Quick start:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

Please report bugs and feature requests using the [GitHub Issues](https://github.com/liv-skeete/teen_civics/issues) page.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.