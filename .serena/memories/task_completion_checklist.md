# Task Completion Checklist

## Commands to Run When Task is Completed

When you complete a coding task in the FAIRDatabase project, you MUST run these commands to ensure code quality:

### 1. Run Tests
```bash
cd backend
uv run pytest
```

### 2. Run Linter
```bash
cd backend
uv run ruff check .
```

### 3. Format Code
```bash
cd backend
uv run ruff format .
```

### 4. Type Checking (if configured)
```bash
cd backend
uv run mypy src/
```

## Development Checklist

### Before Starting Development
- [ ] Read root CLAUDE.md for project-wide conventions
- [ ] Understand the simplest solution first
- [ ] Check if feature already exists
- [ ] Question if the feature is needed (YAGNI)

### While Developing
- [ ] Start with the simplest working solution
- [ ] Add complexity only when proven necessary
- [ ] Follow PEP 8 and project conventions
- [ ] Add type hints to functions
- [ ] Write simple docstrings (Google style)
- [ ] Keep functions under 50 lines
- [ ] Handle errors explicitly
- [ ] Validate inputs at boundaries

### Before Committing
- [ ] Run tests: `uv run pytest`
- [ ] Run linter: `uv run ruff check .`
- [ ] Format code: `uv run ruff format .`
- [ ] Type check: `uv run mypy src/` (if applicable)
- [ ] Ensure no secrets in code
- [ ] Question: "Can this be simpler?"

### Security Checklist
- [ ] No hardcoded credentials
- [ ] Inputs validated with Pydantic or forms
- [ ] SQL queries use parameterization
- [ ] Passwords hashed with bcrypt
- [ ] Authentication required for protected endpoints
- [ ] Use timezone-aware datetimes

## Important Notes
- **Always use `uv` for package management** - Never use pip directly
- **Work from backend directory** when running Python commands
- **Follow the progressive complexity rule** - Start simple, add complexity only when proven necessary
- **If tests fail or linting errors occur**, fix them before considering the task complete