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

### Development Methods

Choose based on your setup complexity preference (simplest first). All methods take approximately **2-3 minutes** to set up, plus **~5 minutes** for Supabase on first run.

| Method | Use When You Want | What You Need |
|--------|-------------------|---------------|
| **[1. GitHub Codespaces](#1-github-codespaces)** | Zero local setup, instant cloud development | GitHub account only |
| **[2. VS Code Dev Containers](#2-vs-code-dev-containers)** | Full IDE experience with debugging | VS Code + Docker/Podman¹ |
| **[3. DevPod](#3-devpod)** | Flexibility to use any IDE or backend | DevPod + Docker/Podman¹ |
| **[4. Dev Container CLI](#4-dev-container-cli)** | Terminal-based workflow or CI/CD | Node.js + Docker/Podman¹ |

¹ **Need a Container Runtime?** Choose one:
- **Quick Setup:** [Docker Desktop](https://docs.docker.com/get-docker/) (macOS/Windows) or [Rancher Desktop](https://rancherdesktop.io/) (all platforms)
- **Linux:** [Docker Engine](https://docs.docker.com/engine/install/) (native performance)
- **Alternative:** [Podman](https://podman.io/) (rootless containers, all platforms)

### 1. GitHub Codespaces

**Zero Setup Cloud Development** • Free tier: 120-180 hours/month

[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/seijispieker/FAIRDatabase)

Click the badge above. That's it!

### 2. VS Code Dev Containers

**Full IDE with Debugging** • Works locally or remotely

#### Prerequisites
- [VS Code](https://code.visualstudio.com/)
- [Dev Containers extension](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers)
- Docker or Podman (see table above)

#### Setup
```bash
git clone https://github.com/seijispieker/FAIRDatabase.git
cd FAIRDatabase
code .
```

When prompted, click **"Reopen in Container"**.

#### Remote Options
- **Remote Development:** Install [Remote Development extension pack](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.vscode-remote-extensionpack)
- **More Info:** [VS Code Remote Development Overview](https://code.visualstudio.com/docs/remote/remote-overview)

### 3. DevPod

**Any IDE, Any Backend** • Flexible provider support

#### Prerequisites
- [DevPod](https://devpod.sh/docs/getting-started/install)
- Docker or Podman (see table above)

#### Quick Start
```bash
# Add Docker provider
devpod provider add docker

# Create workspace
devpod up github.com/seijispieker/FAIRDatabase
```

**Using GUI?** DevPod Desktop → Add Docker provider → New Workspace → `github.com/seijispieker/FAIRDatabase`

**Other backends:** SSH, Kubernetes, AWS, Azure, GCP ([docs](https://devpod.sh/docs/managing-providers/add-provider))

### 4. Dev Container CLI

**Terminal Workflows & CI/CD** • No GUI needed

#### Prerequisites
- [Node.js 20+](https://nodejs.org/)
- Docker or Podman (see table above)

#### Setup
```bash
# Install CLI
npm install -g @devcontainers/cli

# Clone and start
git clone https://github.com/seijispieker/FAIRDatabase.git
cd FAIRDatabase
devcontainer up --workspace-folder .

# Enter container
devcontainer exec --workspace-folder . bash
```

#### Remote Options
- Use Docker contexts for remote hosts
- **More Info:** [Dev Container CLI](https://github.com/devcontainers/cli)

## What's Included

Your development environment comes pre-configured with:

- **Python 3.13** - Latest Python version with uv package manager
- **Node.js 22.20** - For frontend tooling and package management
- **Supabase** - Local PostgreSQL database with authentication
- **Development Tools**:
  - `uv` - Fast Python package manager
  - `ruff` - Python linter and formatter
  - GitHub CLI - Repository management
  - Docker-in-Docker - Container operations

## Running the Application

### Quick Start

```bash
# 1. Start Supabase (first time takes ~5 minutes)
npx supabase start

# 2. Start application
cd backend
uv run flask run --debug
```

### Access Points

| Service | URL | Description |
|---------|-----|-------------|
| Flask App | http://localhost:5000 | Main application |
| Supabase Studio | http://localhost:54321 | Database management UI |
| Inbucket | http://localhost:54324 | Email testing interface |

### First Steps

1. Navigate to http://localhost:5000
2. Create an account or login with test user
3. Upload a dataset with FAIR metadata
4. Browse and search existing datasets

## Troubleshooting

### Container Issues

**Container Won't Start**
```bash
docker version  # Verify Docker is running
docker stop $(docker ps -aq) 2>/dev/null || true  # Stop all containers
docker system prune -af --volumes  # Remove containers, images, volumes, networks
docker builder prune -af  # Remove ALL build cache

# Optional: Remove ALL volumes (including named volumes) - WARNING: data loss!
docker volume rm $(docker volume ls -q) 2>/dev/null || true
```

**Permission Denied**

Follow the [official Docker post-install steps](https://docs.docker.com/engine/install/linux-postinstall/#manage-docker-as-a-non-root-user):

```bash
sudo usermod -aG docker $USER
```

Then **log out and log back in** (or restart your container).

**Port Already in Use**
```bash
lsof -i :5000  # Find process using port
# Change port in .devcontainer/devcontainer.json: "forwardPorts": [5001, 54321, 54323]
```

### Service Issues

**Supabase Won't Start**
```bash
npx supabase stop --no-backup && npx supabase start
```

**Flask/Backend Issues**
```bash
docker logs <container-id>  # Check container logs
curl http://localhost:5000  # Test Flask
curl http://localhost:54321  # Test Supabase
```

### Performance

- **macOS**: Use Rancher Desktop or Colima instead of Docker Desktop
- **Windows**: Clone repo inside WSL2, not Windows filesystem
- **All**: Increase Docker resources (Memory/CPU) in settings

### Remote Development

**Connection Issues**
```bash
ssh user@remote-server.com  # Test SSH connection
ssh user@remote "docker version"  # Verify remote Docker
ssh user@remote "sudo usermod -aG docker $USER"  # Fix remote permissions
```

**Port Forwarding**
```bash
ssh -L 5000:localhost:5000 user@remote-server.com  # Manual port forward
# Or use your tool's port forwarding (VS Code Ports panel, DevPod settings)
```

## Getting Help

- **Found a bug?** Open an issue on [GitHub](https://github.com/seijispieker/FAIRDatabase/issues)
- **Questions?** Review the [Dev Containers Documentation](https://containers.dev/)