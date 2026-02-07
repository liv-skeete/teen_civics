# Contributing to TeenCivics

Thank you for your interest in contributing to TeenCivics! This document provides guidelines and instructions for contributing to the project.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Code Style Guidelines](#code-style-guidelines)
- [Testing Guidelines](#testing-guidelines)
- [Pull Request Process](#pull-request-process)
- [Code Review Checklist](#code-review-checklist)
- [Reporting Bugs](#reporting-bugs)
- [Suggesting Enhancements](#suggesting-enhancements)

## Code of Conduct

This project and everyone participating in it is governed by the [TeenCivics Code of Conduct](CODE_OF_CONDUCT.md). By participating, you are expected to uphold this code. Please report unacceptable behavior to liv@di.st.

## Getting Started

1. **Fork the repository** on GitHub
2. **Clone your fork** locally:
   ```bash
   git clone https://github.com/YOUR_USERNAME/teen_civics.git
   cd teen_civics
   ```
3. **Add the upstream repository**:
   ```bash
   git remote add upstream https://github.com/liv-skeete/teen_civics.git
   ```

## Development Setup

### Prerequisites

- Python 3.8 or higher
- PostgreSQL database (or use SQLite for local development)
- API keys for Congress.gov, Venice.ai (for AI summarization), and Twitter

### Installation

1. **Create a virtual environment**:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

2. **Install dependencies**:
   ```bash
   # Production dependencies
   pip install -r requirements.txt
   
   # Development dependencies (includes testing and linting tools)
   pip install -r requirements-dev.txt
   ```

3. **Set up environment variables**:
   ```bash
   cp .env.example .env
   # Edit .env with your API keys and configuration
   ```

4. **Initialize the database**:
   ```bash
   python scripts/migrate_to_postgresql.py
   ```

### Running the Application

```bash
# Run the web application
python app.py

# Run the orchestrator (processes and posts bills)
python src/orchestrator.py
```

## Code Style Guidelines

### Python Style

We follow [PEP 8](https://pep8.org/) style guidelines with some modifications:

- **Line length**: Maximum 100 characters (not 79)
- **Indentation**: 4 spaces (no tabs)
- **Imports**: Organized in three groups (standard library, third-party, local)
- **Docstrings**: Use Google-style docstrings for all public functions and classes

### Code Formatting

We use **Black** for automatic code formatting:

```bash
# Format all Python files
black src/ tests/

# Check formatting without making changes
black --check src/ tests/
```

### Linting

We use **flake8** for linting:

```bash
# Run linter
flake8 src/ tests/

# Configuration is in .flake8 or setup.cfg
```

### Type Hints

We use **mypy** for static type checking:

```bash
# Run type checker
mypy src/

# Add type hints to all new functions
def process_bill(bill_id: str) -> dict[str, Any]:
    ...
```

### Import Organization

Organize imports in this order:

```python
# Standard library imports
import os
import sys
from typing import Optional

# Third-party imports
import requests
from anthropic import Anthropic

# Local imports
from src.config import get_config
from src.database.connection import get_db_connection
```

### Naming Conventions

- **Functions and variables**: `snake_case`
- **Classes**: `PascalCase`
- **Constants**: `UPPER_SNAKE_CASE`
- **Private methods**: `_leading_underscore`

### Documentation

- Add docstrings to all public functions, classes, and modules
- Use Google-style docstrings:

```python
def fetch_bill(bill_id: str, api_key: str) -> dict[str, Any]:
    """
    Fetch bill data from Congress.gov API.
    
    Args:
        bill_id: The bill identifier (e.g., "hr1234-118")
        api_key: Congress.gov API key
        
    Returns:
        Dictionary containing bill data
        
    Raises:
        requests.HTTPError: If the API request fails
        ValueError: If bill_id format is invalid
    """
    ...
```

## Testing Guidelines

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage report
pytest --cov=src --cov-report=html

# Run specific test file
pytest tests/test_orchestrator.py

# Run specific test function
pytest tests/test_orchestrator.py::test_duplicate_prevention
```

### Writing Tests

- Place tests in the [`tests/`](tests/) directory
- Name test files with `test_` prefix (e.g., `test_orchestrator.py`)
- Name test functions with `test_` prefix (e.g., `test_fetch_bill`)
- Use descriptive test names that explain what is being tested

Example test structure:

```python
import pytest
from src.orchestrator import process_bill

def test_process_bill_success():
    """Test that process_bill successfully processes a valid bill."""
    # Arrange
    bill_id = "hr1234-118"
    
    # Act
    result = process_bill(bill_id)
    
    # Assert
    assert result["success"] is True
    assert "summary" in result

def test_process_bill_invalid_id():
    """Test that process_bill raises ValueError for invalid bill ID."""
    with pytest.raises(ValueError):
        process_bill("invalid-id")
```

### Test Coverage

- Aim for at least 80% code coverage
- Focus on testing critical paths and edge cases
- Mock external API calls to avoid rate limits and ensure consistent tests

### Integration Tests

Integration tests are in [`tests/test_integration.py`](tests/test_integration.py). These tests:

- Test the full workflow from fetching to posting
- Use test database or mock database connections
- May be slower and should be marked with `@pytest.mark.integration`

## Pull Request Process

### Before Submitting

1. **Create a feature branch**:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes** following the code style guidelines

3. **Write or update tests** for your changes

4. **Run the test suite**:
   ```bash
   pytest
   ```

5. **Format your code**:
   ```bash
   black src/ tests/
   ```

6. **Run linters**:
   ```bash
   flake8 src/ tests/
   mypy src/
   ```

7. **Update documentation** if needed (README.md, docstrings, etc.)

8. **Commit your changes** with clear, descriptive commit messages:
   ```bash
   git commit -m "Add feature: brief description"
   ```

### Commit Message Guidelines

Use clear, descriptive commit messages:

- **Format**: `<type>: <description>`
- **Types**: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`
- **Examples**:
  - `feat: add bill filtering by date range`
  - `fix: correct database connection timeout issue`
  - `docs: update API documentation`
  - `test: add tests for summarizer edge cases`

### Submitting the Pull Request

1. **Push your branch** to your fork:
   ```bash
   git push origin feature/your-feature-name
   ```

2. **Open a Pull Request** on GitHub with:
   - Clear title describing the change
   - Detailed description of what changed and why
   - Reference to any related issues (e.g., "Fixes #123")
   - Screenshots if UI changes are involved

3. **Wait for review** and address any feedback

## Code Review Checklist

When reviewing code (or preparing your PR), check:

### Functionality
- [ ] Code works as intended and solves the stated problem
- [ ] Edge cases are handled appropriately
- [ ] No breaking changes to existing functionality

### Code Quality
- [ ] Code follows project style guidelines
- [ ] Code is readable and well-organized
- [ ] No unnecessary complexity
- [ ] Proper error handling is in place

### Testing
- [ ] New code has appropriate test coverage
- [ ] All tests pass
- [ ] Tests are clear and maintainable

### Documentation
- [ ] Code is properly documented with docstrings
- [ ] README or other docs updated if needed
- [ ] Comments explain "why" not "what"

### Security
- [ ] No sensitive data (API keys, passwords) in code
- [ ] Input validation is present where needed
- [ ] No SQL injection or other security vulnerabilities

### Performance
- [ ] No obvious performance issues
- [ ] Database queries are efficient
- [ ] API calls are properly rate-limited

## Reporting Bugs

When reporting bugs, please include:

1. **Clear title** describing the issue
2. **Steps to reproduce** the bug
3. **Expected behavior** vs actual behavior
4. **Environment details** (OS, Python version, etc.)
5. **Error messages** or logs if available
6. **Screenshots** if applicable

Use the [GitHub Issues](https://github.com/liv-skeete/teen_civics/issues) page to report bugs.

## Suggesting Enhancements

When suggesting enhancements:

1. **Check existing issues** to avoid duplicates
2. **Describe the enhancement** clearly
3. **Explain the use case** and benefits
4. **Provide examples** if possible
5. **Consider implementation** complexity

## Questions?

If you have questions about contributing:

- Open a [GitHub Discussion](https://github.com/liv-skeete/teen_civics/discussions)
- Check existing documentation in the repository
- Review closed issues and PRs for similar questions

Thank you for contributing to TeenCivics! 🎉