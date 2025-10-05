# FAIRDatabase Project Structure

## Root Directory Structure
```
FAIRDatabase/
├── backend/              # Python Flask application
├── frontend/             # HTML templates and frontend assets  
├── static/              # Static assets (CSS, JS, images) at root level
├── supabase/            # Database configuration
├── .devcontainer/       # Development container configuration
├── .serena/             # Serena agent memories (not in git)
├── CLAUDE.md            # Project-wide AI assistant guidelines
├── README.md            # User-facing documentation
└── .gitignore           # Git ignore rules
```

## Backend Structure (Flask Application)
```
backend/
├── CLAUDE.md            # Backend-specific guidelines
├── pyproject.toml       # Python project config & dependencies (UV package manager)
├── uv.lock             # Dependency lock file (auto-generated, committed)
├── .python-version     # Python version specification (3.13)
├── app.py              # Main Flask application entry point
├── config.py           # Application configuration (Config class, Supabase extension)
├── .env                # Environment variables (not in git)
├── .venv/              # Virtual environment (auto-created by uv, not in git)
│
├── src/                # Application source code
│   ├── __init__.py
│   │
│   ├── auth/           # Authentication module
│   │   ├── routes.py   # Auth blueprint and route handlers
│   │   ├── helpers.py  # Auth business logic
│   │   ├── decorators.py # Auth decorators (login_required)
│   │   └── form.py     # Form handler classes (LoginHandler, RegisterHandler)
│   │
│   ├── dashboard/      # Dashboard module
│   │   ├── routes.py   # Dashboard blueprint and routes
│   │   └── helpers.py  # Dashboard utilities
│   │
│   ├── data/           # Data management module
│   │   ├── routes.py   # Data blueprint and routes
│   │   ├── helpers.py  # Data utilities
│   │   └── form.py     # Data form handlers
│   │
│   ├── main/           # Main/home module
│   │   ├── routes.py   # Main blueprint and routes
│   │   └── helpers.py  # Main utilities
│   │
│   ├── privacy/        # Privacy module
│   │   ├── routes.py   # Privacy blueprint and routes
│   │   ├── helpers.py  # Privacy utilities
│   │   └── form.py     # Privacy form handlers
│   │
│   ├── anonymization/  # Data anonymization module
│   │   ├── k_anonymity.py
│   │   ├── enforce_privacy.py
│   │   ├── normalized_entropy.py
│   │   ├── p_29.py
│   │   ├── t_closeness.py
│   │   ├── checks/     # Validation checks
│   │   └── utils/      # Helper utilities
│   │
│   ├── exceptions.py   # Custom exceptions (GenericExceptionHandler)
│   └── form_handler.py # Base form handler (BaseHandler)
│
└── tests/              # Test suite
    ├── conftest.py     # Pytest fixtures
    ├── .env.test       # Test environment variables (not in git)
    ├── auth/           # Auth module tests
    ├── dashboard/      # Dashboard module tests
    ├── data/           # Data module tests
    ├── main/           # Main module tests
    └── privacy/        # Privacy module tests
```

## Frontend Structure
```
frontend/
├── CLAUDE.md           # Frontend-specific guidelines
├── templates/          # Jinja2 HTML templates
│   ├── auth/          # Authentication templates (login, register)
│   ├── dashboard/     # Dashboard templates
│   ├── data/          # Data management templates
│   ├── privacy/       # Privacy templates
│   ├── documentation/ # Documentation pages
│   └── federated_learning/ # Federated learning templates
└── public/            # Public assets (ONLY logo images)
    ├── avatar1.png
    ├── metahealth_logo.svg
    └── metahealth_small.png
```

## Static Assets (Root Level)
**IMPORTANT**: Static assets are at ROOT level in `/static/`, NOT in `/frontend/public/`
```
static/                 # Static assets at root level
├── styles.css         # Main stylesheet
├── script.js          # Main JavaScript file
└── img/               # Image assets
    ├── avatar1.png
    ├── metahealth_logo.svg
    └── metahealth_small.png
```

