# Code Style and Conventions

## Python Code Style (PEP 8 + Project Enhancements)

### Line and File Limits
- Line length: 100 characters maximum (enforced by Ruff)
- Maximum file length: 500 lines
- Maximum function length: 50 lines  
- Maximum class length: 100 lines
- Maximum cyclomatic complexity: 10

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
- Minimum coverage: 80% (critical paths 100%)
- Use fixtures for setup/teardown
- Mock external dependencies
- Test both success and failure paths

### Security Requirements
- Never hardcode credentials
- Use parameterized queries (no SQL injection)
- Hash passwords with bcrypt
- Validate all inputs with Pydantic
- Use timezone-aware datetimes (datetime.now(UTC))

### Ruff Configuration (from pyproject.toml)
- Auto-fixes enabled
- Checks for: pycodestyle, pyflakes, isort, bugbear, comprehensions, naming, simplify
- Quote style: double quotes
- Indent: spaces

### Anti-Patterns to Avoid
- Abstractions with single implementations
- Premature optimization without measurements
- Features beyond requirements
- Frameworks when standard library suffices
- Complex solutions when simple ones work

### Progressive Complexity Rule
Start left, move right only when needed:
- Function → Class → Module → Package
- Dict → DataClass → Pydantic Model
- Direct Call → Callback → Event System
- Hardcoded → Config → Environment Variable