# TeenCivics Code Quality Implementation Plan
**Date:** October 1, 2025  
**Based on:** [CODE_QUALITY_ANALYSIS.md](CODE_QUALITY_ANALYSIS.md)

---

## Overview

This document provides a prioritized, actionable implementation plan for addressing the issues identified in the code quality analysis. Tasks are organized by priority and estimated effort.

---

## 🔴 Phase 1: Critical Security Issues (IMMEDIATE - Day 1)

### Task 1.1: Secure API Credentials
**Priority:** CRITICAL  
**Effort:** 2-3 hours  
**Owner:** DevOps/Security Lead  
**Mode:** Manual (Security-sensitive)

**Steps:**
1. **Rotate all exposed credentials immediately:**
   - Anthropic API key (regenerate at console.anthropic.com)
   - Twitter API keys (regenerate at developer.twitter.com)
   - Twitter OAuth credentials (regenerate)
   
2. **Remove .env from git history:**
   ```bash
   # Use BFG Repo-Cleaner or git-filter-repo
   git filter-repo --path .env --invert-paths
   # Force push to all branches
   git push origin --force --all
   ```

3. **Update GitHub Secrets:**
   - Add all new credentials to GitHub repository secrets
   - Verify workflows use secrets correctly

4. **Verify .env is ignored:**
   ```bash
   git rm --cached .env
   git commit -m "Remove .env from tracking"
   ```

**Verification:**
- [ ] All API keys rotated
- [ ] .env removed from git history
- [ ] GitHub Secrets updated
- [ ] Workflows tested with new secrets
- [ ] .env not in git status

**Dependencies:** None  
**Blocks:** All other tasks (must complete first)

---

### Task 1.2: Remove Legacy Database Files
**Priority:** CRITICAL  
**Effort:** 30 minutes  
**Owner:** Backend Developer  
**Mode:** Code Mode

**Steps:**
1. **Backup SQLite data (if needed):**
   ```bash
   mkdir -p archive/legacy-db
   cp data/bills.db* archive/legacy-db/
   ```

2. **Remove from repository:**
   ```bash
   git rm data/bills.db data/bills.db-shm data/bills.db-wal
   ```

3. **Update .gitignore:**
   ```gitignore
   # Databases / Data
   *.db
   *.db-shm
   *.db-wal
   data/*.db
   ```

4. **Commit changes:**
   ```bash
   git commit -m "Remove legacy SQLite database files"
   ```

**Verification:**
- [ ] SQLite files backed up (if needed)
- [ ] Files removed from repository
- [ ] .gitignore updated
- [ ] No database files in git status

**Dependencies:** Task 1.1  
**Blocks:** None

---

### Task 1.3: Remove Sensitive Log Files
**Priority:** CRITICAL  
**Effort:** 15 minutes  
**Owner:** Backend Developer  
**Mode:** Code Mode

**Steps:**
1. **Remove log files:**
   ```bash
   git rm run_orchestrator.log
   rm -f *.log
   ```

2. **Verify .gitignore includes logs:**
   ```gitignore
   *.log
   logs/
   ```

3. **Update logging to never log credentials:**
   - Review [`src/orchestrator.py`](src/orchestrator.py:42-46)
   - Remove credential logging entirely (even masked)

**Verification:**
- [ ] Log files removed
- [ ] .gitignore includes *.log
- [ ] No credential logging in code

**Dependencies:** Task 1.1  
**Blocks:** None

---

## 🟠 Phase 2: High Priority Cleanup (Week 1)

### Task 2.1: Consolidate Test Files
**Priority:** HIGH  
**Effort:** 3-4 hours  
**Owner:** Backend Developer  
**Mode:** Code Mode

**Steps:**
1. **Review root test files for unique functionality:**
   - [`test_database.py`](test_database.py:1)
   - [`test_db_connection.py`](test_db_connection.py:1)
   - [`test_orchestrator_enhanced.py`](test_orchestrator_enhanced.py:1)
   - [`test_summarizer_fix.py`](test_summarizer_fix.py:1)
   - [`post_tweet_test.py`](post_tweet_test.py:1)
   - [`twitter_test.py`](twitter_test.py:1)

