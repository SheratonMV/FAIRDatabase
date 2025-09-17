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

## Post-Commit (Automatic Execution)

### Push and Create PR
**This section is automatically executed after commits are created.**

```bash
# Push to fork
git push -u origin $(git branch --show-current)

# Create PR to main branch in fork (NOT original repo)
gh pr create \
  --repo seijispieker/FAIRDatabase \
  --base main \
  --head $(git branch --show-current) \
  --title "<generated from commits>" \
  --body "<summary of changes>"
```

### CRITICAL: Fork Workflow
```bash
# ALWAYS verify you're creating PR in the fork
gh pr list --repo seijispieker/FAIRDatabase

# NEVER create PR to original repository
# ❌ WRONG: gh pr create --repo SheratonMV/FAIRDatabase
# ✅ RIGHT: gh pr create --repo seijispieker/FAIRDatabase
```

### PR Creation Logic
1. **Target repository**: Always `seijispieker/FAIRDatabase`
2. **Base branch**: `main` (in the fork)
3. **Title generation**: From commit messages
4. **Body content**:
   - Summary of changes
   - List of commits
   - Breaking changes if any
   - Testing status

### Example PR Creation
```bash
# After commits are made
current_branch=$(git branch --show-current)
git push -u origin $current_branch

# Generate PR title from last commit or branch name
pr_title=$(git log -1 --pretty=%s)

# Generate PR body from commit messages
pr_body=$(cat <<EOF
## Changes
$(git log main..$current_branch --pretty="- %s")

## Commits
$(git log main..$current_branch --oneline)

---
Created from branch: $current_branch
EOF
)

# Create PR in fork only
gh pr create \
  --repo seijispieker/FAIRDatabase \
  --base main \
  --head $current_branch \
  --title "$pr_title" \
  --body "$pr_body"
```

### Display Summary
```bash
git log --oneline -n <number-of-commits>
echo "Branch pushed to fork: seijispieker/FAIRDatabase"
echo "PR created: $(gh pr view --repo seijispieker/FAIRDatabase --json url -q .url)"
```

**Note**: Testing handled by CI/CD pipeline, not pre-commit.
**IMPORTANT**: PRs are ONLY created within the fork. Never to SheratonMV/FAIRDatabase.