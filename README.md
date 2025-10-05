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

Choose your development method, then install only what's needed:

| Method | Required Prerequisites | Optional |
|--------|----------------------|----------|
| **GitHub Codespaces** | GitHub account | - |
| **VS Code Dev Containers** | VS Code + Dev Containers extension + Container runtime¹ | - |
| **DevPod** | DevPod + Container runtime¹ | - |
| **Dev Container CLI** | Node.js 20+ + Container runtime¹ | - |
| **Local Development** | Python 3.13+ + Node.js 20+ + PostgreSQL | Container runtime¹ |

¹ **Container Runtime Options**:
- **macOS/Windows**: [Docker Desktop](https://docs.docker.com/get-docker/), [Rancher Desktop](https://rancherdesktop.io/), [Podman Desktop](https://podman.io/)
- **Linux**: [Docker Engine](https://docs.docker.com/engine/install/), [Podman](https://podman.io/)
- **Remote**: Install on remote machine (not locally) when using SSH/remote development

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

### Dev Container CLI
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

**Remote Development:** Works with Docker contexts to target remote hosts (via Docker's context system; not explicitly documented in CLI docs). See [Docker contexts](https://docs.docker.com/engine/context/working-with-contexts/) for setup.

**Learn More:** [Dev Container CLI GitHub](https://github.com/devcontainers/cli) | [VS Code DevContainer CLI](https://code.visualstudio.com/docs/devcontainers/devcontainer-cli)

## What's Included

Your development environment comes pre-configured with:

- **Python 3.13** - Latest Python version with uv package manager
- **Node.js 20+** - For frontend tooling and package management
- **Supabase** - Local PostgreSQL database with authentication
- **Development Tools**:
  - `uv` - Fast Python package manager
  - `ruff` - Python linter and formatter
  - GitHub CLI - Repository management
  - Docker-in-Docker - Container operations

## Running the Application

### Quick Start

```bash
# 1. Start Supabase (first time takes ~2 minutes)
npx supabase start

# Note the Anon Key and Service Key shown in output
# Default credentials will be displayed in the terminal

# 2. Setup backend
cd backend
uv sync --all-groups              # Install dependencies

# 3. Start application
uv run flask run --debug
```

### Access Points

| Service | URL | Description |
|---------|-----|-------------|
| Flask App | http://localhost:5000 | Main application |
| Supabase Studio | http://localhost:54321 | Database management UI |
| API Gateway | http://localhost:54323 | Supabase API endpoint |
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
docker version                                    # Verify Docker is running
docker stop $(docker ps -aq) 2>/dev/null || true  # Stop all containers
docker system prune -af --volumes                 # Remove containers, images, volumes, networks
docker builder prune -af                          # Remove ALL build cache

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
lsof -i :5000                                     # Find process using port
# Change port in .devcontainer/devcontainer.json: "forwardPorts": [5001, 54321, 54323]
```

### Service Issues

**Supabase Won't Start**
```bash
npx supabase stop --no-backup && npx supabase start
```

**Flask/Backend Issues**
```bash
docker logs <container-id>                        # Check container logs
curl http://localhost:5000                        # Test Flask
curl http://localhost:54321                       # Test Supabase
```

### Performance

- **macOS**: Use Rancher Desktop or Colima instead of Docker Desktop
- **Windows**: Clone repo inside WSL2, not Windows filesystem
- **All**: Increase Docker resources (Memory/CPU) in settings

### Remote Development

**Connection Issues**
```bash
ssh user@remote-server.com                        # Test SSH connection
ssh user@remote "docker version"                  # Verify remote Docker
ssh user@remote "sudo usermod -aG docker $USER"   # Fix remote permissions
```

**Port Forwarding**
```bash
ssh -L 5000:localhost:5000 user@remote-server.com # Manual port forward
# Or use your tool's port forwarding (VS Code Ports panel, DevPod settings)
```

## Getting Help

- **Found a bug?** Open an issue on [GitHub](https://github.com/seijispieker/FAIRDatabase/issues)
- **Questions?** Review the [Dev Containers Documentation](https://containers.dev/)