2. **Merge unique tests into [`tests/`](tests/) directory:**
   - Database tests → [`tests/test_database_queries.py`](tests/test_database_queries.py:1)
   - Orchestrator tests → [`tests/test_orchestrator_enhanced.py`](tests/test_orchestrator_enhanced.py:1)
   - Add new test files as needed

3. **Remove redundant root test files:**
   ```bash
   git rm test_database.py test_db_connection.py test_orchestrator_enhanced.py \
          test_summarizer_fix.py post_tweet_test.py twitter_test.py
   ```

4. **Update test documentation in README**

**Verification:**
- [ ] All unique test functionality preserved
- [ ] Tests pass: `pytest tests/`
- [ ] Root test files removed
- [ ] README updated with test instructions

**Dependencies:** Task 1.1  
**Blocks:** Task 2.5 (Test Coverage)

---

### Task 2.2: Remove Redundant Scripts
**Priority:** HIGH  
**Effort:** 1-2 hours  
**Owner:** Backend Developer  
**Mode:** Code Mode

**Steps:**
1. **Archive one-time migration scripts:**
   ```bash
   mkdir -p scripts/archive
   git mv scripts/migrate_to_postgresql.py scripts/archive/
   git mv scripts/cleanup_summaries.py scripts/archive/
   git mv scripts/workflow_cleanup.py scripts/archive/
   ```

2. **Remove duplicate reprocess script:**
   ```bash
   git rm reprocess_latest_bill.py
   # Keep scripts/reprocess_latest_bill.py as canonical version
   ```

3. **Document remaining scripts in README:**
   - [`scripts/dev.sh`](scripts/dev.sh:1) - Development server
   - [`scripts/seed_one_bill.py`](scripts/seed_one_bill.py:1) - Seed database
   - [`scripts/reprocess_latest_bill.py`](scripts/reprocess_latest_bill.py:1) - Reprocess bills

**Verification:**
- [ ] Migration scripts archived
- [ ] Duplicate scripts removed
- [ ] README documents remaining scripts
- [ ] Scripts still functional

**Dependencies:** Task 1.2  
**Blocks:** None

---

### Task 2.3: Remove Obsolete Files
**Priority:** HIGH  
**Effort:** 30 minutes  
**Owner:** Backend Developer  
**Mode:** Code Mode

**Steps:**
1. **Remove obsolete files:**
   ```bash
   git rm imghdr.py debug_imports.py dev-start.pid
   ```

2. **Update .gitignore for PID files:**
   ```gitignore
   *.pid
   ```

3. **Archive or integrate DATABASE_SETUP.md:**
   ```bash
   # Option 1: Archive
   git mv DATABASE_SETUP.md docs/archive/
   
   # Option 2: Integrate into README
   # Merge relevant content into README.md, then remove
   ```

**Verification:**
- [ ] Obsolete files removed
- [ ] .gitignore updated
- [ ] DATABASE_SETUP.md handled appropriately

**Dependencies:** Task 1.2  
**Blocks:** None

---

### Task 2.4: Implement Centralized Configuration
**Priority:** HIGH  
**Effort:** 4-6 hours  
**Owner:** Backend Developer  
**Mode:** Code Mode

**Steps:**
1. **Create `config.py` module:**
   ```python
   # config.py
   import os
   from typing import Optional
   from dataclasses import dataclass
   
   @dataclass
   class Config:
       # API Configuration
       CONGRESS_API_KEY: str
       ANTHROPIC_API_KEY: str
       TWITTER_API_KEY: str
       TWITTER_API_SECRET: str
       TWITTER_ACCESS_TOKEN: str
       TWITTER_ACCESS_SECRET: str
       TWITTER_BEARER_TOKEN: Optional[str] = None
       
       # Database Configuration
       DATABASE_URL: str
       
       # Application Configuration
       FLASK_ENV: str = "production"
       FLASK_DEBUG: bool = False
       FLASK_PORT: int = 5000
       
       # API Configuration
       CONGRESS_API_TIMEOUT: int = 30
       CONGRESS_API_LIMIT: int = 5
       
       # Model Configuration
       ANTHROPIC_MODEL_PREFERRED: str = "claude-3-5-sonnet-20240620"
       ANTHROPIC_MODEL_FALLBACK: str = "claude-3-haiku-20240307"
       
       @classmethod
       def from_env(cls) -> 'Config':
           """Load configuration from environment variables with validation."""
           # Implementation here
           pass
       
       def validate(self) -> None:
           """Validate configuration values."""
           # Implementation here
           pass
   ```

