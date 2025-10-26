"""
Centralized configuration management for TeenCivics.
Loads and validates environment variables with typed configuration classes.
"""

import os
import logging
from dataclasses import dataclass
from typing import Optional

# Use module logger (do NOT call basicConfig here; app.py owns logging)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


@dataclass
class DatabaseConfig:
    """Database configuration."""
    url: str

    @property
    def is_postgresql(self) -> bool:
        # Support both postgres:// and postgresql://
        return self.url.startswith(("postgresql://", "postgres://"))

    @property
    def is_sqlite(self) -> bool:
        return self.url.startswith("sqlite://") or not self.is_postgresql


@dataclass
class CongressAPIConfig:
    """Congress.gov API configuration."""
    api_key: str

    def validate(self) -> bool:
        if not self.api_key:
            logger.warning("CONGRESS_API_KEY is not set")
            return False
        return True


@dataclass
class AnthropicConfig:
    """Anthropic (Claude) API configuration."""
    api_key: str

    def validate(self) -> bool:
        if not self.api_key:
            logger.warning("ANTHROPIC_API_KEY is not set")
            return False
        return True


@dataclass
class TwitterConfig:
    """Twitter/X API configuration."""
    api_key: str
    api_secret: str
    bearer_token: str
    access_token: str
    access_secret: str
    client_id: Optional[str] = None
    client_secret: Optional[str] = None

    def validate(self) -> bool:
        required = [
            self.api_key,
            self.api_secret,
            self.bearer_token,
            self.access_token,
            self.access_secret,
        ]
        if not all(required):
            logger.warning("Twitter API credentials are incomplete")
            return False
        return True


@dataclass
class FlaskConfig:
    """Flask application configuration."""
    debug: bool = False
    port: int = 5000
    host: str = "0.0.0.0"
    ga_measurement_id: Optional[str] = None

    @classmethod
    def from_env(cls) -> "FlaskConfig":
        return cls(
            debug=os.getenv("FLASK_DEBUG", "False").lower() == "true",
            port=int(os.getenv("PORT", "5000")),
            host=os.getenv("FLASK_HOST", "0.0.0.0"),
            ga_measurement_id=os.getenv("GA_MEASUREMENT_ID"),
        )


@dataclass
class LoggingConfig:
    """Logging configuration (format/level only—handlers set in app.py)."""
    level: str = "INFO"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    file_path: Optional[str] = None

    @classmethod
    def from_env(cls) -> "LoggingConfig":
        return cls(
            level=os.getenv("LOG_LEVEL", "INFO").upper(),
            format=os.getenv(
                "LOG_FORMAT", "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            ),
            file_path=os.getenv("LOG_FILE"),
        )


class Config:
    """Main configuration class that aggregates all configuration sections."""

    def __init__(self):
        """Initialize configuration by loading environment variables."""

        # Load .env ONLY for local development (skip in Railway/containers)
        if not os.environ.get("RAILWAY_ENVIRONMENT") and os.path.exists(".env"):
            try:
                from src.load_env import load_env
                load_env()
                logger.info("Loaded .env for local development.")
            except Exception as e:
                logger.info(f"Skipping .env load: {e}")

        # Initialize configuration sections
        self.database = self._load_database_config()
        self.congress_api = self._load_congress_config()
        self.anthropic = self._load_anthropic_config()
        self.twitter = self._load_twitter_config()
        self.flask = FlaskConfig.from_env()
        self.logging = LoggingConfig.from_env()

        # Log configuration status
        self._log_config_status()

    def _load_database_config(self) -> DatabaseConfig:
        database_url = os.getenv("DATABASE_URL", "")
        if not database_url:
            # Fallback to SQLite if no DATABASE_URL is set (dev only)
            database_url = "sqlite:///data/bills.db"
            logger.warning("DATABASE_URL not set, using SQLite fallback: %s", database_url)
        return DatabaseConfig(url=database_url)

    def _load_congress_config(self) -> CongressAPIConfig:
        return CongressAPIConfig(api_key=os.getenv("CONGRESS_API_KEY", ""))

    def _load_anthropic_config(self) -> AnthropicConfig:
        return AnthropicConfig(api_key=os.getenv("ANTHROPIC_API_KEY", ""))

    def _load_twitter_config(self) -> TwitterConfig:
        return TwitterConfig(
            api_key=os.getenv("TWITTER_API_KEY", ""),
            api_secret=os.getenv("TWITTER_API_SECRET", ""),
            bearer_token=os.getenv("TWITTER_BEARER_TOKEN", ""),
            access_token=os.getenv("TWITTER_ACCESS_TOKEN", ""),
            access_secret=os.getenv("TWITTER_ACCESS_SECRET", ""),
            client_id=os.getenv("TWITTER_CLIENT_ID"),
            client_secret=os.getenv("TWITTER_CLIENT_SECRET"),
        )

    def _log_config_status(self):
        logger.info("Configuration loaded:")
        logger.info("  Database: %s", "PostgreSQL" if self.database.is_postgresql else "SQLite")
        logger.info("  Congress API: %s", "configured" if self.congress_api.validate() else "missing")
        logger.info("  Anthropic API: %s", "configured" if self.anthropic.validate() else "missing")
        logger.info("  Twitter API: %s", "configured" if self.twitter.validate() else "missing")
        logger.info("  Flask: debug=%s, port=%d", self.flask.debug, self.flask.port)

    def validate_all(self) -> bool:
        validations = [
            ("Database", bool(self.database.url)),
            ("Congress API", self.congress_api.validate()),
            ("Anthropic API", self.anthropic.validate()),
            ("Twitter API", self.twitter.validate()),
        ]
        all_valid = all(valid for _, valid in validations)
        if not all_valid:
            logger.warning("Some configuration sections are invalid:")
            for name, valid in validations:
                if not valid:
                    logger.warning("  - %s: invalid or missing", name)
        return all_valid


# Global configuration instance
_config: Optional[Config] = None


def get_config() -> Config:
    global _config
    if _config is None:
        _config = Config()
    return _config


def reset_config():
    """Reset the global configuration instance (useful for testing)."""
    global _config
    _config = None