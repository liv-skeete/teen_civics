# TeenCivics

[![MIT License](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

TeenCivics makes government accessible for young people by posting daily plain-English summaries of congressional bills from Congress.gov.

## About The Project

This project was created to help young people understand the legislative process and stay informed about the bills being considered in the U.S. Congress. By providing clear, concise summaries of complex legislation, TeenCivics aims to foster civic engagement and make government more transparent for the next generation of voters.

Key features include:
- Automated fetching of the most recent bills from the Congress.gov API.
- AI-powered summarization using Claude AI for easy-to-understand content.
- Teen Impact Score that estimates how much each bill affects teens.
- Daily updates posted to X/Twitter via Tweepy.
- A PostgreSQL database for robust data tracking and deduplication.
- A public-facing website to display all tweeted bill summaries.

## Built With

This project is built with a modern Python stack:

*   [Python 3.10+](https://www.python.org/)
*   [Flask](https://flask.palletsprojects.com/) with Flask-Limiter and Flask-WTF for rate limiting and CSRF protection
*   [PostgreSQL](https://www.postgresql.org/)
*   [SQLAlchemy](https://www.sqlalchemy.org/)
*   [Tweepy](https://www.tweepy.org/)
*   [Anthropic API (Claude)](https://www.anthropic.com/)
*   [Congress.gov API](https://api.congress.gov/)
*   [BeautifulSoup4](https://www.crummy.com/software/BeautifulSoup/) and [Playwright](https://playwright.dev/) for web scraping
*   [Gunicorn](https://gunicorn.org/) for production WSGI serving

## Getting Started

To get a local copy up and running, follow these simple steps.

### Prerequisites

*   Python 3.10+
*   pip
*   A PostgreSQL database

### Installation

1.  **Clone the repository**
    ```sh
    git clone https://github.com/liv-skeete/teen_civics.git
    cd teen_civics
    ```
2.  **Create and activate a virtual environment**
    ```sh
    python -m venv venv
    source venv/bin/activate
    ```
3.  **Install dependencies**
    ```sh
    pip install -r requirements.txt
    ```
4.  **Configure environment variables**
    -   Copy the example `.env` file:
        ```sh
        cp .env.example .env
        ```
    -   Add your API keys and database URL to the `.env` file. You will need keys for:
        *   Congress.gov API (`CONGRESS_API_KEY`)
        *   Anthropic API (`ANTHROPIC_API_KEY`)
        *   Twitter/X API (`TWITTER_API_KEY`, `TWITTER_API_SECRET_KEY`, `TWITTER_ACCESS_TOKEN`, `TWITTER_ACCESS_TOKEN_SECRET`)
        *   Your PostgreSQL `DATABASE_URL`
        *   Optional: `GA_MEASUREMENT_ID` for Google Analytics
        *   Optional: `SUMMARIZER_MODEL` to specify Claude model (defaults to claude-sonnet-4-5)

5.  **Initialize the database**
    The database schema is created automatically on the first run.

## Usage

There are two main components to this application: the web server and the bill processing orchestrator.

1.  **Run the web application**
    ```sh
    python app.py
    ```
    Navigate to `http://127.0.0.1:5000` in your browser to see the website.

2.  **Run the orchestrator**
    This script fetches, summarizes, and posts new bills.
    ```sh
    python src/orchestrator.py
    ```

## Contributing

Contributions are what make the open-source community such an amazing place to learn, inspire, and create. Any contributions you make are **greatly appreciated**.

Please see [`CONTRIBUTING.md`](CONTRIBUTING.md:1) for detailed guidelines on how to get started.

## Deployment

TeenCivics is deployed on Railway.app using Gunicorn as the WSGI server with a production-optimized configuration. The application is served with automatic SSL through Railway's built-in reverse proxy and load balancing.

## Custom Domain

The application is accessible at [teencivics.org](https://teencivics.org) with SSL provided by Cloudflare.

## Production Architecture

- **Platform**: Railway.app with 512MB RAM, 1 vCPU instance
- **Web Server**: Gunicorn with 2 workers optimized for memory constraints
- **Process Management**: Managed by Railway's process orchestration
- **Database**: PostgreSQL with SSL connections and connection pooling
- **SSL**: Automatic HTTPS with Cloudflare integration
- **Monitoring**: Built-in Railway logging and metrics

For deployment instructions, see [DEPLOYMENT_RAILWAY.md](DEPLOYMENT_RAILWAY.md). Legacy AWS deployment instructions are in [`DEPLOYMENT.md`](DEPLOYMENT.md:1).

## License

Distributed under the MIT License. See [`LICENSE`](LICENSE:1) for more information.

## Contact

Olivia (Liv) Skeete - [@TeenCivics](https://twitter.com/TeenCivics) - liv@di.st

Project Link: [https://github.com/liv-skeete/teen_civics](https://github.com/liv-skeete/teen_civics)

---

## Teen Impact Score

TeenCivics includes a Teen Impact Score that estimates how directly and significantly a bill affects teenagers. The score is derived from bill topic areas, scope, enforcement, and proximity to youth programs and schools. It is displayed on the site alongside summaries to help teens quickly gauge relevance.

Developer tools:
- Regenerate any missing scores:
  - python [scripts/regenerate_missing_teen_impact_scores.py](scripts/regenerate_missing_teen_impact_scores.py:1)
- Tests (if present) live under [tests/](tests)

## Security and Secrets

This repo follows a strict "No secrets in source" policy. See [SECURITY.md](SECURITY.md).

- Load credentials at runtime via [load_env()](src/load_env.py:6)
- CI blocks leaks using a repo scanner:
  - Run locally before committing:
    - python [scripts/secret_scan.py](scripts/secret_scan.py:1)

## CI and Automation

- Daily posting workflow: [.github/workflows/daily.yml](.github/workflows/daily.yml:1)
  - Runs twice daily (9:00 AM ET and 10:30 PM ET)
  - Uses GitHub Actions Secrets (masked in logs)
  - Performs secret scanning early to block leaks
  - Uses Playwright for bill text extraction with fallback to API
- Test workflow: [.github/workflows/test-orchestrator.yml](.github/workflows/test-orchestrator.yml:1)
- Weekly digest workflow (disabled): [.github/workflows/weekly.yml](.github/workflows/weekly.yml:1)

## Production Readiness Checklist

- Secrets are not logged or embedded in code
  - Environment dumping removed from orchestrator
- Secret scanning enforced in CI
- Database connections use SSL by default via [init_connection_pool()](src/database/connection.py:73)
- Duplicate tweet prevention enabled via [has_posted_today()](src/database/db.py:103)
- Idempotent tweet updates and row-level locking to avoid race conditions

## Local Development

- Web app: python [app.py](app.py:1) then open http://127.0.0.1:5000
- Orchestrator (fetch → summarize → store → tweet): python [src/orchestrator.py](src/orchestrator.py:1)
- Secret scan: python [scripts/secret_scan.py](scripts/secret_scan.py:1)
- Run tests: `pytest tests/`
- Optional: install pre-commit and add a hook to run secret_scan before each commit
- For development with browser automation: Playwright is used for bill text extraction (installed automatically in CI)

## Future Improvements (TODO)

The following enhancements are planned for future versions:

- **Weekly Digest**: Implement weekly summary feature (workflow exists but functionality not yet complete)
- **Documentation**: Add architecture diagram and status badge to README
- **SEO**: Implement structured data markup (JSON-LD) and canonical URLs
- **Accessibility**: Remove emoji from summaries for screen reader compatibility
- **Monitoring**: Set up full monitoring stack with error tracking and performance metrics
- **CI/CD**: Add GitHub Actions concurrency controls to prevent overlapping workflows