2. **Update modules to use Config:**
   - [`app.py`](app.py:1)
   - [`src/orchestrator.py`](src/orchestrator.py:1)
   - [`src/fetchers/congress_fetcher.py`](src/fetchers/congress_fetcher.py:1)
   - [`src/processors/summarizer.py`](src/processors/summarizer.py:1)
   - [`src/publishers/twitter_publisher.py`](src/publishers/twitter_publisher.py:1)

3. **Remove hardcoded values:**
   - Port numbers
   - Timeouts
   - Model names
   - API limits

4. **Add configuration validation on startup**

**Verification:**
- [ ] Config module created
- [ ] All modules use Config
- [ ] No hardcoded configuration values
- [ ] Configuration validated on startup
- [ ] Tests pass with new configuration

**Dependencies:** Task 1.1  
**Blocks:** Task 3.2 (Environment-based settings)

---

### Task 2.5: Improve Error Handling
**Priority:** HIGH  
**Effort:** 6-8 hours  
**Owner:** Backend Developer  
**Mode:** Code Mode

**Steps:**
1. **Create custom exception classes:**
   ```python
   # src/exceptions.py
   class TeenCivicsException(Exception):
       """Base exception for TeenCivics application."""
       pass
   
   class APIException(TeenCivicsException):
       """Exception for external API errors."""
       pass
   
   class DatabaseException(TeenCivicsException):
       """Exception for database errors."""
       pass
   
   class ConfigurationException(TeenCivicsException):
       """Exception for configuration errors."""
       pass
   ```

2. **Add specific exception handling:**
   - [`src/orchestrator.py`](src/orchestrator.py:234-239) - Replace generic Exception
   - [`src/fetchers/congress_fetcher.py`](src/fetchers/congress_fetcher.py:1) - Add retry logic
   - [`src/publishers/twitter_publisher.py`](src/publishers/twitter_publisher.py:147-161) - Specific API errors
   - [`src/database/connection.py`](src/database/connection.py:1) - Database-specific errors

3. **Implement retry logic with exponential backoff:**
   ```python
   # src/utils/retry.py
   from functools import wraps
   import time
   
   def retry_with_backoff(max_retries=3, base_delay=1):
       def decorator(func):
           @wraps(func)
           def wrapper(*args, **kwargs):
               for attempt in range(max_retries):
                   try:
                       return func(*args, **kwargs)
                   except Exception as e:
                       if attempt == max_retries - 1:
                           raise
                       delay = base_delay * (2 ** attempt)
                       time.sleep(delay)
               return None
           return wrapper
       return decorator
   ```

4. **Remove debug=True from production:**
   ```python
   # app.py
   if __name__ == '__main__':
       config = Config.from_env()
       app.run(
           debug=config.FLASK_DEBUG,
           port=config.FLASK_PORT
       )
   ```

**Verification:**
- [ ] Custom exceptions created
- [ ] Specific exception handling added
- [ ] Retry logic implemented
- [ ] Debug mode controlled by environment
- [ ] Error messages are informative
- [ ] Tests cover error conditions

**Dependencies:** Task 2.4  
**Blocks:** None

---

### Task 2.6: Centralize Logging Configuration
**Priority:** HIGH  
**Effort:** 3-4 hours  
**Owner:** Backend Developer  
**Mode:** Code Mode

**Steps:**
1. **Create centralized logging module:**
   ```python
   # src/logging_config.py
   import logging
   import sys
   from typing import Optional
   
   def setup_logging(
       level: str = "INFO",
       log_file: Optional[str] = None,
       json_format: bool = False
   ) -> None:
       """Configure application-wide logging."""
       # Implementation here
       pass
   ```

2. **Remove all `logging.basicConfig()` calls:**
   - [`src/orchestrator.py`](src/orchestrator.py:13)
   - [`src/database/connection.py`](src/database/connection.py:16)
   - [`src/load_env.py`](src/load_env.py:6)
   - Other modules

