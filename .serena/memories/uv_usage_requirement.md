# UV Usage Requirement

Always use `uv` for Python package management and script execution in this project.

## Commands to use:
- `uv run <command>` - Run Python scripts
- `uv add <package>` - Add dependencies
- `uv remove <package>` - Remove dependencies
- `uv sync` - Sync dependencies
- `uv lock` - Lock dependencies

Never use:
- `python3` directly (use `uv run python3` instead)
- `pip` (use `uv add/remove` instead)
