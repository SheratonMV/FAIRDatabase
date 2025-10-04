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

**Container Runtime** (location depends on your setup method):
- **Local development**: Install on your machine - [Docker Desktop](https://docs.docker.com/get-docker/) (Windows/macOS), [Docker Engine](https://docs.docker.com/engine/install/) (Linux), or alternatives like [Podman](https://podman.io/), [Rancher Desktop](https://rancherdesktop.io/), [Colima](https://github.com/abiosoft/colima)
- **Remote development**: Container runtime must be installed on the remote machine (not locally)
- **GitHub Codespaces**: No container runtime needed (fully cloud-based)

Choose your setup method:

| Method | Best For | Remote Support | Prerequisites |
|--------|----------|----------------|---------------|
| **GitHub Codespaces** | Instant start, zero setup | ☁️ Cloud-native | GitHub account |
| **VS Code + Dev Containers** | Full IDE with debugging | ✅ Via Remote-SSH | VS Code + container runtime (local or remote) |
| **DevPod** | GUI + multi-backend flexibility | ✅ SSH/K8s/Cloud | DevPod + container runtime (local or remote) |
| **DevContainer CLI** | Terminal workflows, CI/CD | ✅ Via Docker context | Node.js 20+ + container runtime (local or remote) |

### GitHub Codespaces
**Best for:** Instant start without installing anything locally

**Prerequisites:**
- GitHub account (120-180 free hours/month)

**Setup:**

[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/seijispieker/FAIRDatabase)

Click the badge above. Your environment will be ready in ~2-3 minutes.

### VS Code Dev Containers
**Best for:** Full-featured IDE with debugging, extensions, and IntelliSense
**Default:** Local development (supports remote via SSH/WSL/tunnels)

**Additional Prerequisites:**
- **For local:** VS Code with [Dev Containers extension](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers)
- **For remote:** VS Code with [Remote Development extension pack](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.vscode-remote-extensionpack) (includes Dev Containers + Remote-SSH/Tunnels/WSL)

**Quick Start (Local):**

```bash
git clone https://github.com/seijispieker/FAIRDatabase.git
cd FAIRDatabase
code .
```

Click "Reopen in Container" when prompted. First build takes ~5-10 minutes.

**Remote Development:** VS Code Dev Containers works on remote hosts via SSH, tunnels, or WSL. See [VS Code Remote Development docs](https://code.visualstudio.com/docs/remote/remote-overview) for setup.

**Learn More:** [Dev Containers Documentation](https://code.visualstudio.com/docs/devcontainers/containers)

### DevPod
**Best for:** Multi-backend flexibility (local/remote/cloud) with GUI or CLI, works with any IDE
**Default:** Local development (easily switch to remote/cloud providers)

**Additional Prerequisites:**
- [DevPod Desktop or CLI](https://devpod.sh/docs/getting-started/install) installed

**Quick Start (Local):**

```bash
# CLI
devpod provider add docker
devpod up github.com/seijispieker/FAIRDatabase
devpod ide use vscode

# Or use DevPod Desktop GUI:
# 1. Add Docker provider
# 2. Create workspace from: github.com/seijispieker/FAIRDatabase
# 3. Select your IDE
```

**Remote/Cloud:** DevPod supports SSH, Kubernetes, AWS, Azure, GCP and more. See [DevPod Providers](https://devpod.sh/docs/managing-providers/add-provider) for setup.

**Learn More:** [DevPod Documentation](https://devpod.sh/docs/what-is-devpod) | [Creating Workspaces](https://devpod.sh/docs/developing-in-workspaces/create-a-workspace)

### DevContainer CLI
**Best for:** Automation, CI/CD, terminal-only workflows, or non-VS Code editors
**Default:** Local development (supports remote via Docker contexts)

**Additional Prerequisites:**
- [Node.js 20+](https://nodejs.org/en/download)

**Quick Start (Local):**

```bash
# Install
npm install -g @devcontainers/cli

# Clone and start
git clone https://github.com/seijispieker/FAIRDatabase.git
cd FAIRDatabase
devcontainer up --workspace-folder .

# Execute commands in container
devcontainer exec --workspace-folder . bash
```

**Remote Development:** Works with Docker contexts to target remote hosts. See [Docker contexts](https://docs.docker.com/engine/context/working-with-contexts/) for setup.

**Learn More:** [DevContainer CLI Reference](https://github.com/devcontainers/cli) | [VS Code DevContainer CLI](https://code.visualstudio.com/docs/devcontainers/devcontainer-cli)

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
# Start Supabase (required first time and after container restart)
npx supabase start

# Navigate to backend
cd backend

# Install dependencies (if needed)
uv sync --all-groups

# Start Flask application
uv run flask run
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
- **macOS**: Use Rancher Desktop or Colima instead of Docker Desktop
- **Windows**: Clone repo inside WSL2, not Windows filesystem
- **All platforms**: Increase Docker resources in settings

#### Supabase Won't Start
```bash
npx supabase stop --no-backup
npx supabase start
```

#### Remote Setup Issues

These issues apply when using any remote development method (VS Code Remote-SSH, DevPod, Docker context):

**SSH Connection Fails**
```bash
# Test SSH connection first
ssh user@remote-server.com

# Enable verbose logging
ssh -v user@remote-server.com

# Check SSH key permissions
chmod 600 ~/.ssh/id_rsa
chmod 644 ~/.ssh/id_rsa.pub
```

**Remote Container Won't Start**
```bash
# Verify Docker is running on remote
ssh user@remote-server.com "docker version"

# Check remote Docker permissions
ssh user@remote-server.com "docker ps"

# Add remote user to docker group (on remote machine)
ssh user@remote-server.com "sudo usermod -aG docker $USER"
```

**Port Forwarding Not Working**
```bash
# Check port forwarding in your tool (VS Code Ports panel, DevPod settings, etc.)
# Or manually forward via SSH
ssh -L 5000:localhost:5000 user@remote-server.com
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

# Remote diagnostics
ssh user@remote "docker ps"
ssh user@remote "docker logs <container-id>"
```

## Getting Help

- **Found a bug?** Open an issue on [GitHub](https://github.com/seijispieker/FAIRDatabase/issues)
- **Questions?** Review the [Dev Containers Documentation](https://containers.dev/)