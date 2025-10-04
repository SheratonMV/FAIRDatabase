# DevContainer Configuration Guide

## Quick Reference

**Base Image:** `mcr.microsoft.com/devcontainers/python:3.13`
**Package Manager:** uv (exclusively - never use pip)
**Database:** Supabase (manual start required: `npx supabase start`)

## Lifecycle Scripts

### post-create.sh (runs once on container creation)
- Git safe directory configuration
- Python environment setup (uv sync)
- npm and Supabase CLI installation
- Claude Code CLI and MCP setup
- Displays setup notes and quick command reference

**Note**: Supabase is NOT auto-started. Users must manually run `npx supabase start` before using the backend.

## Access Points

- **Flask Backend:** http://localhost:5000 (run `cd backend && ./run.sh`)
- **Supabase Studio:** http://localhost:54323 (after running `npx supabase start`)
- **Supabase API:** http://localhost:54321 (after running `npx supabase start`)

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