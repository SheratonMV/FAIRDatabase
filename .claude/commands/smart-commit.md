# Smart Git Commit

## Automated Conventional Commits for FAIRDatabase

Analyzes changes and creates atomic, conventional commits following project standards.

## Quick Analysis
```bash
# Current state
git branch --show-current
git status --porcelain
git diff --stat

# Recent patterns
git log --oneline -5
```

## Commit Strategy

### Conventional Format (Aligned with CLAUDE.md)
```
<type>(<scope>): <subject>

<body>

<footer>
```

**Types**: feat, fix, docs, style, refactor, test, chore

### Change Classification
1. **Group related files**:
   - Implementation + tests → single commit
   - API endpoint + schema → single commit
   - Keep docs separate unless tightly coupled

2. **Scope identification**:
   - backend, frontend, api, auth, db
   - Use file path as guide

3. **Breaking changes**:
   - API contract changes
   - Schema modifications
   - Removed features
   - Mark with ! or BREAKING CHANGE:

## Branch Management

### Per CLAUDE.md Guidelines
- **Current branch check**: Never commit directly to `main`
- **Feature branches**: `feature/*`, `fix/*`, `refactor/*`, `test/*`
- **Fork workflow**: Always work in `seijispieker/FAIRDatabase`

### Auto-branch creation
```bash
# If on main/develop, create feature branch
if [[ $(git branch --show-current) =~ ^(main|develop)$ ]]; then
  git checkout -b feature/<descriptive-name>
fi
```

## Implementation Steps

### 1. Analyze Changes
```bash
# List all changes
git status --porcelain

# Group by directory
git diff --name-only | sed 's|/[^/]*$||' | sort -u
```

### 2. Create Atomic Commits
For each logical group:
```bash
# Stage related files
git add <related-files>

# Commit with conventional message
git commit -m "<type>(<scope>): <description>"
```

### 3. Message Guidelines
- **Subject**: Imperative, <50 chars, no period
- **Body**: Why not how, wrap at 72 chars
- **Footer**: Issue refs, breaking changes

## Examples

### Single Feature
```bash
git add backend/src/auth.py backend/tests/test_auth.py
git commit -m "feat(auth): add JWT token validation

Implements token validation middleware for API endpoints
following FAIR authentication principles"
```

### Multiple Changes
```bash
# Backend fix
git add backend/src/api/users.py
git commit -m "fix(backend): correct user validation regex"

# Frontend update
git add frontend/templates/dashboard.html
git commit -m "feat(frontend): add user metrics display"

# Documentation
git add docs/api.md
git commit -m "docs: update API endpoint documentation"
```

### Breaking Change
```bash
git add backend/src/api/* migrations/*
git commit -m "feat(api)!: restructure response format

BREAKING CHANGE: API responses now use envelope pattern
Migration required for existing clients"
```

## Automation Logic

### Smart Grouping
- Detect test files → group with implementation
- Detect migration → separate commit
- Detect config changes → separate commit
- Detect docs → evaluate coupling

### Commit Order
1. Dependencies/configs first
2. Core implementation
3. Tests
4. Documentation

### Quality Checks
- No secrets in commits
- No debug code
- Files properly grouped
- Message follows convention

## Post-Commit

Display summary:
```bash
git log --oneline -n <number-of-commits>
echo "Ready to push: git push -u origin $(git branch --show-current)"
```

**Note**: Testing handled by CI/CD pipeline, not pre-commit.