# Git Atomic Commits & PR Workflow

## Quick Commands

### 1. Start Work (Create Branch)
```bash
# Check current status
git status

# Create and switch to feature branch
git checkout -b feature/description   # For new features
git checkout -b fix/description       # For bug fixes
git checkout -b docs/description      # For documentation
```

### 2. Make Atomic Commits
```bash
# See what changed
git diff

# Stage specific files (atomic grouping)
git add src/component.py tests/test_component.py  # Group implementation + tests
git add README.md docs/                           # Group documentation

# Commit with conventional format
git commit -m "feat(scope): add new functionality"
git commit -m "fix(api): resolve timeout issue"
git commit -m "docs: update installation guide"
```

### 3. Push & Ask Before Creating PR
```bash
# Push to your fork
git push -u origin feature/your-branch

# IMPORTANT: Ask user before creating PR
# Claude Code should say: "Would you like me to create a pull request for these changes?"
# If user says yes, then create PR:
gh pr create \
  --repo seijispieker/FAIRDatabase \
  --base main \
  --title "feat: your feature title" \
  --body "## Summary
- What changed
- Why it changed

Closes #123"
```

## Conventional Commit Types

- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation only
- `style`: Formatting (no code change)
- `refactor`: Code restructuring (no behavior change)
- `test`: Adding tests
- `perf`: Performance improvement
- `ci`: CI/CD changes
- `build`: Build system or dependencies
- `chore`: Maintenance

## Format: `type(scope): subject`

```
feat(auth): add password reset
fix(api): handle null values properly
docs(readme): add setup instructions
refactor(users): simplify validation logic
```

## Atomic Commit Rules

### ✅ DO: One Logical Change
```bash
# Good: Related changes together
git add src/auth.py tests/test_auth.py
git commit -m "feat(auth): implement JWT validation"
```

### ❌ DON'T: Mix Unrelated Changes
```bash
# Bad: Multiple unrelated changes
git add -A
git commit -m "fix stuff and add features"
```

## Branch Naming

Format: `type/issue-description`

- `feature/123-user-authentication`
- `fix/456-null-pointer-error`
- `docs/789-api-documentation`
- `refactor/simplify-validation`

## Pre-Commit Checklist

```bash
# 1. Check you're on the right branch
git branch --show-current

# 2. Review your changes
git diff --staged

# 3. Check for debugging code
git diff --staged | grep -E "console\.|print\(|TODO"

# 4. Run tests
pytest  # or npm test

# 5. Check for secrets
git diff --staged | grep -E "password.*=|token.*=|key.*="
```

## Pull Request Template

```markdown
## Summary
- Brief description of changes

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation

## Testing
- [ ] Tests pass locally
- [ ] Added new tests

## Related Issues
Closes #issue_number
```

## Complete Workflow Example

```bash
# 1. Start from main
git checkout main
git pull origin main

# 2. Create feature branch
git checkout -b feature/add-user-validation

# 3. Make changes and commit atomically
git add src/validation.py tests/test_validation.py
git commit -m "feat(validation): add email format check"

git add src/models.py
git commit -m "feat(models): add validation to User model"

# 4. Push to fork
git push -u origin feature/add-user-validation

# 5. Ask before creating PR
# Claude Code: "Would you like me to create a pull request for these changes?"
# If user says yes:
gh pr create \
  --repo seijispieker/FAIRDatabase \
  --base main \
  --title "feat: add user validation" \
  --body "## Summary
- Added email validation
- Updated User model

Closes #42"

# 6. View PR (if created)
gh pr view --web
```

## Common Git Commands

```bash
# View status
git status -sb

# View commit history
git log --oneline -10

# Stage interactively
git add -p

# Amend last commit
git commit --amend

# Stash work temporarily
git stash
git stash pop

# Rebase to clean history (before push)
git rebase -i HEAD~3

# Check what will be pushed
git log origin/main..HEAD
```

## GitHub CLI Quick Reference

```bash
# Authenticate (one time)
gh auth login

# Create PR
gh pr create

# List PRs
gh pr list

# View PR in browser
gh pr view --web

# Check PR status
gh pr status
```

## Tips

1. **Keep commits small** - Easier to review and revert
2. **Write clear messages** - Future you will thank you
3. **Test before commit** - Each commit should work
4. **Never force push to main** - Always use PRs
5. **Group related changes** - Implementation + tests together

---

Remember: The goal is clean, understandable history where each commit is a logical unit of work.