3. **Replace all `print()` with `logger` calls:**
   - [`src/publishers/twitter_publisher.py`](src/publishers/twitter_publisher.py:259-263)
   - [`src/fetchers/congress_fetcher.py`](src/fetchers/congress_fetcher.py:468-480)
   - Test files

4. **Remove credential logging:**
   - [`src/orchestrator.py`](src/orchestrator.py:42-46) - Remove entirely
   - [`src/publishers/twitter_publisher.py`](src/publishers/twitter_publisher.py:36-40) - Remove

5. **Add structured logging (JSON format option)**

**Verification:**
- [ ] Centralized logging configured
- [ ] No `logging.basicConfig()` calls
- [ ] No `print()` statements in production code
- [ ] No credential logging
- [ ] Consistent log format across application
- [ ] Log levels appropriate

**Dependencies:** Task 2.4  
**Blocks:** Task 3.5 (Monitoring)

---

### Task 2.7: Fix Environment Loading
**Priority:** HIGH  
**Effort:** 2-3 hours  
**Owner:** Backend Developer  
**Mode:** Code Mode

**Steps:**
1. **Remove duplicate `load_dotenv()` calls:**
   - [`src/publishers/twitter_publisher.py`](src/publishers/twitter_publisher.py:19)
   - [`src/processors/summarizer.py`](src/processors/summarizer.py:17)
   - [`src/fetchers/congress_fetcher.py`](src/fetchers/congress_fetcher.py:19)

2. **Use only [`src/load_env.py`](src/load_env.py:9) for loading:**
   - Load once at application startup
   - Import and call `load_env()` only in entry points

3. **Update entry points:**
   - [`app.py`](app.py:14-15) - Already correct
   - [`src/orchestrator.py`](src/orchestrator.py:1) - Add load_env() call
   - Test files - Add load_env() in setup

4. **Document environment loading strategy in README**

**Verification:**
- [ ] Only one load_env() call per process
- [ ] No duplicate dotenv loading
- [ ] All modules access environment correctly
- [ ] Tests work with new loading strategy

**Dependencies:** Task 2.4  
**Blocks:** None

---

### Task 2.8: Add Input Validation
**Priority:** HIGH  
**Effort:** 4-5 hours  
**Owner:** Backend Developer  
**Mode:** Code Mode

**Steps:**
1. **Install validation library:**
   ```bash
   pip install pydantic
   # Add to requirements.txt
   ```

2. **Create validation schemas:**
   ```python
   # src/schemas.py
   from pydantic import BaseModel, Field, validator
   from typing import Optional, Literal
   
   class VoteRequest(BaseModel):
       bill_id: str = Field(..., min_length=1)
       vote_type: Literal["yes", "no", "unsure"]
       previous_vote: Optional[Literal["yes", "no", "unsure"]] = None
       
       @validator('bill_id')
       def validate_bill_id(cls, v):
           # Validation logic
           return v
   ```

3. **Add validation to API endpoints:**
   - [`app.py`](app.py:225-241) - `/api/vote` endpoint

4. **Validate environment variables:**
   - In `Config.validate()` method

5. **Validate external API responses:**
   - [`src/fetchers/congress_fetcher.py`](src/fetchers/congress_fetcher.py:1)

**Verification:**
- [ ] Pydantic installed
- [ ] Validation schemas created
- [ ] API endpoints validate input
- [ ] Environment variables validated
- [ ] External API responses validated
- [ ] Tests cover validation errors

**Dependencies:** Task 2.4  
**Blocks:** None

---

## 🟡 Phase 3: Medium Priority Improvements (Weeks 2-3)

### Task 3.1: Add Health Check Endpoints
**Priority:** MEDIUM  
**Effort:** 2-3 hours  
**Owner:** Backend Developer  
**Mode:** Code Mode

**Steps:**
1. **Add health check endpoints to [`app.py`](app.py:1):**
   ```python
   @app.route('/health')
   def health():
       """Basic health check."""
       return jsonify({"status": "healthy"}), 200
   
   @app.route('/ready')
   def ready():
       """Readiness check including dependencies."""
       checks = {
           "database": check_database(),
           "congress_api": check_congress_api(),
           "anthropic_api": check_anthropic_api()
       }
       all_ready = all(checks.values())
       status_code = 200 if all_ready else 503
       return jsonify({"ready": all_ready, "checks": checks}), status_code
   ```

