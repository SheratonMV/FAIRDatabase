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
Dict → DataClass → Custom Model
Direct Call → Callback → Event System
Hardcoded → Config → Environment Variable
Flask → Flask with extensions → Consider FastAPI (future)
```

## 🐍 Python Standards & Conventions

### Code Style (PEP 8 + Enhancements)
```python
# Line length: 100 characters maximum (enforced by Ruff)
# Imports: Standard library → Third-party → Local (alphabetical within groups)
import os
import sys
from datetime import datetime, timezone

from flask import Flask, request, jsonify, session
from supabase import Client

from config import Config, supabase_extension
from src.exceptions import GenericExceptionHandler
```

### Type Hints (PEP 484)
```python
# Use type hints for function signatures when helpful
from typing import Optional, Dict, Any

def process_user_data(
    user_id: str,
    data: Dict[str, Any],
    optional_param: Optional[str] = None
) -> Dict[str, Any]:
    """Process and validate user data."""
    pass
```

### Naming Conventions
- **Variables/Functions**: `snake_case`
- **Classes**: `PascalCase`
- **Constants**: `UPPER_SNAKE_CASE`
- **Private**: `_leading_underscore`
- **Blueprints**: `{module}_routes` (e.g., `auth_routes`, `data_routes`)
- **Templates**: `{module}/{action}.html` (e.g., `auth/login.html`)

### File Organization Limits
- **Maximum file length**: 500 lines
- **Maximum function length**: 50 lines
- **Maximum class length**: 100 lines
- **Maximum cyclomatic complexity**: 10

## 📁 Project Structure

```
backend/
├── CLAUDE.md                # This file
├── pyproject.toml          # Project configuration and dependencies
├── uv.lock                 # Lock file for reproducible builds
├── app.py                  # Flask application entry point
├── config.py               # Configuration settings
│
├── src/                   # Main application package
│   ├── __init__.py
│   │
│   ├── auth/              # Authentication module
│   │   ├── routes.py      # Blueprint and route handlers
│   │   ├── helpers.py     # Business logic utilities
│   │   └── form.py        # Form handler classes
│   │
│   ├── dashboard/         # Dashboard module
│   │   ├── routes.py
│   │   └── helpers.py
│   │
│   ├── data/              # Data management module
│   │   ├── routes.py
│   │   ├── helpers.py
│   │   └── form.py
│   │
│   ├── main/              # Main/home module
│   │   ├── routes.py
│   │   └── helpers.py
│   │
│   ├── privacy/           # Privacy module
│   │   ├── routes.py
│   │   ├── helpers.py
│   │   └── form.py
│   │
│   ├── anonymization/     # Data anonymization module
│   │   ├── k_anonymity.py
│   │   ├── enforce_privacy.py
│   │   ├── normalized_entropy.py
│   │   ├── p_29.py
│   │   ├── t_closeness.py
│   │   ├── checks/        # Validation checks
│   │   └── utils/         # Helper utilities
│   │
│   ├── exceptions.py      # Custom exception classes
│   └── form_handler.py    # Base form handler
│
└── tests/                # Test suite
    ├── conftest.py      # Pytest fixtures
    ├── .env.test       # Test environment variables
    └── */              # Module-specific tests
```

## 🔧 Technology Stack & Dependencies

### Current Dependencies (from pyproject.toml)

**Production:**
```toml
flask>=3.1.0              # Web framework
werkzeug>=3.1.3          # WSGI utilities
psycopg2-binary>=2.9.10  # PostgreSQL adapter
pandas>=2.2.3            # Data manipulation
sqlalchemy>=2.0.40       # SQL toolkit (used sparingly)
supabase>=2.15.1         # Backend-as-a-Service (Auth + DB)
flask-cors>=5.0.1        # CORS support
flask-limiter>=3.12      # Rate limiting
python-dotenv>=1.1.0     # Environment variable loading
```

**Development:**
```toml
pytest>=8.3.4            # Testing framework
pytest-cov>=6.0.0        # Coverage reporting
pytest-mock>=3.14.0      # Mocking utilities
pytest-asyncio>=0.25.2   # Async testing support
ruff>=0.9.2              # Linter and formatter
mypy>=1.14.1             # Type checker
ipython>=8.31.0          # Enhanced Python REPL
ipdb>=0.13.13            # IPython debugger
rich>=13.9.4             # Rich terminal formatting
httpx>=0.28.1            # HTTP client for testing
```

**Test-Only Dependencies:**
```toml
pytest>=8.3.4
pytest-cov>=6.0.0
pytest-mock>=3.14.0
pytest-asyncio>=0.25.2
httpx>=0.28.1
```

The project uses dependency groups (`[dependency-groups]`) rather than optional dependencies.

### Key Technology Choices

- **Flask** (not FastAPI): Simple, synchronous web framework
- **Supabase**: Handles authentication, database, storage
- **PostgreSQL**: Direct connections via psycopg2
- **No ORM**: Minimal SQLAlchemy usage, mostly raw SQL
- **No Pydantic**: Plain Python classes and dicts
- **No WTForms**: Custom handler classes for forms

## 📝 Flask Application Structure

### Application Factory Pattern

```python
# app.py
from flask import Flask, g
from config import Config, supabase_extension, limiter, get_db, teardown_db

