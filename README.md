# FAIRDatabase

A system implementing FAIR data principles (Findable, Accessible, Interoperable, and Reusable) for managing research data.

## Prerequisites

Before setting up the development environment, ensure you have:
- **Docker Desktop** or **Docker Engine** installed
- **Git** for version control
- Additional tools based on your chosen setup method (see below)

## Development Environment Setup

Choose one of the following methods to set up your development environment:

### Option 1: VS Code with Dev Container (Recommended)

The easiest way to get started with a full-featured development environment.

1. **Install Prerequisites**
   - [Visual Studio Code](https://code.visualstudio.com/)
   - [Remote - Containers extension](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers)

2. **Clone and Open**
   ```bash
   git clone https://github.com/seijispieker/FAIRDatabase.git
   cd FAIRDatabase
   code .
   ```

3. **Start Development Environment**
   - VS Code will detect the dev container configuration
   - Click **"Reopen in Container"** when prompted
   - Wait for the container to build (first time: ~5-10 minutes)
   - The terminal will show when Supabase is ready

### Option 2: GitHub Codespaces (Cloud-Based)

No local setup required - develop entirely in the browser.

[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://github.com/codespaces/new?hide_repo_select=true&ref=main&repo=seijispieker%2FFAIRDatabase)

1. **Create a Codespace**
   - Click the button above, or
   - Navigate to the repository on GitHub
   - Click the **Code** button → **Codespaces** tab
   - Click **"Create codespace on main"**

2. **Wait for Setup**
   - The codespace will automatically build and configure everything
   - This includes all dependencies and Supabase initialization
   - You'll have a full VS Code environment in your browser

### Option 3: DevContainer CLI (Command Line)

For developers who prefer command-line workflows.

1. **Install DevContainer CLI**
   ```bash
   npm install -g @devcontainers/cli
   ```

2. **Clone Repository**
   ```bash
   git clone https://github.com/seijispieker/FAIRDatabase.git
   cd FAIRDatabase
   ```

3. **Start and Enter Container**
   ```bash
   # Build and open an interactive shell in the container
   devcontainer up --workspace-folder . && \
   devcontainer exec --workspace-folder . bash
   ```

   Or separately:
   ```bash
   # Build and start the container
   devcontainer up --workspace-folder .

   # Open an interactive shell in the running container
   devcontainer exec --workspace-folder . bash
   ```

## What's Included

Your development environment comes pre-configured with:

- **Python 3.13** - Latest Python version with uv package manager
- **Node.js** - For frontend tooling and package management
- **Supabase** - Local PostgreSQL database with authentication
- **Development Tools**:
  - `uv` - Fast Python package manager
  - `ruff` - Python linter and formatter
  - `ripgrep` - Fast code searching
  - GitHub CLI - Repository management
  - Docker-in-Docker - Container operations

## Getting Started

Once your environment is ready:

### Verify Setup
```bash
# Check Python
python --version

# Check Supabase status
npx supabase status

# Check database connection
npx supabase db reset
```

### Run the Application
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

## Port Information

The following ports are automatically forwarded:

| Port  | Service                    | Description                          |
|-------|----------------------------|--------------------------------------|
| 5000  | Flask Backend API          | Main application API                 |
| 54321 | Supabase Studio            | Database management UI               |
| 54323 | Supabase Kong API Gateway  | API gateway for Supabase services   |

## Development Workflow

### Python Development
```bash
cd backend

# Sync dependencies
uv sync --all-groups

# Run tests
uv run pytest

# Lint code
ruff check .

# Format code
ruff format .

# Run application
uv run python app.py
```

### Supabase Management
```bash
# Check status
npx supabase status

# Reset database
npx supabase db reset

# Stop services
npx supabase stop

# Restart services
npx supabase start
```

## First-Time Setup Notes

⏱️ **Initial Setup Time**: The first container build takes 5-10 minutes as it:
- Downloads all development tools
- Installs Python and Node dependencies
- Downloads Supabase Docker images (~1.5GB)
- Initializes the local database

Subsequent starts are much faster (under a minute).

## Troubleshooting

### Container Won't Start
- Ensure Docker is running: `docker version`
- Check available disk space: `docker system df`
- Try rebuilding: `devcontainer rebuild --workspace-folder .`

### Supabase Not Accessible
- Check if services are running: `npx supabase status`
- Restart services: `npx supabase stop && npx supabase start`
- Check logs: `docker logs supabase-db`

### Port Already in Use
- Check for conflicting services: `lsof -i :5000` (or relevant port)
- Stop conflicting services or change the port in configuration

### Slow Performance
- Increase Docker resource allocation in Docker Desktop settings
- Ensure you have at least 4GB RAM allocated to Docker
- Consider using the simplified devcontainer for faster builds

## Contributing

Please read our contributing guidelines and ensure your development environment is properly configured before submitting pull requests.

## Support

For issues and questions:
- Check the [troubleshooting section](#troubleshooting)
- Review existing [GitHub Issues](https://github.com/seijispieker/FAIRDatabase/issues)
- Create a new issue if your problem persists