2. **Implement dependency checks:**
   - Database connectivity
   - External API availability

3. **Add to deployment documentation**

**Verification:**
- [ ] `/health` endpoint returns 200
- [ ] `/ready` endpoint checks dependencies
- [ ] Endpoints documented
- [ ] Used in deployment/monitoring

**Dependencies:** Task 2.6  
**Blocks:** Task 3.5 (Monitoring)

---

### Task 3.2: Implement Connection Pooling
**Priority:** MEDIUM  
**Effort:** 3-4 hours  
**Owner:** Backend Developer  
**Mode:** Code Mode

**Steps:**
1. **Update [`src/database/connection.py`](src/database/connection.py:1):**
   ```python
   from psycopg2 import pool
   
   # Create connection pool
   connection_pool = None
   
   def init_connection_pool(minconn=1, maxconn=10):
       global connection_pool
       conn_string = get_connection_string()
       connection_pool = pool.ThreadedConnectionPool(
           minconn, maxconn, conn_string
       )
   
   @contextmanager
   def postgres_connect():
       conn = connection_pool.getconn()
       try:
           yield conn
           conn.commit()
       except Exception:
           conn.rollback()
           raise
       finally:
           connection_pool.putconn(conn)
   ```

2. **Initialize pool at application startup:**
   - [`app.py`](app.py:1)
   - [`src/orchestrator.py`](src/orchestrator.py:1)

3. **Add pool monitoring**

**Verification:**
- [ ] Connection pool implemented
- [ ] Pool initialized at startup
- [ ] Connections properly returned to pool
- [ ] Performance improved
- [ ] No connection leaks

**Dependencies:** Task 2.4  
**Blocks:** None

---

### Task 3.3: Add Rate Limiting
**Priority:** MEDIUM  
**Effort:** 2-3 hours  
**Owner:** Backend Developer  
**Mode:** Code Mode

**Steps:**
1. **Install Flask-Limiter:**
   ```bash
   pip install Flask-Limiter
   # Add to requirements.txt
   ```

2. **Configure rate limiting in [`app.py`](app.py:1):**
   ```python
   from flask_limiter import Limiter
   from flask_limiter.util import get_remote_address
   
   limiter = Limiter(
       app=app,
       key_func=get_remote_address,
       default_limits=["200 per day", "50 per hour"]
   )
   
   @app.route('/api/vote', methods=['POST'])
   @limiter.limit("10 per minute")
   def record_vote():
       # Implementation
       pass
   ```

3. **Add rate limiting for external APIs:**
   - Congress.gov API
   - Anthropic API
   - Twitter API

**Verification:**
- [ ] Flask-Limiter installed
- [ ] Rate limits configured
- [ ] Endpoints protected
- [ ] External APIs rate limited
- [ ] Rate limit errors handled gracefully

**Dependencies:** Task 2.4  
**Blocks:** None

---

### Task 3.4: Consolidate Test Suite
**Priority:** MEDIUM  
**Effort:** 6-8 hours  
**Owner:** Backend Developer  
**Mode:** Code Mode

**Steps:**
1. **Organize tests by category:**
   - Unit tests
   - Integration tests
   - End-to-end tests

2. **Add missing test coverage:**
   - Error conditions
   - Edge cases
   - Configuration validation
   - API endpoints

3. **Add test fixtures and utilities:**
   ```python
   # tests/conftest.py
   import pytest
   
   @pytest.fixture
   def test_config():
       # Test configuration
       pass
   
   @pytest.fixture
   def test_db():
       # Test database
       pass
   ```

4. **Configure pytest:**
   ```ini
   # pytest.ini
   [pytest]
   testpaths = tests
   python_files = test_*.py
   python_classes = Test*
   python_functions = test_*
   ```

5. **Add coverage reporting:**
   ```bash
   pip install pytest-cov
   pytest --cov=src --cov-report=html
   ```

**Verification:**
- [ ] Tests organized
- [ ] Coverage > 80%
- [ ] All tests pass
- [ ] CI/CD runs tests
- [ ] Coverage report generated

**Dependencies:** Task 2.1  
**Blocks:** None