def create_app(db_name=None, env=None):
    """
    Construct the core Flask application.

    Args:
        db_name: Optional database name override for testing
        env: Optional environment override for testing
    """
    app = Flask(
        __name__,
        template_folder=os.path.abspath("../frontend/templates"),
        static_folder=os.path.abspath("../static"),
    )
    app.config.from_object(Config)

    if db_name is not None:
        app.config["POSTGRES_DB_NAME"] = db_name
    if env is not None:
        app.config["ENV"] = env

    # Register blueprints
    app.register_blueprint(main_routes, url_prefix="/")
    app.register_blueprint(auth_routes, url_prefix="/auth")
    app.register_blueprint(dashboard_routes, url_prefix="/dashboard")
    app.register_blueprint(data_routes, url_prefix="/data")
    app.register_blueprint(privacy_routes, url_prefix="/privacy")

    # Initialize extensions
    if app.config["ENV"] != "testing":
        limiter.init_app(app)

    supabase_extension.init_app(app)
    app.teardown_appcontext(teardown_db)

    @app.before_request
    def before_request():
        """Establish database connection for the current request."""
        g.db = get_db()

    return app
```

### Blueprint Pattern

```python
# src/auth/routes.py
from flask import Blueprint, render_template, request, redirect, url_for

routes = Blueprint("auth_routes", __name__)

@routes.route("/login", methods=["GET", "POST"])
def login():
    """Handle user login."""
    if request.method == "GET":
        return render_template("auth/login.html")

    # POST request
    from src.auth.form import LoginHandler
    handler = LoginHandler()
    return handler.handle_auth()

@routes.route("/logout")
def logout():
    """Handle user logout."""
    session.clear()
    return redirect(url_for("main_routes.index"))
```

## 🎨 Form Handling Pattern

### Custom Handler Classes (NOT WTForms)

The codebase uses custom handler classes that extract data from `request.form`:

```python
# src/auth/form.py
from flask import request, session, render_template, redirect, url_for, flash
from supabase import AuthApiError
from config import supabase_extension

class LoginHandler:
    """Handle user login using Supabase authentication."""

    def __init__(self):
        try:
            self.email = request.form.get("email", "")
            self.password = request.form.get("password", "")
        except (AttributeError, KeyError):
            self.email = self.password = None

    def handle_auth(self):
        """Authenticate user and redirect to dashboard on success."""
        if not self.email or not self.password:
            flash("Email and password are required", "danger")
            return render_template("auth/login.html"), 400

        try:
            signup_resp = supabase_extension.client.auth.sign_in_with_password(
                {"email": self.email, "password": self.password}
            )
        except AuthApiError:
            flash("Invalid email or password", "danger")
            return render_template("auth/login.html"), 400

        session["email"] = self.email
        session["user"] = signup_resp.user.id

        return redirect(url_for("dashboard_routes.dashboard"))
```

### Base Handler Pattern

For data operations, use the BaseHandler:

```python
# src/form_handler.py
import pandas as pd
from flask import session
from src.exceptions import GenericExceptionHandler

