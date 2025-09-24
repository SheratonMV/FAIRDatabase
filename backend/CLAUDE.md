# CLAUDE.md - Python Backend Development Guide

This file provides comprehensive Python-specific guidance for the FAIRDatabase backend. It extends the root CLAUDE.md with backend-specific conventions and standards.

## 📋 Core Development Philosophy

**Start simple. Add complexity only when proven necessary.**

This backend guide follows and extends the project-wide philosophy from root CLAUDE.md:
- **KISS** - Keep It Simple, Stupid
- **YAGNI** - You Aren't Gonna Need It
- **DRY** - Don't Repeat Yourself (but duplication > wrong abstraction)
- **Single Responsibility** - Each module/class/function does ONE thing well
- **Fail Fast** - Detect and report errors immediately
- **Explicit Over Implicit** - Code should clearly express intent

### Python-Specific Principles (PEP 20)
- **Explicit is better than implicit**
- **Simple is better than complex**
- **Complex is better than complicated**
- **Flat is better than nested**
- **Readability counts**
- **Errors should never pass silently**
- **In the face of ambiguity, refuse the temptation to guess**
- **There should be one-- and preferably only one --obvious way to do it**

### Design Principles Priority
1. **Correctness** - Working code over elegant code
2. **Simplicity** - Start simple, add complexity only when proven necessary
3. **Security** - Never compromise on security
4. **Maintainability** - Code for the next developer (including future you)
5. **Testability** - If it's hard to test, it's poorly designed
6. **Performance** - Optimize only after profiling and measuring

### Progressive Complexity (Python Context)
Start left, move right only when needed:
```
Function → Class → Module → Package
Dict → DataClass → Pydantic Model → Domain Model
Direct Call → Callback → Event System
Hardcoded → Config → Environment Variable
Flask → Flask with extensions → FastAPI (if needed)
```

## 🐍 Python Standards & Conventions

### Code Style (PEP 8 + Enhancements)
```python
# Line length: 100 characters maximum (enforced by Ruff)
# Imports: Standard library → Third-party → Local (alphabetical within groups)
import os
import sys
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from flask import Flask, request, jsonify
from sqlalchemy.orm import Session

from config import config
from src.models.user import User
```

### Type Hints (PEP 484)
```python
# Always use type hints for function signatures
def process_user_data(
    user_id: int,
    data: Dict[str, Any],
    session: Optional[Session] = None
) -> Optional[User]:
    """Process and validate user data."""
    pass

# Use TypeAlias for complex types
from typing import TypeAlias

UserId: TypeAlias = int
UserData: TypeAlias = Dict[str, Any]
```

### Naming Conventions
- **Variables/Functions**: `snake_case`
- **Classes**: `PascalCase`
- **Constants**: `UPPER_SNAKE_CASE`
- **Private**: `_leading_underscore`
- **Name mangling**: `__double_leading_underscore` (avoid unless necessary)
- **Type aliases**: `PascalCase`
- **Enum members**: `UPPER_SNAKE_CASE`

### File Organization Limits
- **Maximum file length**: 500 lines
- **Maximum function length**: 50 lines
- **Maximum class length**: 100 lines
- **Maximum cyclomatic complexity**: 10
- **Maximum module imports**: 20

## 📁 Project Structure

```
backend/
├── CLAUDE.md                # This file
├── pyproject.toml          # Project configuration and dependencies
├── uv.lock                 # Lock file for reproducible builds
├── pytest.ini              # Pytest configuration
├── app.py                  # Flask application entry point
├── config.py               # Configuration settings
├── .venv/                 # Virtual environment (auto-created by uv)
│
├── src/                   # Main application package
│   ├── __init__.py
│   ├── auth/              # Authentication module
│   │   ├── __init__.py
│   │   ├── routes.py
│   │   ├── helpers.py
│   │   ├── decorators.py
│   │   └── form.py
│   │
│   ├── dashboard/         # Dashboard module
│   │   ├── __init__.py
│   │   ├── routes.py
│   │   └── helpers.py
│   │
│   ├── data/              # Data management module
│   │   ├── __init__.py
│   │   ├── routes.py
│   │   ├── helpers.py
│   │   └── form.py
│   │
│   ├── main/              # Main module
│   │   ├── __init__.py
│   │   ├── routes.py
│   │   └── helpers.py
│   │
│   ├── privacy/           # Privacy module
│   │   ├── __init__.py
│   │   ├── routes.py
│   │   ├── helpers.py
│   │   └── form.py
│   │
│   ├── anonymization/     # Anonymization module (NEW)
│   │   ├── __init__.py
│   │   ├── k_anonymity.py
│   │   ├── enforce_privacy.py
│   │   ├── normalized_entropy.py
│   │   ├── p_29.py
│   │   ├── t_closeness.py
│   │   ├── checks/        # Validation checks
│   │   └── utils/         # Helper utilities
│   │
│   ├── exceptions.py      # Custom exceptions
│   └── form_handler.py    # Form handling utilities
│
└── tests/                # Test suite
    ├── __init__.py
    ├── conftest.py      # Pytest fixtures
    └── test_*.py        # Test files
```