---

### Task 3.5: Add Monitoring and Alerting
**Priority:** MEDIUM  
**Effort:** 4-6 hours  
**Owner:** DevOps/Backend Developer  
**Mode:** Code Mode + Manual Configuration

**Steps:**
1. **Add Sentry for error tracking:**
   ```bash
   pip install sentry-sdk[flask]
   ```
   
   ```python
   # app.py
   import sentry_sdk
   from sentry_sdk.integrations.flask import FlaskIntegration
   
   sentry_sdk.init(
       dsn=config.SENTRY_DSN,
       integrations=[FlaskIntegration()],
       environment=config.FLASK_ENV
   )
   ```

2. **Add Prometheus metrics:**
   ```bash
   pip install prometheus-flask-exporter
   ```
   
   ```python
   from prometheus_flask_exporter import PrometheusMetrics
   metrics = PrometheusMetrics(app)
   ```

3. **Configure alerts:**
   - Critical errors
   - API failures
   - Database issues
   - Performance degradation

4. **Create dashboards:**
   - Application metrics
   - Error rates
   - API usage
   - Database performance

**Verification:**
- [ ] Sentry configured
- [ ] Errors tracked
- [ ] Metrics exposed
- [ ] Alerts configured
- [ ] Dashboards created

**Dependencies:** Task 2.6, Task 3.1  
**Blocks:** None

---

### Task 3.6: Improve CI/CD Workflows
**Priority:** MEDIUM  
**Effort:** 3-4 hours  
**Owner:** DevOps  
**Mode:** Code Mode

**Steps:**
1. **Create test workflow:**
   ```yaml
   # .github/workflows/test.yml
   name: Tests
   on: [push, pull_request]
   jobs:
     test:
       runs-on: ubuntu-latest
       steps:
         - uses: actions/checkout@v4
         - name: Run tests
           run: pytest
   ```

2. **Create linting workflow:**
   ```yaml
   # .github/workflows/lint.yml
   name: Lint
   on: [push, pull_request]
   jobs:
     lint:
       runs-on: ubuntu-latest
       steps:
         - uses: actions/checkout@v4
         - name: Run linters
           run: |
             black --check .
             flake8 .
             mypy .
   ```

3. **Add security scanning:**
   ```yaml
   # .github/workflows/security.yml
   name: Security Scan
   on: [push, pull_request]
   jobs:
     security:
       runs-on: ubuntu-latest
       steps:
         - uses: actions/checkout@v4
         - name: Run safety check
           run: safety check
   ```

4. **Fix existing workflows:**
   - Use GitHub Secrets properly
   - Separate test and production
   - Add proper error handling

**Verification:**
- [ ] Test workflow runs on PR
- [ ] Linting workflow runs on PR
- [ ] Security scanning runs
- [ ] Existing workflows fixed
- [ ] All workflows pass

**Dependencies:** Task 1.1, Task 3.4  
**Blocks:** None

---

### Task 3.7: Add Documentation
**Priority:** MEDIUM  
**Effort:** 6-8 hours  
**Owner:** Technical Writer/Developer  
**Mode:** Architect Mode

**Steps:**
1. **Create API documentation:**
   - Use OpenAPI/Swagger
   - Document all endpoints
   - Add examples

2. **Create architecture documentation:**
   - System architecture diagram
   - Data flow diagrams
   - Component interactions

3. **Create deployment guide:**
   - Prerequisites
   - Installation steps
   - Configuration
   - Troubleshooting

4. **Update README.md:**
   - Current setup instructions
   - Development workflow
   - Testing instructions
   - Contributing guidelines

5. **Add inline documentation:**
   - Docstrings for all functions
   - Complex logic explanations
   - Configuration options

**Verification:**
- [ ] API documentation complete
- [ ] Architecture documented
- [ ] Deployment guide created
- [ ] README updated
- [ ] Inline docs added

**Dependencies:** None  
**Blocks:** None

---

## 🟢 Phase 4: Low Priority Improvements (Month 2)

### Task 4.1: Code Style and Formatting
**Priority:** LOW  
**Effort:** 2-3 hours  
**Owner:** Backend Developer  
**Mode:** Code Mode

**Steps:**
1. **Install code formatters:**
   ```bash
   pip install black isort flake8 mypy
   ```