## Supabase Configuration
```
supabase/
├── config.toml        # Supabase local configuration
├── .temp/             # Temporary files (not in git)
├── .branches/         # Branch configurations
└── .gitignore         # Supabase-specific ignores
```

## Development Container
```
.devcontainer/
├── CLAUDE.md          # Dev container documentation
├── devcontainer.json  # Dev container configuration
└── post-create.sh     # Post-creation setup script
```

## URL Structure (Flask Blueprints)
- `/` - Main routes (home, about, etc.) - `main_routes`
- `/auth` - Authentication routes (login, register, logout) - `auth_routes`
- `/dashboard` - Dashboard routes - `dashboard_routes`
- `/data` - Data management routes - `data_routes`
- `/privacy` - Privacy and anonymization routes - `privacy_routes`

## Module Pattern
Each module (auth, dashboard, data, privacy) follows this structure:
- `routes.py` - Flask blueprint, route definitions and request handlers
- `helpers.py` - Business logic and utility functions
- `form.py` - Custom handler classes for form processing (NOT WTForms)
- `decorators.py` - Custom decorators (only in auth module)

## Form Handling Pattern
The codebase uses **custom handler classes** (NOT WTForms or Pydantic):
- Extract data from `request.form` in `__init__`
- Business logic in `handle_auth()` or similar methods
- Return rendered templates or redirects
- Examples: `LoginHandler`, `RegisterHandler`, `BaseHandler`

## Authentication Pattern
- **Supabase** handles all authentication (NOT custom JWT)
- User credentials stored in Supabase
- Session managed via Flask sessions
- `supabase_extension.client.auth` for auth operations
- Session keys: `email`, `user` (user ID)

## Configuration Pattern
- Plain Python `Config` class (NOT Pydantic BaseSettings)
- Environment variables loaded via `python-dotenv`
- Values read with `os.getenv()`
- `Supabase` extension class for lazy client initialization
- Database connections via `psycopg2` with connection pooling in Flask `g`

## Key Configuration Files
- `pyproject.toml` - Python dependencies, tools config (ruff, mypy, pytest)
- `uv.lock` - Locked dependency versions (auto-generated, committed)
- `.python-version` - Python version specification (3.13)
- `config.py` - Flask app configuration (Config class, Supabase, DB functions)
- `.env` - Environment variables (not in git)
- `CLAUDE.md` files - AI assistant context and guidelines

## Technology Stack
- **Framework**: Flask 3.1+ (synchronous, NOT FastAPI)
- **Database**: Supabase (PostgreSQL) with direct psycopg2 connections
- **Package Manager**: UV (NOT pip)
- **Template Engine**: Jinja2 (server-side rendering)
- **Testing**: pytest with fixtures
- **Linting**: Ruff (replaces black, flake8, isort, etc.)
- **Type Checking**: mypy
- **Auth**: Supabase Auth (NOT custom JWT or sessions)
- **Frontend**: Vanilla JS + CSS (no build process)
- **Python Version**: 3.13+ (minimum required)

## Important Notes
- NO FastAPI, Pydantic, WTForms, Passlib, Structlog, or SQLAlchemy ORM
- Uses Flask's built-in logger (NOT structlog)
- Uses custom handler classes for forms (NOT WTForms)
- Uses Supabase for auth (NOT custom password hashing)
- Static files at root `/static/`, NOT `/frontend/public/` (which only has logos)
- Python 3.13 is the MINIMUM required version
- UV is the ONLY package manager (NEVER use pip directly)

## Development Dependencies (pyproject.toml)
Production: flask, werkzeug, psycopg2-binary, pandas, sqlalchemy, supabase, flask-cors, flask-limiter, python-dotenv

Development: pytest, pytest-cov, pytest-mock, pytest-asyncio, ruff, mypy, ipython, ipdb, rich, httpx