# FAIRDatabase

## Project Overview

FAIRDatabase is a system implementing **FAIR data principles** for managing research data:

- **F**indable: Data has persistent identifiers and rich metadata
- **A**ccessible: Clear protocols for data retrieval and access
- **I**nteroperable: Uses standard formats and vocabularies
- **R**eusable: Includes licenses and provenance information

The project provides a web-based interface for researchers to manage and share their data following these principles.

## Repository Information

- **Working Fork**: [github.com/seijispieker/FAIRDatabase](https://github.com/seijispieker/FAIRDatabase) (current)
- **Original Repository**: [github.com/SheratonMV/FAIRDatabase](https://github.com/SheratonMV/FAIRDatabase)

**Important**: All development should occur in the fork. Never push directly to the original repository.

## Technology Stack

- **Backend**: Python/Flask (may migrate to FastAPI)
- **Database**: Supabase (PostgreSQL)
- **Frontend**: HTML templates with static assets
- **Testing**: pytest framework
- **Package Management**: uv with pyproject.toml

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
   - [Dev Containers extension](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers)

2. **Clone and Open**
   ```bash
   git clone https://github.com/seijispieker/FAIRDatabase.git
   cd FAIRDatabase
   ```
   Open the folder in VS Code (File → Open Folder)

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
  - GitHub CLI - Repository management
  - Docker-in-Docker - Container operations

## Getting Started

Once your environment is ready (see CLAUDE.md for development principles):

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

## Supabase Version Management

### Version Pinning Strategy

This project uses version pinning to ensure consistent development environments:

- **Supabase CLI**: Version `2.40.7` (pinned in `package.json`)
- **Docker Images**: Controlled by the Supabase CLI version
- **Database**: PostgreSQL 17 (configured in `supabase/config.toml`)

The Supabase CLI version determines which Docker image versions are used. Each CLI version pins specific versions of:
- PostgreSQL database
- Supabase Studio
- Auth service
- Storage service
- Realtime service
- Other Supabase components

### Checking Current Versions

```bash
# Check Supabase CLI version
npx supabase --version

# Check running service versions
npx supabase status

# Verify version matches package.json
cat package.json | grep supabase
```

### Updating Supabase Safely

⚠️ **Important**: Always test updates in a development environment first!

#### 1. Check for Updates
```bash
# Check latest available version
npm view supabase version

# Check for breaking changes
# Visit: https://github.com/supabase/cli/releases
```

#### 2. Update Process
```bash
# 1. Stop current services
npx supabase stop

# 2. Backup your local database (if needed)
npx supabase db dump > backup.sql

# 3. Update package.json with new version
npm install --save-dev supabase@latest

# 4. Install the new version
npm install

# 5. Start services with new version
npx supabase start

# 6. Run migrations (if any)
npx supabase db reset

# 7. Test your application thoroughly
```

#### 3. Commit the Changes
```bash
# If everything works, commit the updated versions
git add package.json package-lock.json
git commit -m "chore: update Supabase CLI to version X.Y.Z"
```

### Rollback Procedure

If issues occur after updating:

```bash
# 1. Stop services
npx supabase stop

# 2. Revert package.json and package-lock.json
git checkout HEAD -- package.json package-lock.json

# 3. Reinstall previous version
npm ci

# 4. Restart services
npx supabase start

# 5. Restore database if needed
npx supabase db reset
psql -h localhost -p 54322 -U postgres -d postgres < backup.sql
```

### Version Compatibility

- **Node.js**: Requires version 18 or higher
- **Docker**: Requires Docker Engine 20.10 or higher
- **PostgreSQL**: Version 17 (major version must match remote database)

### Troubleshooting Version Issues

#### Version Mismatch Warning
If you see a version mismatch warning on container startup:
```bash
# Install the correct version from package.json
cd /workspaces/FAIRDatabase
npm install
```

#### Docker Image Updates
Supabase Docker images are updated monthly. To get the latest security patches:
```bash
# Pull latest images for current CLI version
npx supabase stop
docker system prune -a  # Optional: clean old images
npx supabase start
```

## Project Structure

```
FAIRDatabase/
├── backend/           # Flask application (see backend/CLAUDE.md)
│   ├── src/          # Application source code
│   ├── tests/        # Test files
│   └── CLAUDE.md     # Backend-specific conventions
├── frontend/         # Web interface
│   ├── templates/    # HTML templates
│   └── CLAUDE.md     # Frontend-specific conventions
├── supabase/         # Database configuration
│   └── config.toml   # Supabase settings
├── static/           # Static assets
├── .devcontainer/    # Development container config
│   └── CLAUDE.md     # DevContainer documentation
├── .github/          # GitHub workflows
├── package.json      # Node dependencies
├── CLAUDE.md        # Project-wide conventions
└── README.md        # This file
```

## Development Philosophy

**Core Principle: Start simple. Add complexity only when proven necessary.**

This project follows key development principles:
- **KISS** (Keep It Simple): The simplest solution is usually the best
- **YAGNI** (You Aren't Gonna Need It): Build only what's required now
- **DRY** (Don't Repeat Yourself): Single source of truth for knowledge
- **Single Responsibility**: Each component does one thing well
- **Fail Fast**: Detect and report errors immediately

For detailed development guidelines, see [CLAUDE.md](./CLAUDE.md).

## Important Notes

⚠️ **Current Codebase Status**:
- The existing code may not follow all standards defined in CLAUDE.md
- Major refactoring is expected in the future
- When contributing, prioritize following the principles in CLAUDE.md over matching existing patterns
- Check subdirectory CLAUDE.md files for context-specific guidance

## Contributing

1. Read [CLAUDE.md](./CLAUDE.md) for development principles
2. Check relevant subdirectory CLAUDE.md files
3. Follow the Git workflow rules (work in fork only)
4. Ensure your development environment is properly configured
5. Update documentation if your changes affect patterns or workflows

## Support

For issues and questions:
- Check the [troubleshooting section](#troubleshooting)
- Review existing [GitHub Issues](https://github.com/seijispieker/FAIRDatabase/issues)
- Create a new issue if your problem persists
- Consult CLAUDE.md files for development guidelines