## 📝 Documentation Standards

### Google-Style Docstrings (Keep It Simple)
```python
def calculate_fair_score(
    data_quality: float,
    accessibility: float,
    interoperability: float,
    reusability: float,
    weights: Optional[Dict[str, float]] = None
) -> float:
    """
    Calculate FAIR compliance score for a dataset.

    Args:
        data_quality: Quality score from 0.0 to 1.0.
        accessibility: Accessibility score from 0.0 to 1.0.
        interoperability: Interoperability score from 0.0 to 1.0.
        reusability: Reusability score from 0.0 to 1.0.
        weights: Optional weight dictionary for each component.

    Returns:
        Weighted FAIR score between 0.0 and 1.0.

    Raises:
        ValueError: If any score is outside the 0.0-1.0 range.
    """
    # Implementation here
    pass
```


## 🧪 Testing Standards

### Test Structure
```python
# tests/test_user_service.py
import pytest
from unittest.mock import Mock, patch
from datetime import datetime, UTC

from src.services.user import UserService
from src.schemas.user import UserCreate


class TestUserService:
    """Test suite for UserService."""

    @pytest.fixture
    def service(self, mock_repository):
        """Provide UserService instance with mocked dependencies."""
        return UserService(repository=mock_repository)

    @pytest.fixture
    def valid_user_data(self):
        """Provide valid user creation data."""
        return UserCreate(
            email="test@example.com",
            username="testuser",
            full_name="Test User"
        )

    def test_create_user_success(self, service, valid_user_data):
        """Test successful user creation."""
        # Arrange
        expected_id = 123

        # Act
        user = service.create_user(valid_user_data)

        # Assert
        assert user.id == expected_id
        assert user.email == valid_user_data.email

    @pytest.mark.parametrize("invalid_email", [
        "notanemail",
        "@example.com",
        "user@",
        "",
        None
    ])
    def test_create_user_invalid_email(self, service, invalid_email):
        """Test various invalid email formats."""
        with pytest.raises(ValueError, match="Invalid email"):
            service.create_user(invalid_email)
```

### Testing Requirements
- **Minimum coverage**: 80% (critical paths 100%)
- **Test categories**:
  - Unit tests (isolated components)
  - Integration tests (component interactions)
  - End-to-end tests (complete workflows)
- **Test naming**: `test_<what>_<condition>_<expected_result>`
- **Use fixtures** for setup and teardown
- **Mock external dependencies** appropriately
- **Test both success and failure paths**

## 🔐 Security Implementation

### Authentication & Authorization (Simple & Secure)
```python
from passlib.context import CryptContext
from datetime import datetime, timedelta, UTC
import secrets

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    """Hash password using bcrypt with automatic salt."""
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against hash."""
    return pwd_context.verify(plain_password, hashed_password)

# Secure random tokens
def generate_reset_token(length: int = 32) -> str:
    """Generate cryptographically secure random token."""
    return secrets.token_urlsafe(length)
```

### SQL Injection Prevention
```python
from sqlalchemy import text
from sqlalchemy.orm import Session

# ❌ NEVER do this - vulnerable to SQL injection
def get_user_unsafe(db: Session, username: str):
    query = f"SELECT * FROM users WHERE username = '{username}'"
    return db.execute(text(query))

# ✅ Use parameterized queries
def get_user_safe(db: Session, username: str):
    query = text("SELECT * FROM users WHERE username = :username")
    return db.execute(query, {"username": username})

# ✅ Better: Use ORM queries
def get_user_orm(db: Session, username: str):
    return db.query(User).filter(User.username == username).first()
```

