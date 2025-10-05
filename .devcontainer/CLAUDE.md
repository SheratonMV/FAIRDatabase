# CLAUDE.md - Development Container Guide

This file provides guidance for the development container setup and configuration for FAIRDatabase.

## 📋 Overview

The project uses **Development Containers** (devcontainers) for consistent, reproducible development environments. This approach ensures all developers have identical development setups regardless of their local machine configuration.

## 🎯 Core Principles

Following the project's KISS philosophy:
- **Simple Base Image**: Use official Microsoft devcontainer images
- **Minimal Features**: Only include essential development tools
- **Convention Over Configuration**: Sensible defaults, minimal customization
- **Reproducible**: Anyone can spin up the same environment

## 🐳 Container Configuration

### Base Image

```json
"image": "mcr.microsoft.com/devcontainers/python:3.13"
```

We use Microsoft's official Python 3.13 devcontainer image which provides:
- Python 3.13 (latest stable)
- Common development tools
- Git
- Basic shell utilities

### Installed Features

```json
"features": {
  "ghcr.io/devcontainers/features/docker-in-docker:2": {
    "moby": "false"
  },
  "ghcr.io/devcontainers-extra/features/uv:1": {},
  "ghcr.io/devcontainers-extra/features/ruff:1": {},
  "ghcr.io/devcontainers/features/node:1": {},
  "ghcr.io/devcontainers/features/github-cli:1": {}
}
```

**Feature Purposes:**
- **docker-in-docker**: Run Docker inside the container (for Supabase local instance)
- **uv**: Fast Python package manager
- **ruff**: Python linter and formatter
- **node**: Node.js for Supabase CLI
- **github-cli**: GitHub CLI for repository management

## 🔧 Environment Variables

Environment variables are managed via `.env` files, NOT `containerEnv` in devcontainer.json.

### Environment File Setup

The post-create script automatically creates environment files from templates:

**Production/Development** (`backend/.env`):
- Created from `backend/.env.example`
- Contains Flask, Supabase, and PostgreSQL configuration
- Must be reviewed and updated with actual values

**Testing** (`backend/tests/.env.test`):
- Created from `backend/tests/.env.test.example`
- Configured for test environment

### Key Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `ENV` | Application environment | `development` or `testing` |
| `SECRET_KEY` | Flask session secret | Generate with `secrets.token_hex(32)` |
| `FLASK_RUN_HOST` | Flask bind address | `0.0.0.0` (all interfaces) |
| `UPLOAD_FOLDER` | File upload directory | `/workspaces/FAIRDatabase/backend/uploads` |
| `SUPABASE_URL` | Local Supabase instance | `http://127.0.0.1:54321` |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase service key | From local Supabase instance |
| `POSTGRES_HOST` | PostgreSQL host | `127.0.0.1` |
| `POSTGRES_PORT` | PostgreSQL port | `54322` |
| `POSTGRES_USER` | PostgreSQL user | `postgres` |
| `POSTGRES_SECRET` | PostgreSQL password | `postgres` |
| `POSTGRES_DB_NAME` | PostgreSQL database | `postgres` |

## 🔌 Port Forwarding

### VS Code Port Forwarding

```json
"forwardPorts": [5000, 54323, 54324]
```

### All Platforms Port Mapping

```json
"runArgs": [
  "-p", "5000:5000",
  "-p", "54323:54323",
  "-p", "54324:54324"
]
```

The `runArgs` ensures ports work across all devcontainer implementations (VS Code, DevPod, Dev Container CLI).

### Port Reference

| Port | Service | Description |
|------|---------|-------------|
| 5000 | Flask App | Main web application |
| 54323 | Supabase Studio | Database management UI |
| 54324 | Mailpit | Email testing interface |

**Note**: Supabase runs additional services on other ports (54321, 54322) but those are accessed internally.

## 🛠️ VS Code Extensions

### Installed Extensions

The container pre-installs these VS Code extensions:

**Python Development:**
- `ms-python.python` - Python language support
- `ms-python.vscode-pylance` - Python language server
- `charliermarsh.ruff` - Ruff linter/formatter

**AI Assistants:**
- `Anthropic.claude-code` - Claude Code assistant
- `GitHub.copilot` - GitHub Copilot
- `GitHub.copilot-chat` - GitHub Copilot Chat

**Database:**
- `Supabase.vscode-supabase-extension` - Supabase integration
- `Supabase.postgrestools` - PostgreSQL tools
- `mtxr.sqltools` - SQL tools
- `mtxr.sqltools-driver-pg` - PostgreSQL driver

**Development:**
- `ms-azuretools.vscode-docker` - Docker support
- `mhutchie.git-graph` - Git visualization
- `GitHub.vscode-pull-request-github` - GitHub PR management
- `GitHub.vscode-github-actions` - GitHub Actions support
- `redhat.vscode-yaml` - YAML language support
- `mikestead.dotenv` - .env file support

## 📦 Post-Creation Setup

### Lifecycle Script

```json
"postCreateCommand": "bash .devcontainer/post-create.sh"
```

The `post-create.sh` script runs automatically after container creation and performs:

1. **Python Environment Setup**
   - Syncs all dependencies with `uv sync --all-groups`

2. **Environment Configuration**
   - Creates `backend/.env` from `backend/.env.example` (if not exists)
   - Creates `backend/tests/.env.test` from template (if not exists)
   - **IMPORTANT**: Review and update values in `.env` files as needed

