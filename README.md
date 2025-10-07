# FAIRDatabase

## Project Overview

FAIRDatabase: A FAIR-compliant database for human microbiome research data, balancing **FAIR principles** (Findable, Accessible, Interoperable, Reusable) with GDPR privacy requirements.

## Technology Stack

- **Backend**: Flask/Python
- **Database**: Supabase (PostgreSQL)
- **Frontend**: HTML templates + static assets
- **Testing**: pytest
- **Package Manager**: uv

## Development Environment Setup

This project uses **[Development Containers](https://containers.dev/)** for consistent, reproducible development environments.

### Development Methods

Choose your preferred method. Each takes approximately **2-3 minutes** to set up, plus **~5 minutes** for first-time Supabase initialization.

| Method | Description | What You Need |
|--------|-------------|---------------|
| **[1. GitHub Codespaces](#1-github-codespaces)** | Cloud-based development environment in your browser or VS Code | GitHub account only |
| **[2. VS Code Dev Containers](#2-vs-code-dev-containers)** | Use a container as a full-featured development environment | VS Code + Docker/Podman¹ |
| **[3. DevPod](#3-devpod)** | Reproducible dev environments with IDE choice and provider flexibility | DevPod + Docker/Podman¹ |
| **[4. Dev Container CLI](#4-dev-container-cli)** | Command-line tool to build and manage dev containers | Node.js + Docker/Podman¹ |

¹ **Need a Container Runtime?** Popular options include:
- **macOS/Windows:** [Docker Desktop](https://docs.docker.com/get-docker/), [Rancher Desktop](https://rancherdesktop.io/), [OrbStack](https://orbstack.dev/), [Colima](https://github.com/abiosoft/colima)
- **Linux:** [Docker Engine](https://docs.docker.com/engine/install/), [Podman](https://podman.io/)
- **All Platforms:** [Podman](https://podman.io/), [Finch](https://github.com/runfinch/finch)

### 1. GitHub Codespaces

Free tier: 120-180 hours/month

[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/seijispieker/FAIRDatabase)

Click the badge above. That's it!

### 2. VS Code Dev Containers

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

# 3. Run tests
uv run pytest
```

### Access Points

| Service | URL | Description |
|---------|-----|-------------|
| Flask App | http://localhost:5000 | Main application |
| Supabase Studio | http://localhost:54321 | Database management UI |
| Inbucket | http://localhost:54324 | Email testing interface |

## Testing

### Application Tests (pytest)

Run Python unit and integration tests:

```bash
cd backend
uv run pytest                    # Run all tests
uv run pytest tests/dashboard/   # Run specific test suite
uv run pytest -v                 # Verbose output
```

### Database Tests (pgTAP)

Run database-level tests for schema, RLS policies, and RPC functions:

```bash
# Run all database tests (58 tests)
npx supabase test db

# Reset database and run tests
npx supabase db reset && npx supabase test db
```

**What's tested:**
- Schema structure (`_realtime` schema, `metadata_tables` table)
- Row-level security (RLS) policies and permissions
- All 11 RPC functions with signature and functionality validation

See [`supabase/CLAUDE.md`](supabase/CLAUDE.md#database-testing-with-pgtap) for detailed test documentation.

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

**Reset Database (when Supabase is running)**
```bash
npx supabase db reset
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