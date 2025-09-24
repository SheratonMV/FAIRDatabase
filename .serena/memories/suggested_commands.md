# Suggested Commands for FAIRDatabase Development

## Package Management (Always use uv)
```bash
# Navigate to backend directory first
cd backend

# Sync all dependencies (including dev)
uv sync --all-groups

# Sync only production dependencies  
uv sync

# Add production dependencies
uv add <package-name>

# Add development dependencies
uv add --group dev <package-name>

# Remove dependencies
uv remove <package-name>

# Update all dependencies
uv sync --upgrade

# List installed packages
uv pip list

# Run commands in virtual environment
uv run python app.py
uv run pytest
```

## Running the Application
```bash
cd backend
uv sync --all-groups  # Install dependencies if needed
uv run python app.py  # Start Flask application
```

## Testing Commands
```bash
cd backend
uv run pytest                    # Run all tests
uv run pytest -v                  # Verbose output
uv run pytest tests/auth         # Run specific test directory
uv run pytest -m "not slow"      # Skip slow tests
uv run pytest --cov              # With coverage
```

## Code Quality Commands
```bash
cd backend
uv run ruff check .              # Run linter
uv run ruff format .             # Format code
uv run mypy src/                 # Type checking
```

## Supabase Commands
```bash
npx supabase start               # Start local Supabase
npx supabase stop                # Stop Supabase
npx supabase status              # Check status
npx supabase db reset            # Reset database
```

## Git Commands (Linux system)
```bash
git status
git add .
git commit -m "message"
git push origin <branch>
git checkout -b <new-branch>
```

## System Utilities (Linux)
```bash
ls -la                           # List files with details
grep -r "pattern" .              # Recursive search
find . -name "*.py"              # Find Python files
cd <directory>                   # Change directory
pwd                              # Print working directory
```

## Important Notes
- **NEVER use pip directly** - Always use uv for package management
- Always work from the backend directory when running Python commands
- The virtual environment (.venv) is auto-managed by uv