3. **Tool Installation**
   - Updates npm to latest version
   - Installs Claude Code CLI globally
   - Configures Claude Code MCP (Serena) for semantic code analysis

4. **Supabase Initialization**
   - Initializes Supabase for local development (if not already initialized)
   - **Note**: Supabase services must be started manually with `npx supabase start`

### Manual Setup Steps

After container creation completes:

```bash
# 1. Review and update environment variables (REQUIRED on first run)
#    Update SUPABASE_SERVICE_ROLE_KEY after starting Supabase
nano backend/.env

# 2. Start Supabase (first time takes ~5 minutes to download images)
npx supabase start
# Copy the service_role key from output and update backend/.env

# 3. Start Flask application
cd backend
uv run flask run

# 4. Access application at http://localhost:5000
```

## 💻 System Requirements

### Minimum Host Requirements

```json
"hostRequirements": {
  "cpus": 2,
  "memory": "2gb",
  "storage": "8gb"
}
```

**Recommended for optimal performance:**
- CPUs: 4 cores
- Memory: 4GB
- Storage: 16GB

### Container Runtime

Choose one:
- **Docker Desktop** (macOS/Windows)
- **Docker Engine** (Linux - best performance)
- **Rancher Desktop** (all platforms)
- **Podman** (rootless alternative)

## 🔍 Development Workflow

### Starting Development

```bash
# Container starts automatically when you open the workspace
# Post-create script runs automatically (Python deps, env files, tools)

# 1. Review environment configuration (first time only)
nano backend/.env

# 2. Start Supabase
npx supabase start
# Copy service_role key to backend/.env (first time only)

# 3. Start Flask
cd backend
uv run flask run
```

### Running Tests

```bash
cd backend
uv run pytest
```

### Code Quality

```bash
cd backend
uv run ruff check .      # Lint
uv run ruff format .     # Format
```

### Database Management

Access Supabase Studio at http://localhost:54323 to:
- Browse database tables
- Run SQL queries
- Manage authentication
- View logs

## 🐛 Troubleshooting

### Container Won't Start

```bash
# Verify Docker is running
docker version

# Rebuild container
# In VS Code: Cmd/Ctrl + Shift + P → "Dev Containers: Rebuild Container"
```

### Supabase Won't Start

```bash
# Stop and restart
npx supabase stop --no-backup
npx supabase start

# If still failing, check Docker resources
docker stats
```

### Port Conflicts

If port 5000 is in use:

```bash
# Find process using port
lsof -i :5000

# Kill process or change Flask port
FLASK_RUN_PORT=5001 uv run flask run --debug
```

### Performance Issues

**macOS/Windows:**
- Increase Docker Desktop memory/CPU limits
- Consider Rancher Desktop or Colima for better performance

**Windows:**
- Clone repo inside WSL2, not Windows filesystem
- Use WSL2-based Docker backend

## 📝 Customization

### Adding New VS Code Extensions

Edit `.devcontainer/devcontainer.json`:

```json
"customizations": {
  "vscode": {
    "extensions": [
      "existing.extension",
      "your.new-extension"
    ]
  }
}
```

Then rebuild container.

### Adding New Features

Edit `.devcontainer/devcontainer.json`:

```json
"features": {
  "existing-feature": {},
  "ghcr.io/devcontainers/features/new-feature:1": {}
}
```

Browse available features: https://containers.dev/features

### Environment Variables

**All environment variables are managed via `.env` files** (gitignored):

```bash
# Edit backend/.env for development/production settings
nano backend/.env

# Edit backend/tests/.env.test for test settings
nano backend/tests/.env.test
```

Templates are provided:
- `backend/.env.example` - Template for development environment
- `backend/tests/.env.test.example` - Template for test environment

The post-create script automatically creates these files from templates if they don't exist.

## 🔒 Security Considerations

### Development Secrets

- **Never commit real secrets** to `.env` files (they are gitignored)
- Template files (`.env.example`) contain placeholder values only
- Default values in templates are for **local development only**
- Production secrets must be managed separately via environment variables

### Supabase Credentials

Local Supabase credentials are obtained by running `npx supabase start`:
- Service role key is generated for local instance
- Copy the key from `npx supabase start` output to `backend/.env`
- These credentials are:
  - ✅ Safe for local development
  - ✅ Only valid for local Supabase instance
  - ❌ Never used in production
  - ❌ Not real production secrets

### Production Environment

Production deployments use entirely different credentials from environment variables, never from devcontainer.json.

## 📚 Resources

### Development Containers
- [Dev Containers Specification](https://containers.dev/)
- [VS Code Dev Containers](https://code.visualstudio.com/docs/devcontainers/containers)
- [DevPod Documentation](https://devpod.sh/docs)
- [Dev Container CLI](https://github.com/devcontainers/cli)

### Supabase
- [Supabase Local Development](https://supabase.com/docs/guides/cli/local-development)
- [Supabase CLI Reference](https://supabase.com/docs/reference/cli/introduction)

### Docker
- [Docker Documentation](https://docs.docker.com/)
- [Docker Best Practices](https://docs.docker.com/develop/dev-best-practices/)

---

**Remember**: The devcontainer provides a consistent foundation. Keep it simple. Add only what's necessary. Document what you add.
