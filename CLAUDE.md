# CLAUDE.md - FAIRDatabase Project Guide

This file provides comprehensive guidance to Claude Code when working with the FAIRDatabase repository.

## 📋 Project Overview

FAIRDatabase is a system designed to implement FAIR data principles (Findable, Accessible, Interoperable, and Reusable) for managing research data. The project consists of a Flask backend and a web-based frontend.

### Hierarchical Documentation Structure

- **Root CLAUDE.md (this file)**: Contains general project-wide conventions, principles, and workflows
- **Subdirectory CLAUDE.md files**: Contain context-specific guidance (e.g., `backend/CLAUDE.md` for Python-specific conventions)
- Always check for local CLAUDE.md files when working in subdirectories

## 🎯 Core Development Philosophy

### Primary Principles (from PRINCIPLES.md)

#### 1. Single Responsibility Principle (SRP)
Every module, class, or function should do ONE thing well. When describing what it does, you should be able to do so without using "and" or "or".

#### 2. DRY (Don't Repeat Yourself)
Every piece of knowledge must have a single, unambiguous, authoritative representation within a system. Duplication is acceptable only when the duplicated code might change independently.

#### 3. Clean Code Readability
Code should clearly express intent. Another developer should understand what it does, why it exists, and how to modify it without extensive documentation.

#### 4. Dependency Inversion Principle
High-level modules should not depend on low-level modules. Both should depend on abstractions. This enables testing, flexibility, and maintainability.

#### 5. Open/Closed Principle
Software entities should be open for extension but closed for modification. Add new functionality by adding new code, not by changing existing code that works.

#### 6. Fail Fast and Explicitly
Detect and report errors as early as possible. Fail with clear, actionable error messages at the point of failure, not later when debugging becomes difficult.

### Priority Order for Conflicting Principles

When principles conflict, apply this precedence:
1. **Security** - Never compromise on security
2. **Correctness** - Working code over elegant code
3. **Maintainability** - Future developers over current convenience
4. **Performance** - Optimize only after measuring
5. **Features** - Core functionality before nice-to-haves

## 🔧 Technology Stack

### Current Stack (Subject to Overhaul)
- **Backend**: Python with Flask framework
- **Database**: TBD (review existing docker-compose.yml)
- **Frontend**: HTML templates with static assets
- **Testing**: pytest framework

### Important Notes
- The current codebase is NOT compliant with all standards defined in this document
- Major refactoring is expected; prioritize new code quality over matching existing patterns
- When in doubt, follow the principles in this document rather than existing code patterns

## 🛠️ MCP Tools Usage

### Archon MCP
**Primary Use**: Knowledge base for documentation and best practices

- **Always search Archon first** for:
  - Development best practices
  - Framework documentation
  - Design patterns
  - Security guidelines
- If documentation is missing, **notify the user** that it should be added to the knowledge base
- Use commands like:
  - `mcp__archon__rag_search_knowledge_base` for general searches
  - `mcp__archon__rag_search_code_examples` for implementation examples

### Serena MCP
**Primary Use**: Code analysis and intelligent editing

- Use for semantic code operations
- Prioritize symbolic tools over reading entire files
- Follow the pattern: Overview → Targeted Analysis → Precise Edits

## 📝 Git Workflow & Repository Management

### Critical Fork Information
```
Original Repository: https://github.com/SheratonMV/FAIRDatabase
Forked Repository:   https://github.com/seijispieker/FAIRDatabase (current)
```

### IMPORTANT Git Rules
- **NEVER** push directly to `SheratonMV/FAIRDatabase`
- **NEVER** create pull requests to the original repository without explicit user instruction
- **ALWAYS** work within the fork (`seijispieker/FAIRDatabase`)
- Default remote should be set to the fork, not the original

### Branch Strategy
- `main` - Production-ready code (protected)
- `develop` - Integration branch for features
- `feature/*` - New features
- `fix/*` - Bug fixes
- `refactor/*` - Code refactoring
- `test/*` - Test additions or improvements

### Commit Message Format
```
<type>(<scope>): <subject>

<body>

<footer>
```

Types: feat, fix, docs, style, refactor, test, chore

**IMPORTANT**: Never include "Claude Code", "generated with Claude", or similar attributions in commit messages

### Pull Request Workflow
1. Create feature branch from `develop`
2. Make changes following all principles
3. Run tests and linters
4. Push to fork (`seijispieker/FAIRDatabase`)
5. Create PR within the fork (feature → develop)
6. Only merge to original repository when explicitly instructed

## 🧪 Testing & Quality Assurance