### Input Validation
```python
from pydantic import BaseModel, Field, EmailStr, validator
from typing import Optional
import re

class UserCreate(BaseModel):
    """User creation schema with comprehensive validation."""

    email: EmailStr
    username: str = Field(
        ...,
        min_length=3,
        max_length=50,
        regex="^[a-zA-Z0-9_-]+$"
    )
    password: str = Field(..., min_length=8, max_length=100)
    full_name: Optional[str] = Field(None, max_length=100)

    @validator("password")
    def validate_password_strength(cls, v):
        """Ensure password meets security requirements."""
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain uppercase letter")
        if not re.search(r"[a-z]", v):
            raise ValueError("Password must contain lowercase letter")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain digit")
        if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", v):
            raise ValueError("Password must contain special character")
        return v

    @validator("username")
    def validate_username_reserved(cls, v):
        """Check username against reserved words."""
        RESERVED = {"admin", "root", "api", "system"}
        if v.lower() in RESERVED:
            raise ValueError(f"Username '{v}' is reserved")
        return v
```

## 🚨 Error Handling & Logging

### Custom Exceptions
```python
# app/core/exceptions.py
class FAIRDatabaseError(Exception):
    """Base exception for all application errors."""
    pass

class ValidationError(FAIRDatabaseError):
    """Raised when validation fails."""
    def __init__(self, field: str, message: str):
        self.field = field
        self.message = message
        super().__init__(f"{field}: {message}")

class AuthenticationError(FAIRDatabaseError):
    """Raised when authentication fails."""
    pass

class AuthorizationError(FAIRDatabaseError):
    """Raised when user lacks required permissions."""
    pass

class ResourceNotFoundError(FAIRDatabaseError):
    """Raised when requested resource doesn't exist."""
    def __init__(self, resource_type: str, resource_id: Any):
        self.resource_type = resource_type
        self.resource_id = resource_id
        super().__init__(f"{resource_type} with id {resource_id} not found")
```

### Structured Logging
```python
import logging
import structlog
from typing import Any, Dict

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()

# Usage examples
def process_dataset(dataset_id: int, user_id: int) -> Dict[str, Any]:
    """Process dataset with structured logging."""
    log = logger.bind(dataset_id=dataset_id, user_id=user_id)

    try:
        log.info("dataset_processing_started")

        # Processing logic here
        result = perform_processing()

        log.info(
            "dataset_processing_completed",
            duration=result.duration,
            records_processed=result.count
        )
        return result

    except ValidationError as e:
        log.warning(
            "dataset_validation_failed",
            error=str(e),
            field=e.field
        )
        raise

    except Exception as e:
        log.error(
            "dataset_processing_error",
            error=str(e),
            exc_info=True
        )
        raise
```

### Error Response Handling
```python
from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError
) -> JSONResponse:
    """Handle validation errors with consistent format."""
    errors = []
    for error in exc.errors():
        errors.append({
            "field": ".".join(str(loc) for loc in error["loc"]),
            "message": error["msg"],
            "type": error["type"]
        })

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "Validation Error",
            "details": errors,
            "timestamp": datetime.now(UTC).isoformat()
        }
    )

async def fair_database_exception_handler(
    request: Request,
    exc: FAIRDatabaseError
) -> JSONResponse:
    """Handle application-specific errors."""
    status_code = status.HTTP_400_BAD_REQUEST

    if isinstance(exc, ResourceNotFoundError):
        status_code = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, AuthenticationError):
        status_code = status.HTTP_401_UNAUTHORIZED
    elif isinstance(exc, AuthorizationError):
        status_code = status.HTTP_403_FORBIDDEN

    return JSONResponse(
        status_code=status_code,
        content={
            "error": exc.__class__.__name__,
            "message": str(exc),
            "timestamp": datetime.now(UTC).isoformat()
        }
    )
```

## 🔍 Search & Analysis Guidelines

