# Code Style and Conventions

## Python Code Style (PEP 8 + Project Enhancements)

### Line and File Limits
- Line length: 100 characters maximum (enforced by Ruff)
- Maximum file length: 500 lines
- Maximum function length: 50 lines  
- Maximum class length: 100 lines
- Maximum cyclomatic complexity: 10

### Python Version
- **Required**: Python >=3.13 (minimum version)
- Target version for tools: py313

### Import Order
Standard library → Third-party → Local (alphabetical within groups)
```python
import os
import sys
from datetime import datetime, timezone

from flask import Flask, request
from sqlalchemy.orm import Session

from config import config
from src.models.user import User
```

### Naming Conventions
- Variables/Functions: `snake_case`
- Classes: `PascalCase`
- Constants: `UPPER_SNAKE_CASE`
- Private: `_leading_underscore`
- Type aliases: `PascalCase`
- Enum members: `UPPER_SNAKE_CASE`

### Type Hints
Always use type hints for function signatures:
```python
def process_user_data(
    user_id: int,
    data: Dict[str, Any],
    session: Optional[Session] = None
) -> Optional[User]:
    """Process and validate user data."""
    pass
```

### Docstrings (Google Style - Keep Simple)
```python
def calculate_score(value: float, weight: float = 1.0) -> float:
    """
    Calculate weighted score.
    
    Args:
        value: Score value from 0.0 to 1.0.
        weight: Optional weight multiplier.
        
    Returns:
        Weighted score between 0.0 and 1.0.
        
    Raises:
        ValueError: If value is outside valid range.
    """
    pass
```

### Database Naming
- Tables: Plural, snake_case (`users`, `datasets`)
- Primary Keys: `{entity}_id` (`user_id`, `dataset_id`)
- Foreign Keys: `{referenced_entity}_id` (`owner_user_id`)
- Timestamps: `{action}_at` (`created_at`, `updated_at`)
- Booleans: `is_{state}` or `has_{property}` (`is_active`)
- Counts: `{entity}_count` (`download_count`)

### Testing Conventions
- Test naming: `test_<what>_<condition>_<expected_result>`
- Minimum coverage: 80% (enforced by pytest-cov)
- Use fixtures for setup/teardown
- Mock external dependencies
- Test both success and failure paths

#### Pytest Markers (from pyproject.toml)
```python
@pytest.mark.slow  # For slow-running tests (deselect with '-m "not slow"')
@pytest.mark.integration  # For integration tests
@pytest.mark.unit  # For unit tests
```

#### Coverage Configuration
- Source directory: `src/`
- Minimum coverage: 80% (--cov-fail-under=80)
- Reports: terminal, HTML, XML
- Excludes: tests/, migrations/, __pycache__/
- Ignored lines: pragma: no cover, if TYPE_CHECKING:, raise NotImplementedError, etc.

### Security Requirements
- Never hardcode credentials
- Use parameterized queries (no SQL injection)
- Use Supabase for authentication (NOT custom password hashing)
- Validate all inputs with custom handler classes
- Use timezone-aware datetimes (datetime.now(UTC))

### Ruff Configuration (from pyproject.toml)
- Line length: 100
- Target: Python 3.13
- Auto-fixes enabled
- Checks for: pycodestyle (E, W), pyflakes (F), isort (I), bugbear (B), comprehensions (C4), naming (N), pyupgrade (UP), simplify (SIM)
- Ignored: E501 (line too long - formatter handles), B008 (function calls in defaults), C901 (complexity)
- Quote style: double quotes
- Indent: spaces

### Mypy Configuration (from pyproject.toml)
- Python version: 3.13
- Strict mode features enabled:
  - warn_return_any
  - warn_unused_configs
  - disallow_untyped_defs
  - no_implicit_optional
  - warn_redundant_casts
  - warn_unused_ignores
  - warn_no_return
  - check_untyped_defs
  - strict_equality
- Ignore missing imports for: flask_cors, flask_limiter, supabase

### Anti-Patterns to Avoid
- Abstractions with single implementations
- Premature optimization without measurements
- Features beyond requirements
- Frameworks when standard library suffices
- Complex solutions when simple ones work

### Progressive Complexity Rule
Start left, move right only when needed:
- Function → Class → Module → Package
- Dict → DataClass → Custom Model (NOT Pydantic)
- Direct Call → Callback → Event System
- Hardcoded → Config → Environment Variable

## Testing Standards

### Test File Organization
```
tests/
├── conftest.py          # Shared fixtures
├── .env.test           # Test environment variables
├── auth/               # Auth module tests
├── dashboard/          # Dashboard module tests
├── data/               # Data module tests
├── main/               # Main module tests
└── privacy/            # Privacy module tests
```

### Test Coverage Requirements
- Overall: 80% minimum (enforced)
- Critical paths: 100% recommended
- Coverage reports: terminal, HTML, XML
- HTML report location: `htmlcov/index.html`

### Test Markers Usage
```bash
# Run all tests
uv run pytest

# Run only fast tests (skip slow)
uv run pytest -m "not slow"

# Run only integration tests
uv run pytest -m integration

# Run only unit tests
uv run pytest -m unit

# Run with coverage
uv run pytest --cov=src --cov-report=html
```

### Pytest Options (from pyproject.toml)
- Test discovery: `tests/` directory
- Python path: current directory
- Coverage fail threshold: 80%
- Strict markers enforcement
- Warning filters: error on warnings (except deprecation warnings)
- Ignored: AnonyBiome directory

## Code Quality Commands

### Linting
```bash
cd backend
uv run ruff check .         # Check for issues
uv run ruff check --fix .   # Auto-fix issues
```

### Formatting
```bash
cd backend
uv run ruff format .        # Format code
```

### Type Checking
```bash
cd backend
uv run mypy src/            # Type check source code
```

### Testing
```bash
cd backend
uv run pytest                           # Run all tests
uv run pytest -v                         # Verbose output
uv run pytest --cov=src                  # With coverage
uv run pytest --cov=src --cov-report=html  # With HTML report
```

## Development Workflow

### Before Committing
1. Format code: `uv run ruff format .`
2. Fix linting: `uv run ruff check --fix .`
3. Run tests: `uv run pytest`
4. Type check: `uv run mypy src/` (if applicable)
5. Ensure 80%+ coverage
6. No hardcoded secrets

### Continuous Integration Checks
All of the above should pass in CI:
- Ruff formatting check
- Ruff linting check
- Pytest with 80% coverage
- Mypy type checking (for typed modules)

## Important Notes
- **NEVER use pip directly** - Always use `uv` for package management
- Always work from the `backend/` directory for Python commands
- Follow progressive complexity: start simple, add complexity only when proven necessary
- All tests should pass before committing
- Coverage must be ≥80% or tests will fail