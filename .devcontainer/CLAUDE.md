# DevContainer Configuration Guide

## Quick Reference

**Base Image:** `mcr.microsoft.com/devcontainers/python:3.13`
**Package Manager:** uv (exclusively - never use pip)
**Database:** Supabase (auto-starts on container start)

## Lifecycle Scripts

### post-create.sh (runs once)
- Git safe directory configuration
- Python environment setup (uv sync)
- npm and Supabase CLI installation
- Claude Code CLI and MCP setup

### post-start.sh (runs on each start)
- Starts Supabase services automatically
- Displays comprehensive command reference

## Access Points

- **Flask Backend:** http://localhost:5000 (run `cd backend && ./run.sh`)
- **Supabase Studio:** http://localhost:54323 (auto-starts)
- **Supabase API:** http://localhost:54321 (auto-starts)

## Development Conventions

### Shell Scripts
- **Naming:** Use kebab-case (`post-create.sh`, not `postCreate.sh`)
- **Style:** Emoji-enhanced output with progress indicators
- **Structure:** Unicode boxes for sections (═ for headers, ─ for subsections)

### Python Package Management

**Use uv exclusively** - never use pip directly:
- Add dependency: `uv add <package>`
- Add dev dependency: `uv add --group dev <package>`
- Sync dependencies: `uv sync --all-groups`
- Run commands: `uv run python app.py`

All dependencies managed via `backend/pyproject.toml`


## VS Code Extensions

Configured in `devcontainer.json`:
- **Python:** Core support, Pylance, debugger, Ruff
- **AI:** Claude Code, GitHub Copilot
- **Database:** Supabase, SQLTools with PostgreSQL
- **Git/GitHub:** Git Graph, PR support, Actions
- **Other:** Docker, YAML, dotenv, Deno (for Supabase functions)