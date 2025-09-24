# FAIRDatabase Project Overview

## Purpose
FAIRDatabase implements FAIR data principles (Findable, Accessible, Interoperable, Reusable) for research data management. It provides a simple, pragmatic web interface for researchers to manage and share data following FAIR principles.

## Technology Stack
- **Backend**: Python/Flask (may migrate to FastAPI)
- **Database**: Supabase (PostgreSQL)
- **Frontend**: HTML templates with static assets
- **Testing**: pytest framework  
- **Package Management**: uv with pyproject.toml
- **Python Version**: 3.10+ (up to 3.13)
- **Development Tools**: ruff (linter/formatter), mypy (type checker)

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
- Supabase Studio: http://localhost:54321
- API Gateway: http://localhost:54323