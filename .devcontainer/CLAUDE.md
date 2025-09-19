# DevContainer Configuration Guide

## Naming Conventions

### Shell Scripts
All shell scripts MUST use **kebab-case** (dash-separated lowercase) naming:
- ✅ Correct: `post-create.sh`, `mcp-setup.sh`, `validate-setup.sh`
- ❌ Incorrect: `postCreate.sh`, `post_create.sh`, `PostCreate.sh`

This is the standard convention for shell scripts and ensures consistency across the project.

## Claude Code and MCP Integration

### Claude Code CLI
The devcontainer automatically installs Claude Code CLI, providing:
- Command-line interface for Claude AI assistance
- Integration with MCP (Model Context Protocol) servers
- Enhanced code understanding and generation capabilities

### Serena MCP Server
Serena provides semantic code analysis tools:
- **Symbolic Code Navigation**: Navigate code by symbols, not just text
- **Semantic Editing**: Edit code at the symbol level (classes, functions, methods)
- **Efficient Exploration**: Avoid reading entire files unnecessarily
- **Multi-language Support**: Works with 20+ programming languages

### Setup Process
1. **post-create.sh**: Installs Claude Code CLI via npm or native installer
2. **mcp-setup.sh**: Configures Serena MCP server for the project
3. **post-start.sh**: Runs MCP setup on container start

### Manual MCP Commands
```bash
# Check MCP server status
claude mcp list

# Add Serena manually if needed
claude mcp add serena -- uvx --from git+https://github.com/oraios/serena serena start-mcp-server --context ide-assistant --project $(pwd)

# Remove an MCP server
claude mcp remove serena

# Check Claude Code health
claude doctor
```

## Python Package Management

### Using uv Exclusively with pyproject.toml

This devcontainer uses **uv** as the exclusive Python package manager with a modern pyproject.toml configuration. Do NOT use pip directly.

**uv Commands to Use**:
```bash
# Sync all dependencies (including dev)
uv sync --all-groups

# Sync only production dependencies
uv sync

# Add a new production dependency
uv add flask sqlalchemy

# Add a development dependency
uv add --group dev pytest ruff

# Remove a dependency
uv remove package-name

# Update all dependencies
uv sync --upgrade

# List installed packages
uv pip list

# Run commands in the virtual environment
uv run python app.py
uv run pytest
uv run ruff check .
```

**Key Benefits**:
- Lightning-fast dependency resolution
- Automatic virtual environment management
- Lock file for reproducible builds (uv.lock)
- Modern pyproject.toml configuration
- Native support for dependency groups

**Never Use**:
- `pip install ...` (use `uv add` instead)
- `python -m pip ...` (use `uv` commands instead)
- `pip3 ...` (use `uv` commands instead)
- `requirements.txt` (managed via pyproject.toml now)

## Base Image

**Definitive Base Image**: `mcr.microsoft.com/devcontainers/python:3.13`

This is the standardized base image for the FAIRDatabase development environment. This choice provides:

- Python 3.13 (latest stable release)
- Debian 12 (bookworm) base OS
- Long-term support until October 2029
- Optimal balance of modern features and stability

### Do Not Use

- `dev-3.13` - Unstable development builds
- `latest` - Unpredictable version changes
- `bullseye`/`buster` - Outdated Debian versions
- `trixie` - Unreleased testing version

## VS Code Extensions

### Extension Selection Rationale

**Python Development** (5 extensions)
- Core Python support with debugging and environment management
- Ruff for fast linting/formatting (replaces Black, isort, flake8)

**AI Assistance** (3 extensions)
- Claude Code for primary AI assistance
- GitHub Copilot with chat for code completion

**Database** (3 extensions)
- Supabase extension for native Supabase integration
- SQLTools for general SQL development with PostgreSQL driver

**Git & GitHub** (3 extensions)
- Git Graph for visual branch management
- GitHub integration for PRs and Actions

**Container Development** (2 extensions)
- Remote Containers for devcontainer support
- Docker for container management

**Configuration** (3 extensions)
- YAML, dotenv, and editorconfig for configuration files

### Rejected Extensions

**Database Clients** - Avoided redundancy:
- `cweijan.vscode-postgresql-client2` - Supabase extension covers this
- `ckolkman.vscode-postgres` - SQLTools is sufficient
- `ms-ossdata.vscode-pgsql` - Redundant with SQLTools

**Container Extensions** - Kept minimal:
- `docker.docker` - ms-azuretools.vscode-docker is more comprehensive
- `ms-vscode-remote.vscode-remote-extensionpack` - Too many unnecessary extensions
- `GitHub.codespaces` - Not using GitHub Codespaces

**Git Tools**:
- `eamodio.gitlens` - Git Graph provides cleaner visualization

Any changes to the extension list must be explicitly approved and documented here.