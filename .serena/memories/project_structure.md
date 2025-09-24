# FAIRDatabase Project Structure

## Root Directory Structure
```
FAIRDatabase/
├── backend/              # Python Flask application
├── frontend/             # HTML templates and frontend assets  
├── static/              # Static assets (CSS, JS, images)
├── supabase/            # Database configuration
├── .devcontainer/       # Development container configuration
├── .github/             # GitHub workflows and actions
├── node_modules/        # Node.js dependencies
├── CLAUDE.md            # Project-wide AI assistant guidelines
├── README.md            # User-facing documentation
├── package.json         # Node.js project configuration
└── .gitignore           # Git ignore rules
```

## Backend Structure (Flask Application)
```
backend/
├── CLAUDE.md            # Backend-specific guidelines
├── pyproject.toml       # Python project config & dependencies
├── uv.lock             # Dependency lock file (auto-generated)
├── app.py              # Main Flask application entry point
├── config.py           # Application configuration
├── .env                # Environment variables
├── .venv/              # Virtual environment (auto-created by uv)
│
├── src/                # Application source code
│   ├── auth/           # Authentication module
│   │   ├── routes.py   # Auth endpoints
│   │   ├── helpers.py  # Auth utilities
│   │   ├── decorators.py # Auth decorators
│   │   └── form.py     # Auth forms
│   │
│   ├── dashboard/      # Dashboard module
│   │   ├── routes.py   # Dashboard endpoints
│   │   └── helpers.py  # Dashboard utilities
│   │
│   ├── data/           # Data management module
│   │   ├── routes.py   # Data endpoints
│   │   ├── helpers.py  # Data utilities
│   │   └── form.py     # Data forms
│   │
│   ├── main/           # Main/home module
│   │   ├── routes.py   # Main endpoints
│   │   └── helpers.py  # Main utilities
│   │
│   ├── privacy/        # Privacy module
│   │   ├── routes.py   # Privacy endpoints
│   │   ├── helpers.py  # Privacy utilities
│   │   └── form.py     # Privacy forms
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
│   ├── exceptions.py   # Custom exceptions
│   └── form_handler.py # Form handling utilities
│
└── tests/              # Test suite
    ├── conftest.py     # Pytest fixtures
    ├── .env.test       # Test environment variables
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
├── templates/          # HTML templates
│   ├── base templates
│   └── module templates
└── public/            # Public assets
```

## URL Structure (Flask Blueprints)
- `/` - Main routes (home, about, etc.)
- `/auth` - Authentication routes (login, register, logout)
- `/dashboard` - Dashboard routes
- `/data` - Data management routes
- `/privacy` - Privacy and anonymization routes

## Module Pattern
Each module (auth, dashboard, data, etc.) follows this structure:
- `routes.py` - Flask route definitions and request handlers
- `helpers.py` - Business logic and utility functions
- `form.py` - WTForms form definitions (if applicable)
- `decorators.py` - Custom decorators (if applicable)

## Key Configuration Files
- `pyproject.toml` - Python dependencies, tools config (ruff, mypy, pytest)
- `config.py` - Flask app configuration
- `.env` - Environment variables (not in git)
- `CLAUDE.md` files - AI assistant context and guidelines