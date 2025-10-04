# TeenCivics

[![MIT License](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

TeenCivics makes government accessible for young people by posting daily plain-English summaries of congressional bills from Congress.gov.

## About The Project

This project was created to help young people understand the legislative process and stay informed about the bills being considered in the U.S. Congress. By providing clear, concise summaries of complex legislation, TeenCivics aims to foster civic engagement and make government more transparent for the next generation of voters.

Key features include:
- Automated fetching of the most recent bills from the Congress.gov API.
- AI-powered summarization using Claude AI for easy-to-understand content.
- Daily updates posted to X/Twitter via Tweepy.
- A PostgreSQL database for robust data tracking and deduplication.
- A public-facing website to display all tweeted bill summaries.

## Built With

This project is built with a modern Python stack:

*   [Python](https://www.python.org/)
*   [Flask](https://flask.palletsprojects.com/)
*   [PostgreSQL](https://www.postgresql.org/)
*   [SQLAlchemy](https://www.sqlalchemy.org/)
*   [Tweepy](https://www.tweepy.org/)
*   [Anthropic API (Claude)](https://www.anthropic.com/)
*   [Congress.gov API](https://api.congress.gov/)

## Getting Started

To get a local copy up and running, follow these simple steps.

### Prerequisites

*   Python 3.8+
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
        *   Congress.gov API
        *   Anthropic API
        *   Twitter/X API (Consumer Key, Consumer Secret, Access Token, Access Token Secret)
        *   Your PostgreSQL `DATABASE_URL`

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

## License

Distributed under the MIT License. See `LICENSE` for more information (though a LICENSE file does not exist yet, this is standard practice).

## Contact

Olivia (Liv) Skeete - [@TeenCivics](https://twitter.com/TeenCivics) - liv@di.st

Project Link: [https://github.com/liv-skeete/teen_civics](https://github.com/liv-skeete/teen_civics)