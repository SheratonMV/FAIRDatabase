# CLAUDE.md - Python Backend Development Guide

This file provides comprehensive Python-specific guidance for the FAIRDatabase backend. It extends the root CLAUDE.md with backend-specific conventions and standards.

## 📋 Core Development Philosophy

### Python Zen Principles (PEP 20)
- **Explicit is better than implicit**
- **Simple is better than complex**
- **Complex is better than complicated**
- **Flat is better than nested**
- **Readability counts**
- **Errors should never pass silently**
- **In the face of ambiguity, refuse the temptation to guess**
- **There should be one-- and preferably only one --obvious way to do it**

### Design Principles Priority
1. **Security First** - Never compromise on security, even for performance
2. **Correctness** - Working code over elegant code
3. **Maintainability** - Code for the next developer (including future you)
4. **Testability** - If it's hard to test, it's poorly designed
5. **Performance** - Optimize only after profiling and measuring

### SOLID Principles Applied
- **Single Responsibility**: Each module/class/function does ONE thing well
- **Open/Closed**: Extend through addition, not modification
- **Liskov Substitution**: Subtypes must be substitutable for base types
- **Interface Segregation**: Many specific interfaces over one general-purpose
- **Dependency Inversion**: Depend on abstractions, not concretions

## 🐍 Python Standards & Conventions

### Code Style (PEP 8 + Enhancements)
```python
# Line length: 100 characters maximum (enforced by Ruff)
# Imports: Standard library → Third-party → Local (alphabetical within groups)
import os
import sys
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

import pydantic
from fastapi import FastAPI, HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.user import User
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
├── .env.example           # Environment variables template
├── .env                   # Local environment (never commit)
├── .venv/                 # Virtual environment (auto-created by uv)
│
├── app/                   # Main application package
│   ├── __init__.py
│   ├── main.py           # FastAPI/Flask application entry point
│   │
│   ├── api/              # API endpoints
│   │   ├── __init__.py
│   │   ├── v1/           # API version 1
│   │   │   ├── __init__.py
│   │   │   ├── endpoints/
│   │   │   │   ├── users.py
│   │   │   │   └── auth.py
│   │   │   └── dependencies.py
│   │   └── health.py     # Health check endpoints
│   │
│   ├── core/             # Core functionality
│   │   ├── __init__.py
│   │   ├── config.py     # Settings management (Pydantic)
│   │   ├── security.py   # Security utilities
│   │   ├── database.py   # Database connection
│   │   └── exceptions.py # Custom exceptions
│   │
│   ├── models/           # Database models
│   │   ├── __init__.py
│   │   ├── base.py       # Base model class
│   │   ├── user.py
│   │   └── mixins.py     # Reusable model mixins
│   │
│   ├── schemas/          # Pydantic schemas
│   │   ├── __init__.py
│   │   ├── user.py
│   │   └── common.py     # Shared schemas
│   │
│   ├── services/         # Business logic
│   │   ├── __init__.py
│   │   ├── auth.py
│   │   └── user.py
│   │
│   └── utils/            # Utilities
│       ├── __init__.py
│       ├── validators.py
│       └── helpers.py
│
├── tests/                # Test suite (mirrors app structure)
│   ├── __init__.py
│   ├── conftest.py      # Pytest fixtures
│   ├── test_main.py
│   ├── api/
│   │   └── v1/
│   │       └── test_users.py
│   ├── services/
│   │   └── test_auth.py
│   └── utils/
│       └── test_validators.py
│
├── migrations/           # Database migrations (Alembic)
│   ├── alembic.ini
│   └── versions/
│
└── scripts/             # Utility scripts
    ├── init_db.py
    └── seed_data.py
```

## 📝 Documentation Standards