class BaseHandler:
    """Base class for handling session-based data operations."""

    def __init__(self):
        self._session = session
        self._ctx = {
            "user_email": self._session.get("email"),
        }
        self._filepath = None

    def _load_dataframe(self):
        """Load DataFrame from uploaded file path in session."""
        try:
            self._filepath = self._filepath or self._session.get("uploaded_filepath", "")

            if not self._filepath:
                raise GenericExceptionHandler(
                    "No valid uploaded file found in session.",
                    status_code=400
                )

            df = pd.read_csv(self._filepath)
            if df.empty:
                raise GenericExceptionHandler("Uploaded file is empty.", status_code=400)

            return df

        except pd.errors.ParserError as e:
            raise GenericExceptionHandler(
                f"Failed to parse CSV file: {str(e)}",
                status_code=400
            )
```

## 🔐 Authentication & Security

### Supabase Authentication (NOT Custom JWT)

Authentication is handled entirely by Supabase:

```python
# Login
from config import supabase_extension

response = supabase_extension.client.auth.sign_in_with_password({
    "email": email,
    "password": password
})

# Store in session
session["email"] = email
session["user"] = response.user.id

# Get current user
user = supabase_extension.client.auth.get_user()
```

### Session Management

```python
from flask import session

# Set session data
session["email"] = user_email
session["user"] = user_id
session["uploaded_filepath"] = filepath

# Get session data
user_email = session.get("email")

# Clear session (logout)
session.clear()
```

### Authentication Decorator

```python
# src/auth/decorators.py
from functools import wraps
from flask import session, redirect, url_for, flash

