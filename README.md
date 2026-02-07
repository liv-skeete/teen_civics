# TeenCivics

[![MIT License](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**TeenCivics** makes government accessible for young people by posting daily plain-English summaries of congressional bills from Congress.gov.

🌐 **Live site**: [teencivics.org](https://teencivics.org)

## About The Project

TeenCivics was created to help young people understand the legislative process and stay informed about the bills being considered in the U.S. Congress. By providing clear, concise summaries of complex legislation, TeenCivics aims to foster civic engagement and make government more transparent for the next generation of voters.

### Features

- **Daily Bill Summaries** — Automated fetching and AI-powered summarization of the most recent bills from Congress.gov, written in plain language for teens (ages 13-19).
- **Teen Impact Score** — Each bill gets a 0-10 score estimating how directly it affects teenagers, with a rubric distinguishing direct, indirect, and symbolic impacts.
- **Multi-Platform Social Posting** — Daily updates automatically posted to X/Twitter, Bluesky, and Threads.
- **Community Polls** — Vote on bills to share your opinion and see how others voted.
- **Sponsor Reveal** — Vote on a bill to unlock information about who sponsored it.
- **Bill Archive** — Browse, search, and filter all previously summarized bills with full-text search and sponsor search.
- **Dark Mode** — Full dark/light theme support with system preference detection.
- **Civic Resources** — Curated links to voter registration, contacting representatives, and understanding government.
- **Term Dictionary** — Links to congressional glossaries for unfamiliar legislative terminology.
- **Responsive Design** — Mobile-friendly layout for all pages.
- **SEO Optimized** — Open Graph and Twitter Card meta tags for rich social previews.

## Built With

*   [Python 3.10+](https://www.python.org/)
*   [Flask](https://flask.palletsprojects.com/) with Flask-Limiter and Flask-WTF for rate limiting and CSRF protection
*   [PostgreSQL](https://www.postgresql.org/) with connection pooling
*   [Venice AI](https://venice.ai/) (Claude-compatible API) for bill summarization
*   [Congress.gov API](https://api.congress.gov/) for bill data
*   [Tweepy](https://www.tweepy.org/) for X/Twitter posting
*   [atproto](https://atproto.blue/) for Bluesky posting
*   Meta Threads Graph API for Threads posting
*   [Playwright](https://playwright.dev/) for web scraping bill text and tracker data
*   [Gunicorn](https://gunicorn.org/) for production WSGI serving

## Getting Started

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
    -   Add your API keys and database URL to the `.env` file. Required keys:
        *   `CONGRESS_API_KEY` — Congress.gov API
        *   `VENICE_API_KEY` — Venice AI (Claude-compatible)
        *   `DATABASE_URL` — PostgreSQL connection string
        *   `TWITTER_API_KEY`, `TWITTER_API_SECRET`, `TWITTER_ACCESS_TOKEN`, `TWITTER_ACCESS_SECRET` — X/Twitter API
        *   `BLUESKY_HANDLE`, `BLUESKY_APP_PASSWORD` — Bluesky AT Protocol
        *   `THREADS_USER_ID`, `THREADS_ACCESS_TOKEN` — Meta Threads API
    -   Optional:
        *   `GA_MEASUREMENT_ID` — Google Analytics
        *   `SUMMARIZER_MODEL` — AI model (defaults to `claude-sonnet-45`)

5.  **Initialize the database**
    The database schema is created automatically on the first run.

## Usage

1.  **Run the web application**
    ```sh
    python app.py
    ```
    Navigate to `http://127.0.0.1:5000` in your browser.

2.  **Run the orchestrator** (fetch → summarize → store → post)
    ```sh
    python src/orchestrator.py
    ```

3.  **Dry run** (no posting, no DB updates)
    ```sh
    python src/orchestrator.py --dry-run
    ```

## Deployment

TeenCivics is deployed on [Railway.app](https://railway.app) with the following architecture:

- **Platform**: Railway.app with 512MB RAM, 1 vCPU instance
- **Web Server**: Gunicorn with 2 workers optimized for memory constraints
- **Database**: PostgreSQL with SSL connections and connection pooling
- **SSL**: Automatic HTTPS via Cloudflare
- **Domain**: [teencivics.org](https://teencivics.org)

For deployment instructions, see [DEPLOYMENT_RAILWAY.md](DEPLOYMENT_RAILWAY.md).

## CI and Automation

- **Daily posting**: [.github/workflows/daily.yml](.github/workflows/daily.yml) — Runs twice daily (9:00 AM ET morning scan, 10:30 PM ET evening scan). Fetches new bills, generates summaries, and posts to X/Twitter, Bluesky, and Threads.
- **Database backup**: [.github/workflows/db-backup.yml](.github/workflows/db-backup.yml)
- **Security scanning**: [.github/workflows/security-scan.yml](.github/workflows/security-scan.yml)
- **Test orchestrator**: [.github/workflows/test-orchestrator.yml](.github/workflows/test-orchestrator.yml)

## Security

This repo follows a strict "No secrets in source" policy. See [SECURITY.md](SECURITY.md).

- Credentials loaded at runtime via environment variables
- CI blocks leaks using a repo scanner: `python scripts/secret_scan.py`
- Database connections use SSL by default
- Duplicate post prevention and row-level locking to avoid race conditions

## Teen Impact Score

Each bill receives a Teen Impact Score (0-10) that estimates how directly and significantly a bill affects teenagers:

| Score | Category | Example |
|-------|----------|---------|
| 8-10 | Direct impact on teen daily life | School funding, youth programs, age-related restrictions |
| 5-7 | Indirect impact via family/community | Tax credits to parents, healthcare, infrastructure |
| 2-4 | Symbolic/awareness without material impact | Awareness months, commemorative resolutions |
| 0-1 | Minimal/no teen connection | Highly specialized industry regulations |

## Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

Distributed under the MIT License. See [LICENSE](LICENSE) for more information.

## Contact

Olivia (Liv) Skeete

- **Website**: [teencivics.org](https://teencivics.org)
- **X/Twitter**: [@TeenCivics](https://twitter.com/TeenCivics)
- **Bluesky**: [@teencivics.bsky.social](https://bsky.app/profile/teencivics.bsky.social)
- **Threads**: [@teen.civics](https://www.threads.net/@teen.civics)
- **GitHub**: [liv-skeete/teen_civics](https://github.com/liv-skeete/teen_civics)