### Test-Driven Development Mindset
Even when not strictly following TDD, think about testability. Code that's hard to test is often poorly designed.

### Testing Requirements
- Write tests for all new functionality
- Maintain or improve existing test coverage
- Run tests before committing: `pytest`
- Check for existing test patterns in `backend/tests/`

### Code Quality Checks
Before any commit:
```bash
# Run tests
pytest

# Run linter (if configured)
ruff check .

# Format code (if configured)
ruff format .
```

## 🔒 Security Requirements

### Core Security Principles
1. **Never trust user input** - Validate and sanitize everything
2. **Never commit secrets** - Use environment variables
3. **Use parameterized queries** - Prevent SQL injection
4. **Implement proper authentication** - Before authorization
5. **Keep dependencies updated** - Regular security updates

### Security Checklist
- [ ] All inputs validated with appropriate libraries
- [ ] No hardcoded credentials or API keys
- [ ] SQL queries use parameterized statements
- [ ] Authentication checks on all protected routes
- [ ] Error messages don't leak sensitive information

## 📁 Project Structure Guidelines

### File Organization
```
FAIRDatabase/
├── backend/
│   ├── CLAUDE.md          # Python-specific conventions
│   ├── src/               # Application source code
│   ├── tests/             # Test files next to code
│   └── requirements.txt   # Python dependencies
├── frontend/
│   ├── CLAUDE.md          # Frontend-specific conventions
│   ├── templates/         # HTML templates
│   └── public/            # Static assets
├── docs/                  # Documentation
├── .github/               # GitHub workflows
└── CLAUDE.md             # This file
```

### Module Size Limits
- **Files**: Maximum 500 lines
- **Functions**: Maximum 50 lines
- **Classes**: Maximum 100 lines
- If approaching limits, refactor into smaller modules

## 🚨 Error Handling

### Exception Best Practices
```python
# Create domain-specific exceptions
class FAIRDatabaseError(Exception):
    """Base exception for FAIRDatabase"""
    pass

class ValidationError(FAIRDatabaseError):
    """Raised when validation fails"""
    pass

# Use specific exception handling
try:
    process_data(input_data)
except ValidationError as e:
    logger.warning(f"Validation failed: {e}")
    return error_response(400, str(e))
except FAIRDatabaseError as e:
    logger.error(f"Application error: {e}")
    return error_response(500, "Internal error")
```

### Logging Strategy
- Use structured logging
- Log at appropriate levels (DEBUG, INFO, WARNING, ERROR)
- Include context in log messages
- Never log sensitive data (passwords, tokens, PII)

## 🔍 Search & Analysis Guidelines

### CRITICAL: Use Appropriate Tools
```bash
# ❌ NEVER use these:
grep -r "pattern" .
find . -name "*.py"

# ✅ ALWAYS use these instead:
rg "pattern"              # Use ripgrep
rg --files -g "*.py"     # Find files with ripgrep
```

### Code Discovery Pattern
1. Use Serena MCP for semantic analysis
2. Use ripgrep (`rg`) for text searches
3. Use Archon for documentation searches
4. Only read entire files as last resort

## 📋 Development Checklist

Before starting any task:
- [ ] Check for local CLAUDE.md in working directory
- [ ] Search Archon knowledge base for relevant patterns
- [ ] Review existing code structure with Serena MCP
- [ ] Create clear task breakdown

Before committing:
- [ ] Code follows all principles in this document
- [ ] Tests written and passing
- [ ] No security vulnerabilities introduced
- [ ] Documentation updated if needed
- [ ] Commit message follows format

## ⚠️ Current Codebase Notes

The existing FAIRDatabase implementation:
- Uses Flask (may migrate to FastAPI in future)
- Has inconsistent patterns that need refactoring
- May not follow all conventions defined here
- Should be gradually improved, not rewritten at once

When working with existing code:
1. Understand the current implementation
2. Identify violations of principles
3. Refactor incrementally when touching code
4. Prioritize critical fixes over style improvements

## 🆘 When to Ask for Help

Always inform the user when:
- Documentation is missing from Archon knowledge base
- Security concerns are identified
- Major architectural decisions are needed
- External dependencies need to be added
- Push/PR to original repository is considered

## 📚 Additional Resources

- Check Archon knowledge base for:
  - Flask documentation and patterns
  - Python best practices
  - FAIR data principles
  - Database design patterns
- Review subdirectory CLAUDE.md files for context-specific guidance
- Consult PRINCIPLES.md for detailed development philosophy

---

**Remember**: This is a living document. Update it as the project evolves, but maintain consistency with core principles.