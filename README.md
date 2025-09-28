# FAIRDatabase

## Project Overview

FAIRDatabase implements **FAIR data principles** for research data management:

- **F**indable: Persistent identifiers and rich metadata
- **A**ccessible: Clear retrieval protocols
- **I**nteroperable: Standard formats and vocabularies
- **R**eusable: Licenses and provenance

A simple, pragmatic web interface for researchers to manage and share data following FAIR principles.

## Technology Stack

- **Backend**: Python/Flask (may migrate to FastAPI)
- **Database**: Supabase (PostgreSQL)
- **Frontend**: HTML templates with static assets
- **Testing**: pytest framework
- **Package Management**: uv with pyproject.toml

## Development Environment Setup

This project uses **Development Containers** for consistent, reproducible development following FAIR principles.

### Prerequisites
- Git
- Container runtime (Docker, Podman, or compatible)
- Development tool of choice (see methods below)

### Setup Methods

#### 1. VS Code + Dev Containers
**Best for:** Full IDE experience with debugging and extensions
**Requirements:** VS Code + [Dev Containers extension](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers)

```bash
git clone https://github.com/seijispieker/FAIRDatabase.git
cd FAIRDatabase
code .
```
Click "Reopen in Container" when prompted. First build ~5-10 minutes.

#### 2. devcontainer CLI
**Best for:** Terminal workflows, automation, CI/CD
**Requirements:** Node.js

```bash
# Install CLI
npm install -g @devcontainers/cli

# Start container
devcontainer up --workspace-folder .

# Enter container
devcontainer exec --workspace-folder . bash
```

#### 3. Podman (Docker Alternative)
**Best for:** Rootless containers, enhanced security
**Requirements:** Podman installed

```bash
# Enable Docker compatibility
systemctl --user enable podman.socket
alias docker=podman

# Use with devcontainer CLI or VS Code
DOCKER_HOST=unix://$XDG_RUNTIME_DIR/podman/podman.sock code .
```

#### 4. GitHub Codespaces
**Best for:** Zero local setup, instant start
**Requirements:** GitHub account (120-180 hours free/month)

[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://github.com/codespaces/new?hide_repo_select=true&ref=main&repo=seijispieker%2FFAIRDatabase)

#### 5. code-server (Self-Hosted)
**Best for:** VS Code in browser, team environments
**Requirements:** Server or local machine with Docker

```bash
# Quick start
docker run -it --init -p 8080:8080 \
  -v "$(pwd):/home/coder/project" \
  -v "/var/run/docker.sock:/var/run/docker.sock" \
  codercom/code-server:latest
```

## What's Included

Your development environment comes pre-configured with:

- **Python 3.13** - Latest Python version with uv package manager
- **Node.js** - For frontend tooling and package management
- **Supabase** - Local PostgreSQL database with authentication
- **Development Tools**:
  - `uv` - Fast Python package manager
  - `ruff` - Python linter and formatter
  - GitHub CLI - Repository management
  - Docker-in-Docker - Container operations

## Running the Application

Once your environment is ready:

```bash
# Navigate to backend
cd backend

# Install dependencies (if needed)
uv sync --all-groups

# Start Flask application
uv run python app.py
```

The application will be available at:
- **Flask Backend**: http://localhost:5000
- **Supabase Studio**: http://localhost:54321
- **API Gateway**: http://localhost:54323

## Troubleshooting

### Common Issues

#### Container Won't Start
```bash
# Check Docker/Podman is running
docker version

# Clean and rebuild
docker system prune -a
devcontainer rebuild --workspace-folder .
```

#### Port Already in Use
```bash
# Find process using port (Linux/macOS)
lsof -i :5000

# Change port in .devcontainer/devcontainer.json
"forwardPorts": [5001, 54321, 54323]
```

#### Permission Denied
```bash
# Linux: Add user to docker group
sudo usermod -aG docker $USER
newgrp docker

# Fix file permissions
sudo chown -R $(id -u):$(id -g) .
```

#### Slow Performance
- **macOS**: Use OrbStack or Colima instead of Docker Desktop
- **Windows**: Clone repo inside WSL2, not Windows filesystem
- **All platforms**: Increase Docker resources in settings

#### Supabase Won't Start
```bash
npx supabase stop --no-backup
npx supabase start
```

#### Quick Diagnostics
```bash
# System info
docker info | grep -E "CPUs|Total Memory"
docker system df

# Container logs
docker ps -a
docker logs <container-id>

# Test services
curl http://localhost:5000       # Flask
curl http://localhost:54321      # Supabase
```

## Getting Help

- **Found a bug?** Open an issue on [GitHub](https://github.com/seijispieker/FAIRDatabase/issues)
- **Questions?** Review the [Dev Containers Documentation](https://containers.dev/)