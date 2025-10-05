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

### Application Configuration

```json
"containerEnv": {
  "ENV": "development",
  "SECRET_KEY": "dev-secret-key-change-in-production",
  "FLASK_RUN_HOST": "0.0.0.0",
  "UPLOAD_FOLDER": "./uploads"
}
```

**IMPORTANT**: These are development-only values. Never use these in production.

### Supabase Configuration

```json
"containerEnv": {
  "SUPABASE_URL": "http://127.0.0.1:54321",
  "SUPABASE_SERVICE_ROLE_KEY": "sb_secret_N7UND0UgjKTVK-Uodkm0Hg_xSvEMPvz",
  "POSTGRES_HOST": "127.0.0.1",
  "POSTGRES_PORT": "54322",
  "POSTGRES_USER": "postgres",
  "POSTGRES_SECRET": "postgres",
  "POSTGRES_DB_NAME": "postgres"
}
```

These are the default local Supabase credentials. The service role key is from Supabase's local development defaults.

### Key Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `ENV` | Application environment | `development` |
| `SECRET_KEY` | Flask session secret | Dev-only key |
| `FLASK_RUN_HOST` | Flask bind address | `0.0.0.0` (all interfaces) |
| `SUPABASE_URL` | Local Supabase instance | `http://127.0.0.1:54321` |
| `POSTGRES_HOST` | PostgreSQL host | `127.0.0.1` |
| `POSTGRES_PORT` | PostgreSQL port | `54322` |

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
- `redhat.vscode-yaml` - YAML language support
- `mikestead.dotenv` - .env file support

## 📦 Post-Creation Setup

### Lifecycle Script

```json
"postCreateCommand": "bash .devcontainer/post-create.sh"
```

The `post-create.sh` script runs automatically after container creation:

```bash
#!/bin/bash
# Install Python dependencies
cd backend
uv sync --all-groups

# Note: Supabase is started manually with `npx supabase start`
```

### Manual Setup Steps

After container starts:

```bash
# 1. Start Supabase (first time takes ~5 minutes to download images)
npx supabase start

# 2. Start Flask application
cd backend
uv run flask run --debug

# 3. Access application at http://localhost:5000
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
# Then:

# 1. Start Supabase
npx supabase start

# 2. Start Flask
cd backend
uv run flask run --debug
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

For development-specific environment variables, edit `.devcontainer/devcontainer.json`:

```json
"containerEnv": {
  "YOUR_VAR": "your_value"
}
```

For personal/secret values, create `.env` file (gitignored):

```bash
# backend/.env
SECRET_KEY=your-personal-secret
```

## 🔒 Security Considerations

### Development Secrets

- **Never commit real secrets** to devcontainer.json
- Default values are for **local development only**
- Production secrets must be managed separately

### Supabase Credentials

The service role key in devcontainer.json is Supabase's well-known local development default. It's:
- ✅ Safe for local development
- ✅ Publicly documented
- ❌ Never used in production
- ❌ Not a real secret

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