### CRITICAL: Use Appropriate Tools
```bash
# Use grep with appropriate flags for better results
grep -r "pattern" .       # Recursive search
grep -l "pattern" *.py    # List matching files

# Find files efficiently
find . -name "*.py"       # Find Python files
```

**Note**: While grep is available, consider using IDE search features or language-specific tools when appropriate for better performance and functionality.

## 🗄️ Database Standards

### SQLAlchemy Models
```python
from sqlalchemy import Column, String, DateTime, Boolean, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, declarative_base
from datetime import datetime, UTC
import uuid

Base = declarative_base()

class TimestampMixin:
    """Mixin for automatic timestamp management."""
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC)
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC)
    )

class User(Base, TimestampMixin):
    """User model following database naming conventions."""
    __tablename__ = "users"

    # Primary key with entity-specific naming
    user_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )

    # User fields
    email = Column(String(255), unique=True, nullable=False, index=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)

    # Status fields
    is_active = Column(Boolean, default=True, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)

    # Relationships
    datasets = relationship("Dataset", back_populates="owner")

    def __repr__(self):
        return f"<User(user_id={self.user_id}, username={self.username})>"
```

### Database Naming Conventions
- **Tables**: Plural, snake_case (`users`, `datasets`, `access_logs`)
- **Primary Keys**: `{entity}_id` (`user_id`, `dataset_id`)
- **Foreign Keys**: `{referenced_entity}_id` (`owner_user_id`)
- **Timestamps**: `{action}_at` (`created_at`, `verified_at`)
- **Booleans**: `is_{state}` or `has_{property}` (`is_active`, `has_metadata`)
- **Counts**: `{entity}_count` (`download_count`)

### Repository Pattern
```python
from typing import Generic, TypeVar, Optional, List
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

T = TypeVar("T")

class BaseRepository(Generic[T]):
    """Base repository with common CRUD operations."""

    def __init__(self, model: T, db: Session):
        self.model = model
        self.db = db

    def get(self, id: Any) -> Optional[T]:
        """Get entity by primary key."""
        return self.db.query(self.model).filter(
            self.model.id == id
        ).first()

    def get_multi(
        self,
        skip: int = 0,
        limit: int = 100
    ) -> List[T]:
        """Get multiple entities with pagination."""
        return self.db.query(self.model).offset(skip).limit(limit).all()

    def create(self, obj_in: BaseModel) -> T:
        """Create new entity."""
        db_obj = self.model(**obj_in.dict())
        self.db.add(db_obj)
        try:
            self.db.commit()
            self.db.refresh(db_obj)
            return db_obj
        except IntegrityError as e:
            self.db.rollback()
            raise ValueError(f"Integrity error: {e}")

    def update(self, id: Any, obj_in: BaseModel) -> Optional[T]:
        """Update existing entity."""
        db_obj = self.get(id)
        if not db_obj:
            return None

        for field, value in obj_in.dict(exclude_unset=True).items():
            setattr(db_obj, field, value)

        self.db.commit()
        self.db.refresh(db_obj)
        return db_obj

    def delete(self, id: Any) -> bool:
        """Delete entity by primary key."""
        db_obj = self.get(id)
        if not db_obj:
            return False

        self.db.delete(db_obj)
        self.db.commit()
        return True
```

## 🛠️ Development Environment

### Package Management with UV (Exclusive)
```bash
# IMPORTANT: Use UV exclusively with pyproject.toml - NEVER use pip directly

# Install UV (if not installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Sync all dependencies (including dev)
uv sync --all-groups

# Sync only production dependencies
uv sync

# Add production dependencies
uv add fastapi pydantic sqlalchemy

# Add development dependencies
uv add --group dev pytest pytest-cov ruff mypy

# Remove dependencies
uv remove package-name

# Update all dependencies
uv sync --upgrade

# List installed packages
uv pip list

# Run commands in virtual environment
uv run python app.py
uv run pytest
uv run ruff check .
uv run mypy src/

# Or activate venv and run directly
source .venv/bin/activate
python app.py
pytest
ruff check .
```