### Google-Style Docstrings
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
            Defaults to equal weighting if not provided.

    Returns:
        Weighted FAIR score between 0.0 and 1.0.

    Raises:
        ValueError: If any score is outside the 0.0-1.0 range.
        TypeError: If weights are provided but not as a dictionary.

    Example:
        >>> score = calculate_fair_score(0.8, 0.9, 0.7, 0.85)
        >>> print(f"FAIR Score: {score:.2%}")
        FAIR Score: 81.25%

    Note:
        This implementation follows the FAIR data principles as
        defined in https://www.go-fair.org/fair-principles/
    """
    # Implementation here
    pass
```

### Class Documentation
```python
class DatasetManager:
    """
    Manages FAIR dataset operations and metadata.

    This class provides a high-level interface for managing datasets
    according to FAIR principles, including metadata validation,
    access control, and provenance tracking.

    Attributes:
        repository: Database repository for dataset persistence.
        validator: FAIR compliance validator instance.
        cache: Optional caching layer for performance.

    Example:
        >>> manager = DatasetManager(repository=repo)
        >>> dataset = manager.create_dataset(metadata)
        >>> manager.validate_fair_compliance(dataset.id)
    """

    def __init__(
        self,
        repository: DatasetRepository,
        validator: Optional[FairValidator] = None,
        cache: Optional[CacheInterface] = None
    ):
        """
        Initialize the DatasetManager.

        Args:
            repository: Repository instance for data persistence.
            validator: Optional FAIR validator. Creates default if None.
            cache: Optional cache implementation for performance.
        """
        self.repository = repository
        self.validator = validator or FairValidator()
        self.cache = cache
```

## 🧪 Testing Standards

### Test Structure
```python
# tests/test_user_service.py
import pytest
from unittest.mock import Mock, patch
from datetime import datetime, UTC

from app.services.user import UserService
from app.schemas.user import UserCreate
from app.core.exceptions import UserNotFoundError


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

    def test_create_user_duplicate_email(self, service, valid_user_data):
        """Test that duplicate email raises appropriate error."""
        # Arrange
        service.repository.find_by_email.return_value = Mock()

        # Act & Assert
        with pytest.raises(ValueError, match="Email already exists"):
            service.create_user(valid_user_data)

    @pytest.mark.parametrize("invalid_email", [
        "notanemail",
        "@example.com",
        "user@",
        "",
        None
    ])
    def test_create_user_invalid_email(self, service, invalid_email):
        """Test various invalid email formats."""
        user_data = UserCreate(
            email=invalid_email,
            username="testuser"
        )

        with pytest.raises(ValueError, match="Invalid email"):
            service.create_user(user_data)
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

### Authentication & Authorization
```python
from passlib.context import CryptContext
from jose import JWTError, jwt
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

# JWT tokens
def create_access_token(
    data: Dict[str, Any],
    expires_delta: Optional[timedelta] = None
) -> str:
    """
    Create JWT access token with expiration.

    Security considerations:
    - Use strong secret key (min 256 bits)
    - Set reasonable expiration times
    - Include necessary claims only
    - Use HTTPS in production
    """
    to_encode = data.copy()
    expire = datetime.now(UTC) + (expires_delta or timedelta(minutes=15))
    to_encode.update({"exp": expire, "iat": datetime.now(UTC)})

    encoded_jwt = jwt.encode(
        to_encode,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM
    )
    return encoded_jwt

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
# ❌ NEVER use these:
grep -r "pattern" .
find . -name "*.py"

# ✅ ALWAYS use these instead:
rg "pattern"              # Use ripgrep
rg --files -g "*.py"     # Find files with ripgrep
```

**Note**: This mirrors the root CLAUDE.md guidance. Always use ripgrep (`rg`) instead of grep for better performance and functionality.

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

## 🎯 Pre-commit Hooks

### Configuration (.pre-commit-config.yaml)
```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.1.0
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format

  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.7.0
    hooks:
      - id: mypy
        additional_dependencies: [types-all]

  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.5.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-added-large-files
      - id: check-merge-conflict
      - id: detect-private-key

  - repo: https://github.com/python-poetry/poetry
    rev: 1.7.0
    hooks:
      - id: poetry-check
```

## ⚡ Performance Optimization

### Async/Await Best Practices
```python
import asyncio
from typing import List
import httpx

async def fetch_data(url: str) -> dict:
    """Fetch data asynchronously."""
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        return response.json()

async def fetch_multiple(urls: List[str]) -> List[dict]:
    """Fetch multiple URLs concurrently."""
    tasks = [fetch_data(url) for url in urls]
    return await asyncio.gather(*tasks)

# Database queries
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

async def get_users_async(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 100
) -> List[User]:
    """Get users with async database query."""
    stmt = select(User).offset(skip).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()
```

### Caching Strategy
```python
from functools import lru_cache, cache
from typing import Optional
import redis
import json

# In-memory caching for expensive computations
@lru_cache(maxsize=128)
def expensive_calculation(param: int) -> float:
    """Cache results of expensive calculations."""
    # Complex computation
    return result

# Redis caching for distributed systems
class RedisCache:
    """Redis-based caching implementation."""

    def __init__(self, redis_url: str):
        self.redis = redis.from_url(redis_url)

    def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        value = self.redis.get(key)
        return json.loads(value) if value else None

    def set(
        self,
        key: str,
        value: Any,
        expire: Optional[int] = None
    ) -> None:
        """Set value in cache with optional expiration."""
        self.redis.set(
            key,
            json.dumps(value),
            ex=expire
        )

    def delete(self, key: str) -> None:
        """Delete key from cache."""
        self.redis.delete(key)
```

## 📊 Monitoring & Observability

### Metrics Collection
```python
from prometheus_client import Counter, Histogram, Gauge
import time

# Define metrics
request_count = Counter(
    "app_requests_total",
    "Total number of requests",
    ["method", "endpoint", "status"]
)

request_duration = Histogram(
    "app_request_duration_seconds",
    "Request duration in seconds",
    ["method", "endpoint"]
)

active_users = Gauge(
    "app_active_users",
    "Number of active users"
)

# Use in middleware
async def metrics_middleware(request: Request, call_next):
    """Collect request metrics."""
    start_time = time.time()

    response = await call_next(request)

    duration = time.time() - start_time
    request_count.labels(
        method=request.method,
        endpoint=request.url.path,
        status=response.status_code
    ).inc()

    request_duration.labels(
        method=request.method,
        endpoint=request.url.path
    ).observe(duration)

    return response
```

## 🚀 Deployment Readiness

### Health Checks
```python
from fastapi import APIRouter, status
from sqlalchemy import text

router = APIRouter(tags=["health"])

@router.get("/health", status_code=status.HTTP_200_OK)
async def health_check():
    """Basic health check endpoint."""
    return {"status": "healthy"}

@router.get("/health/ready", status_code=status.HTTP_200_OK)
async def readiness_check(db: Session):
    """Check if application is ready to serve requests."""
    try:
        # Check database connection
        db.execute(text("SELECT 1"))

        # Check other critical dependencies
        # ...

        return {"status": "ready"}
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service not ready"
        )

@router.get("/health/live", status_code=status.HTTP_200_OK)
async def liveness_check():
    """Check if application is alive."""
    return {"status": "alive"}
```

## 📋 Development Checklist

### Before Starting Development
- [ ] Read root CLAUDE.md for project-wide conventions
- [ ] Check Python version compatibility (3.10+)
- [ ] Set up virtual environment with UV
- [ ] Configure `.env` from `.env.example`
- [ ] Install pre-commit hooks
- [ ] Run existing tests to ensure setup

### While Developing
- [ ] Follow PEP 8 and project conventions
- [ ] Add type hints to all functions
- [ ] Write Google-style docstrings
- [ ] Keep functions under 50 lines
- [ ] Keep files under 500 lines
- [ ] Handle errors explicitly
- [ ] Log important operations
- [ ] Validate all inputs

### Before Committing
- [ ] Write/update tests (minimum 80% coverage)
- [ ] Run test suite: `pytest` or `uv run pytest`
- [ ] Run linter: `ruff check .` or `uv run ruff check .`
- [ ] Format code: `ruff format .` or `uv run ruff format .`
- [ ] Type check: `mypy app/` or `uv run mypy app/`
- [ ] Update documentation if needed
- [ ] Ensure no secrets in code

### Security Checklist
- [ ] No hardcoded credentials
- [ ] All inputs validated with Pydantic
- [ ] SQL queries use parameterization
- [ ] Passwords hashed with bcrypt
- [ ] Authentication required for protected endpoints
- [ ] Rate limiting implemented
- [ ] CORS configured properly
- [ ] Sensitive data not logged

## 🔍 Debugging & Troubleshooting

### Debug Tools
```python
# Use ipdb for interactive debugging
import ipdb; ipdb.set_trace()

# Use rich for better tracebacks
from rich.traceback import install
install(show_locals=True)

# Profile performance
import cProfile
import pstats

def profile_function():
    """Profile function execution."""
    profiler = cProfile.Profile()
    profiler.enable()

    # Code to profile
    result = expensive_operation()

    profiler.disable()
    stats = pstats.Stats(profiler)
    stats.sort_stats('cumulative')
    stats.print_stats(10)

    return result
```

## ⚠️ Common Pitfalls to Avoid

1. **Never use mutable default arguments**
   ```python
   # ❌ Wrong
   def add_item(item, items=[]):
       items.append(item)
       return items

   # ✅ Correct
   def add_item(item, items=None):
       if items is None:
           items = []
       items.append(item)
       return items
   ```

2. **Always use timezone-aware datetimes**
   ```python
   # ❌ Wrong
   from datetime import datetime
   now = datetime.now()

   # ✅ Correct
   from datetime import datetime, UTC
   now = datetime.now(UTC)
   ```

3. **Don't catch all exceptions blindly**
   ```python
   # ❌ Wrong
   try:
       process_data()
   except:
       pass

   # ✅ Correct
   try:
       process_data()
   except ValidationError as e:
       logger.warning(f"Validation failed: {e}")
       raise
   ```

## 📚 References & Resources

### Essential Documentation
- [PEP 8 - Style Guide](https://pep8.org/)
- [PEP 484 - Type Hints](https://www.python.org/dev/peps/pep-0484/)
- [PEP 20 - The Zen of Python](https://www.python.org/dev/peps/pep-0020/)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [SQLAlchemy Documentation](https://docs.sqlalchemy.org/)
- [Pydantic Documentation](https://docs.pydantic.dev/)
- [Pytest Documentation](https://docs.pytest.org/)

### Security Resources
- [OWASP Python Security](https://owasp.org/www-project-top-ten/)
- [Python Security Best Practices](https://python.readthedocs.io/en/latest/library/security_warnings.html)
- [SQL Injection Prevention](https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html)

---

**Remember**: This document defines the gold standard for our Python backend. When in doubt, prioritize security, correctness, and maintainability over cleverness or premature optimization.