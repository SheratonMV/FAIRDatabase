# FAIRDatabase DevContainer

Development container for FAIRDatabase with comprehensive tooling and Supabase support.

## Quick Start

### Prerequisites
- Docker Desktop or Docker Engine
- VS Code with Remote-Containers extension (optional)
- DevContainer CLI (optional): `npm install -g @devcontainers/cli`

### Using VS Code
1. Open the project in VS Code
2. When prompted, click "Reopen in Container"
3. Wait for the container to build and start

### Using DevContainer CLI

```bash
# Build the container
devcontainer build --workspace-folder .

# Start the container
devcontainer up --workspace-folder .

# Execute commands in the container
devcontainer exec --workspace-folder . bash
```

### Using Docker Directly

```bash
# Run the validation script to check setup
bash .devcontainer/scripts/validate-setup.sh

# Run Python in the container
docker run --rm -v $(pwd):/workspace -w /workspace \
  mcr.microsoft.com/devcontainers/python:3.13 python --version
```

## Features

The devcontainer includes:
- **Python 3.13** - Latest Python version
- **Docker-in-Docker** - For running Supabase locally
- **Node.js** - For frontend tooling and Supabase CLI
- **UV** - Fast Python package manager
- **GitHub CLI** - For repository operations
- **Ruff** - Python linter/formatter
- **Ripgrep** - Fast search tool

## Configuration Files

- `devcontainer.json` - Main configuration with all features
- `devcontainer-simple.json` - Simplified configuration for quick testing
- `scripts/validate-setup.sh` - Comprehensive validation script
- `scripts/postCreate.sh` - Initial setup script
- `scripts/postStart.sh` - Service initialization script

## Validation Script

Run the validation script to verify your setup:

```bash
bash .devcontainer/scripts/validate-setup.sh
```

This checks:
- Docker and DevContainer CLI installation
- Configuration file validity
- Required project files
- Container image accessibility
- Python environment

## Port Forwarding

The following ports are automatically forwarded:
- **5000** - Flask Backend API
- **54321** - Supabase Studio (browser UI)
- **54323** - Supabase Kong API Gateway

## Development Workflow

### Initial Setup
```bash
# The container runs these automatically:
# 1. Installs Node dependencies
# 2. Installs Supabase CLI
# 3. Sets up Python environment
# 4. Creates .env from sample

# Start Supabase (if not already running)
npx supabase start

# Run Flask backend
cd backend
python app.py
```

### Common Commands

```bash
# Python development
cd backend
uv pip install -r requirements.txt
uv pip install -r requirements-dev.txt
pytest

# Linting and formatting
ruff check .
ruff format .

# Supabase management
npx supabase status
npx supabase stop
npx supabase start

# Git operations
git status
git add .
git commit -m "message"
```

## Troubleshooting

### Build Timeout
If the full devcontainer build times out:
1. Use the simplified configuration:
   ```bash
   devcontainer build --config .devcontainer/devcontainer-simple.json
   ```
2. Build features incrementally
3. Increase timeout: `timeout 300 devcontainer build ...`

### Line Ending Issues
If scripts fail with `\r` errors:
```bash
# Fix line endings
dos2unix .devcontainer/scripts/*.sh
# or
sed -i 's/\r$//' .devcontainer/scripts/*.sh
```

### Permission Issues
Ensure scripts are executable:
```bash
chmod +x .devcontainer/scripts/*.sh
```

### Container Won't Start
1. Check Docker is running: `docker version`
2. Pull base image manually: `docker pull mcr.microsoft.com/devcontainers/python:3.13`
3. Check disk space: `docker system df`
4. Clean up if needed: `docker system prune -a`

## Testing the Setup

### Quick Container Test
```bash
# Test with simplified config (builds faster)
devcontainer build --workspace-folder . \
  --config .devcontainer/devcontainer-simple.json

# Run a command in the container
docker run --rm vsc-fairdatabase-*-features python --version
docker run --rm vsc-fairdatabase-*-features ruff --version
```

### Full Integration Test
```bash
# Build and start the full container
devcontainer up --workspace-folder .

# In another terminal, exec into it
devcontainer exec --workspace-folder . bash -c "
  python --version &&
  ruff --version &&
  npx supabase --version &&
  echo 'All tools working!'
"
```

## Files Created

The devcontainer setup creates/modifies:
- `package.json` - Node.js dependencies (Supabase CLI)
- `backend/requirements-dev.txt` - Python development dependencies
- `.env` - Environment variables (from .env.sample)

## Security Notes

- Never commit `.env` files
- The container runs as `vscode` user, not root
- Git safe directory is configured automatically
- All tools are from official sources

## Performance Tips

- First build takes 2-5 minutes depending on internet speed
- Subsequent starts are much faster (cached layers)
- Use `devcontainer-simple.json` for quick iterations
- Consider using Docker BuildKit for faster builds

## Support

If you encounter issues:
1. Run the validation script
2. Check the troubleshooting section
3. Review Docker logs: `docker logs <container-id>`
4. Ensure all prerequisites are installed