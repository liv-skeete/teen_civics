# TeenCivics

TeenCivics makes government accessible for young people by posting daily plain‑English summaries of congressional bills from Congress.gov.

## Features

- Fetch data from Congress.gov API for the most recent bills
- Summarize content using Claude AI for easy understanding  
- Post updates to X/Twitter using Tweepy
- Store processed data in SQLite database for tracking and deduplication
- Automate daily posting with GitHub Actions

## Project Structure

```
teen_civics/
├── .github/workflows/    # GitHub Actions workflows
├── src/                  # Source code
│   ├── fetchers/         # Data fetching modules (Congress.gov)
│   ├── processors/       # Data processing and summarization
│   ├── publishers/       # Social media publishing
│   └── database/         # Database management
├── config/               # Configuration files
├── data/                 # Data storage (SQLite)
├── tests/                # Test suites
├── .env.example          # Environment variables template
├── requirements.txt      # Python dependencies
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
   ```

4. **Configure environment variables**
   ```bash
   cp .env.example .env
   ```
   Edit `.env` and add your API keys:
   - `CONGRESS_GOV_API_KEY`
   - `ANTHROPIC_API_KEY`
   - `TWITTER_API_KEY`
   - `TWITTER_API_SECRET`
   - `TWITTER_ACCESS_TOKEN`
   - `TWITTER_ACCESS_SECRET`

5. **Run the orchestrator script**
   ```bash
   python src/orchestrator.py
   ```

## GitHub Actions

### Daily Workflow
- Runs every morning at 8:00 AM UTC
- Fetches new bills from Congress.gov
- Generates summaries and posts to X/Twitter
- Prevents duplicate posts using SQLite database

## Database Features

The SQLite database provides:
- Bill deduplication to prevent reposting
- Storage of both short tweet summaries and long-form explanations
- Support for future website integration with slug-based URLs
- Poll tracking for user engagement

## Contributing

We welcome contributions! Here's how you can help:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

Please report bugs and feature requests using the [GitHub Issues](https://github.com/liv-skeete/teen_civics/issues) page.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.