2. **Configure tools:**
   ```toml
   # pyproject.toml
   [tool.black]
   line-length = 100
   target-version = ['py310']
   
   [tool.isort]
   profile = "black"
   line_length = 100
   
   [tool.mypy]
   python_version = "3.10"
   warn_return_any = true
   warn_unused_configs = true
   ```

3. **Format entire codebase:**
   ```bash
   black .
   isort .
   ```

4. **Add pre-commit hooks:**
   ```yaml
   # .pre-commit-config.yaml
   repos:
     - repo: https://github.com/psf/black
       rev: 23.3.0
       hooks:
         - id: black
     - repo: https://github.com/pycqa/isort
       rev: 5.12.0
       hooks:
         - id: isort
   ```

**Verification:**
- [ ] Tools installed
- [ ] Configuration added
- [ ] Codebase formatted
- [ ] Pre-commit hooks working
- [ ] CI checks formatting

**Dependencies:** None  
**Blocks:** None

---

### Task 4.2: Dependency Management
**Priority:** LOW  
**Effort:** 2-3 hours  
**Owner:** Backend Developer  
**Mode:** Code Mode

**Steps:**
1. **Audit dependencies:**
   ```bash
   pip list --outdated
   safety check
   ```

2. **Remove unused dependencies:**
   - `feedparser` (if not used)
   - `flask-cors` (if not configured)
   - `pdfminer.six` (if not used)

3. **Create separate requirements files:**
   ```
   requirements.txt          # Production
   requirements-dev.txt      # Development
   requirements-test.txt     # Testing
   ```

4. **Pin all versions exactly:**
   ```
   requests==2.31.0
   httpx==0.27.0  # Not httpx<0.28
   ```

5. **Add dependency scanning:**
   - Dependabot
   - Safety CI

**Verification:**
- [ ] Dependencies audited
- [ ] Unused dependencies removed
- [ ] Requirements files separated
- [ ] All versions pinned
- [ ] Dependency scanning configured

**Dependencies:** None  
**Blocks:** None

---

### Task 4.3: Static File Optimization
**Priority:** LOW  
**Effort:** 1-2 hours  
**Owner:** Frontend Developer  
**Mode:** Code Mode

**Steps:**
1. **Choose one format per image:**
   - Remove duplicate [`creator.jpg`](static/img/creator.jpg) or [`creator.svg`](static/img/creator.svg)

2. **Optimize images:**
   ```bash
   # Use imagemin or similar
   ```

3. **Minify CSS/JS:**
   ```bash
   # Use webpack or similar
   ```

4. **Add asset versioning:**
   ```python
   # Use Flask-Assets or similar
   ```

**Verification:**
- [ ] No duplicate images
- [ ] Images optimized
- [ ] CSS/JS minified
- [ ] Asset versioning working

**Dependencies:** None  
**Blocks:** None

---

### Task 4.4: Template Improvements
**Priority:** LOW  
**Effort:** 3-4 hours  
**Owner:** Frontend Developer  
**Mode:** Code Mode

**Steps:**
1. **Add CSRF protection:**
   ```bash
   pip install Flask-WTF
   ```
   
   ```python
   from flask_wtf.csrf import CSRFProtect
   csrf = CSRFProtect(app)
   ```

2. **Add SEO meta tags:**
   ```html
   <meta name="description" content="...">
   <meta name="keywords" content="...">
   ```

3. **Add Open Graph tags:**
   ```html
   <meta property="og:title" content="...">
   <meta property="og:description" content="...">
   <meta property="og:image" content="...">
   ```

4. **Add structured data:**
   ```html
   <script type="application/ld+json">
   {
     "@context": "https://schema.org",
     "@type": "WebSite",
     "name": "TeenCivics"
   }
   </script>
   ```

**Verification:**
- [ ] CSRF protection working
- [ ] SEO meta tags added
- [ ] Open Graph tags added
- [ ] Structured data added
- [ ] Validated with tools

**Dependencies:** None  
**Blocks:** None

---

### Task 4.5: Update .env.example
**Priority:** LOW  
**Effort:** 30 minutes  
**Owner:** Backend Developer  
**Mode:** Code Mode

**Steps:**
1. **Update