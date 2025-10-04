# Changelog

All notable changes to the TeenCivics project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.0.0] - 2025-10-01

### Added

- **Centralized Configuration System** ([`src/config.py`](src/config.py))
  - Created typed configuration classes using dataclasses for better type safety
  - Implemented `DatabaseConfig`, `CongressAPIConfig`, `AnthropicConfig`, `TwitterConfig`, `FlaskConfig`, and `LoggingConfig`
  - Added configuration validation methods to ensure all required settings are present
  - Implemented global configuration instance with `get_config()` and `reset_config()` functions
  - Added automatic logging of configuration status on startup

- **Development Dependencies** ([`requirements-dev.txt`](requirements-dev.txt))
  - Created separate development requirements file for testing and development tools
  - Includes pytest, pytest-cov, black, flake8, mypy, and other development utilities
  - Separates production dependencies from development-only packages

- **Enhanced Error Handling**
  - Added comprehensive error handling throughout the codebase
  - Improved logging with structured error messages
  - Added validation checks for API credentials and database connections

- **Comprehensive .gitignore** ([`.gitignore`](.gitignore))
  - Added Python-specific ignore patterns (\_\_pycache\_\_, *.pyc, *.pyo, etc.)
  - Added virtual environment patterns (venv/, env/, .venv/)
  - Added IDE-specific patterns (VSCode, PyCharm, etc.)
  - Added OS-specific patterns (macOS .DS_Store, Windows Thumbs.db)
  - Added development and testing artifacts
  - Added security-sensitive files (.env, *.key, *.pem)

### Changed

- **Environment Loading** ([`src/load_env.py`](src/load_env.py))
  - Refactored environment variable loading into dedicated module
  - Added support for multiple .env file locations
  - Improved error handling for missing .env files
  - Added logging for environment loading status

- **Database Connection** ([`src/database/connection.py`](src/database/connection.py))
  - Updated to use centralized configuration system
  - Improved connection error handling and logging
  - Added better support for both PostgreSQL and SQLite

- **Project Structure**
  - Reorganized configuration management into [`src/config.py`](src/config.py)
  - Improved module organization and imports
  - Enhanced code documentation and type hints

### Fixed

- **Database Connection Issue**
  - Fixed environment variable loading order causing database connection failures
  - Ensured .env file is loaded before any database operations
  - Added proper error messages for missing DATABASE_URL

- **Creator Image Path** ([`static/img/creator.jpg`](static/img/creator.jpg))
  - Corrected image reference from .svg to .jpg format
  - Fixed broken image display on website

### Removed

- **Redundant Test Files**
  - Removed `debug_imports.py` (debugging script no longer needed)
  - Removed `post_tweet_test.py` (superseded by comprehensive test suite)
  - Removed `twitter_test.py` (superseded by comprehensive test suite)
  - Removed `test_orchestrator_enhanced.py` (duplicate test file)
  - Removed `test_database.py` (superseded by [`tests/test_database_queries.py`](tests/test_database_queries.py))
  - Removed `test_summarizer_fix.py` (temporary debugging file)
  - Removed `imghdr.py` (unused utility)
  - Removed `reprocess_latest_bill.py` (moved to [`scripts/reprocess_latest_bill.py`](scripts/reprocess_latest_bill.py))
  - Removed `test_db_connection.py` (superseded by configuration validation)

### Security

- **Enhanced .gitignore Protection**
  - Added comprehensive patterns to prevent accidental commit of sensitive files
  - Protected API keys, credentials, and environment files
  - Added patterns for SSL certificates and private keys

- **Configuration Validation**
  - Added validation checks for all API credentials
  - Implemented secure configuration loading with proper error handling
  - Added warnings for missing or invalid credentials

## [1.0.0] - 2025-09-15

### Added

- Initial release of TeenCivics
- Congress.gov API integration
- Claude AI summarization
- Twitter/X posting functionality
- PostgreSQL database with atomic updates
- GitHub Actions workflows for automation
- Flask web application
- Comprehensive test suite

[2.0.0]: https://github.com/liv-skeete/teen_civics/compare/v1.0.0...v2.0.0
[1.0.0]: https://github.com/liv-skeete/teen_civics/releases/tag/v1.0.0