def login_required(f):
    """Require user to be logged in."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user" not in session:
            flash("Please log in to access this page.", "warning")
            return redirect(url_for("auth_routes.login"))
        return f(*args, **kwargs)
    return decorated_function

# Usage
@routes.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard/index.html")
```

## ⚙️ Configuration

### Environment-Based Config (NOT Pydantic)

Environment variables are loaded from `.env` files. A template is provided at `backend/.env.example`.

```python
# config.py
import os
from dotenv import load_dotenv

# Load from backend/.env (or backend/tests/.env.test for tests)
load_dotenv()

class Config:
    """Application configuration settings."""

    ENV = os.getenv("ENV")
    SECRET_KEY = os.getenv("SECRET_KEY", "supersecret")
    UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", "./uploads")
    ALLOWED_EXTENSIONS = {"csv"}
    MAX_CONTENT_LENGTH = 16 * 1000 * 10000

    # Supabase
    SUPABASE_URL = os.getenv("SUPABASE_URL")
    SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

    # PostgreSQL
    POSTGRES_HOST = os.getenv("POSTGRES_HOST")
    POSTGRES_PORT = os.getenv("POSTGRES_PORT")
    POSTGRES_USER = os.getenv("POSTGRES_USER")
    POSTGRES_SECRET = os.getenv("POSTGRES_SECRET")
    POSTGRES_DB_NAME = os.getenv("POSTGRES_DB_NAME")
```

### Supabase Extension

```python
# config.py (continued)
from flask import g, current_app
from supabase import Client, ClientOptions, create_client

class Supabase:
    """Supabase integration class."""

    def __init__(self, app=None, client_options: dict | None = None):
        self.client_options = client_options
        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        """Initialize Flask app with Supabase configuration."""
        app.config.setdefault("SUPABASE_URL", Config.SUPABASE_URL)
        app.config.setdefault("SUPABASE_SERVICE_ROLE_KEY", Config.SUPABASE_SERVICE_ROLE_KEY)
        app.teardown_appcontext(self.teardown)

    def teardown(self, exception):
        """Clean up Supabase client after each request."""
        g.pop("supabase_client", None)

    @property
    def client(self) -> Client:
        """Lazily initialize and return Supabase client."""
        if "supabase_client" not in g:
            url = current_app.config["SUPABASE_URL"]
            key = current_app.config.get("SUPABASE_SERVICE_ROLE_KEY")

            if not url or not key:
                raise RuntimeError("Supabase URL or KEY not configured properly.")

            options = self.client_options
            if options and not isinstance(options, ClientOptions):
                options = ClientOptions(**options)

            g.supabase_client = create_client(url, key, options=options)

        return g.supabase_client

supabase_extension = Supabase()
```

## 🗄️ Database Access

### Direct PostgreSQL Connections

```python
# config.py (continued)
import psycopg2
from psycopg2 import OperationalError

def init_db():
    """Establish PostgreSQL database connection."""
    try:
        config = current_app.config
        conn = psycopg2.connect(
            host=config["POSTGRES_HOST"],
            port=config["POSTGRES_PORT"],
            user=config["POSTGRES_USER"],
            password=config["POSTGRES_SECRET"],
            database=config["POSTGRES_DB_NAME"],
        )
        return conn
    except OperationalError as e:
        print(f"[ERROR] Failed to connect to DB: {e}")
        return None

def get_db():
    """Get database connection for current request."""
    if "db" not in g:
        g.db = init_db()
    return g.db

def teardown_db(exception):
    """Close database connection after request."""
    db = g.pop("db", None)
    if db is not None:
        db.close()
```

### Executing Queries

```python
from flask import g

def get_datasets_for_user(user_id: str):
    """Get all datasets for a user."""
    db = g.db
    cursor = db.cursor()

    try:
        cursor.execute(
            "SELECT * FROM datasets WHERE user_id = %s ORDER BY created_at DESC",
            (user_id,)
        )
        results = cursor.fetchall()
        return results
    finally:
        cursor.close()
```

## 🚨 Error Handling

### Custom Exception Class

```python
# src/exceptions.py
class GenericExceptionHandler(Exception):
    """Custom exception for application-level errors."""

    status_code = 400

    def __init__(self, message, status_code=None, payload=None, redirect_to=None):
        super().__init__()
        self.message = message
        self.status_code = status_code or self.status_code
        self.payload = payload
        self.redirect_to = redirect_to

    def to_dict(self):
        rv = dict(self.payload or {})
        rv["message"] = self.message
        return rv
```

### Error Handling in Routes

```python
from src.exceptions import GenericExceptionHandler
from flask import flash, redirect, url_for

@routes.route("/process", methods=["POST"])
def process_data():
    try:
        # Process data
        result = perform_operation()
        return render_template("success.html", result=result)

    except GenericExceptionHandler as e:
        flash(e.message, "danger")
        if e.redirect_to:
            return redirect(url_for(e.redirect_to)), e.status_code
        return render_template("error.html"), e.status_code

    except Exception as e:
        flash(f"Unexpected error: {str(e)}", "danger")
        return redirect(url_for("main_routes.index")), 500
```

## 📊 Logging

### Flask's Built-in Logger (NOT Structlog)

```python
from flask import current_app

# In routes or helpers
current_app.logger.info("Processing dataset upload")
current_app.logger.warning(f"Invalid file format: {filename}")
current_app.logger.error(f"Database connection failed: {e}")

# Configure in app.py if needed
import logging

app.logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter(
    '[%(asctime)s] %(levelname)s in %(module)s: %(message)s'
))
app.logger.addHandler(handler)
```

## 🧪 Testing Standards

### Test Structure with Pytest

```python
# tests/test_auth.py
import pytest
from flask import session

def test_login_success(client, app):
    """Test successful user login."""
    response = client.post("/auth/login", data={
        "email": "test@example.com",
        "password": "password123"
    })

    assert response.status_code == 302  # Redirect

    with client.session_transaction() as sess:
        assert sess["email"] == "test@example.com"
        assert "user" in sess

def test_login_invalid_credentials(client):
    """Test login with invalid credentials."""
    response = client.post("/auth/login", data={
        "email": "test@example.com",
        "password": "wrongpassword"
    })

    assert response.status_code == 400
    assert b"Invalid email or password" in response.data
```

### Fixtures

```python
# tests/conftest.py
import pytest
from backend.app import create_app

@pytest.fixture
def app():
    """Create Flask app for testing."""
    app = create_app(db_name="test_database", env="testing")
    app.config["TESTING"] = True
    yield app

@pytest.fixture
def client(app):
    """Create test client."""
    return app.test_client()

@pytest.fixture
def runner(app):
    """Create test CLI runner."""
    return app.test_cli_runner()
```

## 🛠️ Development Environment

### Package Management with UV (Exclusive)

```bash
# IMPORTANT: Use UV exclusively - NEVER use pip directly

# Sync all dependencies (including dev)
uv sync --all-groups

# Sync only production dependencies
uv sync

# Add production dependencies
uv add flask sqlalchemy

# Add development dependencies
uv add --group dev pytest ruff mypy

# Add test-only dependencies
uv add --group test pytest pytest-cov

# Remove dependencies
uv remove package-name

# Run commands in virtual environment
uv run flask run --debug
uv run pytest
uv run ruff check .
uv run mypy src/

# Or activate venv and run directly
source .venv/bin/activate
flask run --debug
```

### Running the Application

```bash
# Development mode
cd backend
uv run flask run --debug

# Access at http://localhost:5000
```

### Code Quality Tools

```bash
# Format code
uv run ruff format .

# Lint code
uv run ruff check .

# Fix linting issues automatically
uv run ruff check --fix .

# Type check (if configured)
uv run mypy src/

# Run tests
uv run pytest

# Run tests with coverage
uv run pytest --cov=src --cov-report=html
```

## 📝 Documentation Standards

### Google-Style Docstrings (Keep Simple)

```python
def upload_dataset(user_id: str, file_path: str, metadata: dict) -> dict:
    """
    Upload dataset with metadata to storage.

    Args:
        user_id: Unique identifier for the user.
        file_path: Path to the dataset file.
        metadata: Dictionary containing dataset metadata.

    Returns:
        Dictionary with upload status and dataset ID.

    Raises:
        GenericExceptionHandler: If upload fails or file is invalid.
    """
    pass
```

## 📋 Development Checklist

### Before Starting Development
- [ ] Read root CLAUDE.md for project-wide conventions
- [ ] Understand the simplest solution first
- [ ] Check if feature already exists
- [ ] Question if feature is needed (YAGNI)

### While Developing
- [ ] Start with simplest working solution
- [ ] Follow Flask patterns (blueprints, templates, sessions)
- [ ] Use custom handler classes for forms
- [ ] Leverage Supabase for authentication
- [ ] Use Flask's session for state management
- [ ] Keep functions under 50 lines when possible
- [ ] Handle errors with GenericExceptionHandler
- [ ] Validate inputs early

### Before Committing
- [ ] Run tests: `uv run pytest`
- [ ] Run linter: `uv run ruff check .`
- [ ] Format code: `uv run ruff format .`
- [ ] Ensure no secrets in code
- [ ] Question: "Can this be simpler?"

### Security Checklist
- [ ] No hardcoded credentials
- [ ] SQL queries use parameterization (%s placeholders)
- [ ] Supabase handles authentication (don't roll your own)
- [ ] Session data validated before use
- [ ] File uploads validated (type, size, content)

## ⚠️ Common Pitfalls to Avoid

1. **Don't Mix Frameworks**
   ```python
   # ❌ Wrong - This is Flask, not FastAPI
   from fastapi import FastAPI
   from pydantic import BaseModel

   # ✅ Correct - Use Flask patterns
   from flask import Flask, request
   ```

2. **Don't Create Custom Auth**
   ```python
   # ❌ Wrong - Don't implement JWT yourself
   def create_jwt_token(user_id):
       return jwt.encode({"user": user_id}, SECRET)

   # ✅ Correct - Use Supabase
   response = supabase_extension.client.auth.sign_in_with_password({
       "email": email,
       "password": password
   })
   ```

3. **Don't Use SQL String Formatting**
   ```python
   # ❌ Wrong - SQL injection vulnerability
   query = f"SELECT * FROM users WHERE email = '{email}'"
   cursor.execute(query)

   # ✅ Correct - Use parameterized queries
   cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
   ```

4. **Don't Import WTForms**
   ```python
   # ❌ Wrong - We don't use WTForms
   from flask_wtf import FlaskForm
   from wtforms import StringField

   # ✅ Correct - Use custom handler classes
   class LoginHandler:
       def __init__(self):
           self.email = request.form.get("email")
   ```

## 📚 References & Resources

### Essential Documentation
- [Flask Documentation](https://flask.palletsprojects.com/)
- [Jinja2 Templates](https://jinja.palletsprojects.com/)
- [Supabase Python Client](https://supabase.com/docs/reference/python/introduction)
- [psycopg2 Documentation](https://www.psycopg.org/docs/)
- [Pytest Documentation](https://docs.pytest.org/)
- [Ruff Linter](https://docs.astral.sh/ruff/)

---

**Remember**: This is a Flask application. Start simple. Use Supabase for auth. Use custom handler classes for forms. The best code is code that doesn't exist. The second best is simple code that works.
