# FAIRDatabase Project Overview

## Purpose
FAIRDatabase implements FAIR data principles (Findable, Accessible, Interoperable, Reusable) for research data management. It provides a simple, pragmatic web interface for researchers to manage and share data following FAIR principles.

## Technology Stack
- **Backend**: Python/Flask (may migrate to FastAPI)
- **Database**: Supabase (PostgreSQL)
- **Frontend**: HTML templates with static assets
- **Testing**: pytest framework  
- **Package Management**: uv with pyproject.toml
- **Python Version**: >=3.13 (minimum required version)
- **Development Tools**: ruff (linter/formatter), mypy (type checker), ipython, ipdb, rich

## Repository Information
- Working Fork: https://github.com/seijispieker/FAIRDatabase
- Original: https://github.com/SheratonMV/FAIRDatabase
- Rule: Never push to original repository, always work in fork

## Development Environment
The project uses DevContainers for consistent development environments with:
- Python 3.13 with uv package manager
- Node.js for frontend tooling
- Supabase for local PostgreSQL database
- Docker-in-Docker support
- Pre-installed tools: uv, ruff, GitHub CLI

## Core Development Philosophy
The project follows a "Start simple, add complexity only when proven necessary" approach with these principles:
- KISS (Keep It Simple, Stupid)
- YAGNI (You Aren't Gonna Need It) 
- DRY (Don't Repeat Yourself)
- Single Responsibility
- Fail Fast
- Explicit Over Implicit

## Application Endpoints
- Flask Backend: http://localhost:5000
- Supabase Studio: http://localhost:54323
- API Gateway: http://localhost:54321

## Key Dependencies

### Production Dependencies
- flask>=3.1.0 - Web framework
- werkzeug>=3.1.3 - WSGI utilities
- psycopg2-binary>=2.9.10 - PostgreSQL adapter
- pandas>=2.2.3 - Data manipulation
- sqlalchemy>=2.0.40 - SQL toolkit (minimal usage)
- supabase>=2.15.1 - Backend-as-a-Service
- flask-cors>=5.0.1 - CORS support
- flask-limiter>=3.12 - Rate limiting
- python-dotenv>=1.1.0 - Environment variables

### Development Dependencies  
- pytest>=8.3.4 - Testing framework
- pytest-cov>=6.0.0 - Coverage reporting
- pytest-mock>=3.14.0 - Mocking utilities
- pytest-asyncio>=0.25.2 - Async test support
- ruff>=0.9.2 - Linter and formatter
- mypy>=1.14.1 - Type checker
- ipython>=8.31.0 - Enhanced Python shell
- ipdb>=0.13.13 - Debugger
- rich>=13.9.4 - Terminal formatting
- httpx>=0.28.1 - HTTP client for testing