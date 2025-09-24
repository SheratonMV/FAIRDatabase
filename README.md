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

Choose one of the following methods to set up your development environment:

**Note:** First-time setup takes 5-10 minutes to download all tools, dependencies, and Docker images. Subsequent starts are much faster.

### Option 1: VS Code with Dev Container (Recommended)

The easiest way to get started with a full-featured development environment.

**Prerequisites:**
- Docker Desktop or Docker Engine
- Git
- [Visual Studio Code](https://code.visualstudio.com/)
- [Dev Containers extension](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers)

1. **Clone and Open**
   ```bash
   git clone https://github.com/seijispieker/FAIRDatabase.git
   cd FAIRDatabase
   ```
   Open the folder in VS Code (File → Open Folder)

2. **Start Development Environment**
   - VS Code will detect the dev container configuration
   - Click **"Reopen in Container"** when prompted
   - Wait for the container to build (first time: ~5-10 minutes)
   - The terminal will show when Supabase is ready

### Option 2: GitHub Codespaces (Cloud-Based)

No local setup required - develop entirely in the browser.

**Prerequisites:** None - just a GitHub account

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

**Prerequisites:**
- Docker Desktop or Docker Engine
- Git
- Node.js and npm (for DevContainer CLI installation)

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

- **Minimum requirements not met:** Container requires 2 CPUs, 2GB RAM, and 8GB storage
- **Container issues:** Ensure Docker is running (`docker version`)
- **Supabase not accessible:** Restart services (`npx supabase stop && npx supabase start`)
- **Port conflicts:** Check for services using the same port (`lsof -i :5000`)