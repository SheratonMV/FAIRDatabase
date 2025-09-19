# CLAUDE.md - FAIRDatabase Project Guide

This file provides comprehensive guidance to Claude Code when working with the FAIRDatabase repository.

## 📋 Project Overview

**Current Date**: September 2025

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

## ⚠️ Current Codebase Notes

The existing FAIRDatabase implementation:
- Uses Flask (may migrate to FastAPI in future)
- Has inconsistent patterns that need refactoring
- May not follow all conventions defined here
- Should be gradually improved, not rewritten at once

---

**Remember**: This is a living document. Update it as the project evolves, but maintain consistency with core principles.