**Project Structure**:
- `pyproject.toml` - Project configuration and dependencies
- `uv.lock` - Lock file for reproducible builds (auto-generated, don't edit)
- `.venv/` - Virtual environment (auto-created by uv)

### Environment Variables
```python
# app/core/config.py
from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Optional

class Settings(BaseSettings):
    """Application settings with validation."""

    # Application
    APP_NAME: str = "FAIRDatabase"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # API
    API_V1_PREFIX: str = "/api/v1"

    # Security
    SECRET_KEY: str  # Required, no default
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # Database
    DATABASE_URL: str  # Required
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20

    # Redis (optional)
    REDIS_URL: Optional[str] = None

    # CORS
    BACKEND_CORS_ORIGINS: list[str] = []

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True

@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()

settings = get_settings()
```


## ⚡ Performance Optimization

### Only Optimize When Needed
1. **Profile first**: Measure before optimizing
2. **Focus on bottlenecks**: 80/20 rule applies
3. **Simple caching**: Use `functools.lru_cache` for expensive computations
4. **Database queries**: Use eager loading only when N+1 is proven issue

```python
from functools import lru_cache

@lru_cache(maxsize=128)
def expensive_calculation(param: int) -> float:
    """Cache results of expensive calculations."""
    # Complex computation
    return result
```

## 📊 Monitoring & Observability

### Simple Health Checks
```python
from flask import Flask, jsonify

app = Flask(__name__)

@app.route("/health")
def health_check():
    """Basic health check endpoint."""
    return jsonify({"status": "healthy"})

@app.route("/ready")
def readiness_check():
    """Check if application is ready."""
    try:
        # Check database connection
        db.execute("SELECT 1")
        return jsonify({"status": "ready"})
    except Exception as e:
        return jsonify({"status": "not ready", "error": str(e)}), 503
```

## 📋 Development Checklist

### Before Starting Development
- [ ] Read root CLAUDE.md for project-wide conventions
- [ ] Understand the simplest solution first
- [ ] Check if feature already exists
- [ ] Question if the feature is needed (YAGNI)

### While Developing
- [ ] Start with the simplest working solution
- [ ] Add complexity only when proven necessary
- [ ] Follow PEP 8 and project conventions
- [ ] Add type hints to functions
- [ ] Write simple docstrings (no novels)
- [ ] Keep functions under 30 lines when possible
- [ ] Handle errors explicitly
- [ ] Validate inputs at boundaries

### Before Committing
- [ ] Run tests: `uv run pytest`
- [ ] Run linter: `uv run ruff check .`
- [ ] Format code: `uv run ruff format .`
- [ ] Type check: `uv run mypy src/` (if configured)
- [ ] Ensure no secrets in code
- [ ] Question: "Can this be simpler?"

### Security Checklist
- [ ] No hardcoded credentials
- [ ] Inputs validated with Pydantic
- [ ] SQL queries use parameterization
- [ ] Passwords hashed with bcrypt
- [ ] Authentication required for protected endpoints


## ⚠️ Common Pitfalls to Avoid

1. **Overengineering**
   ```python
   # ❌ Wrong - too complex for simple need
   class UserManagerFactoryInterface(ABC):
       @abstractmethod
       def create_user_service(self) -> UserServiceInterface:
           pass

   # ✅ Correct - simple and direct
   def create_user(username: str, email: str) -> User:
       return User(username=username, email=email)
   ```

2. **Premature Abstraction**
   ```python
   # ❌ Wrong - abstraction with single use
   class DataProcessor(ABC):
       @abstractmethod
       def process(self, data): pass

   class UserDataProcessor(DataProcessor):
       def process(self, data):
           return data.upper()

   # ✅ Correct - direct implementation
   def process_user_data(data: str) -> str:
       return data.upper()
   ```

3. **Always use timezone-aware datetimes**
   ```python
   # ❌ Wrong
   from datetime import datetime
   now = datetime.now()

   # ✅ Correct
   from datetime import datetime, UTC
   now = datetime.now(UTC)
   ```

## 📚 References & Resources

### Essential Documentation
- [PEP 8 - Style Guide](https://pep8.org/)
- [PEP 20 - The Zen of Python](https://www.python.org/dev/peps/pep-0020/)
- [Flask Documentation](https://flask.palletsprojects.com/)
- [SQLAlchemy Documentation](https://docs.sqlalchemy.org/)
- [Pytest Documentation](https://docs.pytest.org/)

---

**Remember**: Start simple. Add complexity only when proven necessary. The best code is code that doesn't exist. The second best is simple code that works.