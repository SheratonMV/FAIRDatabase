# CLAUDE.md - FAIRDatabase Project Guide

## 📋 Project Overview

FAIRDatabase implements FAIR data principles (Findable, Accessible, Interoperable, Reusable) for research data management using Flask backend and web frontend.

## 🎯 Core Development Philosophy

**Start simple. Add complexity only when proven necessary.**

### Primary Principles (Always Apply)

#### KISS - Keep It Simple, Stupid
The simplest working solution is usually the best. Complexity must be justified by actual need, not anticipated futures.

#### YAGNI - You Aren't Gonna Need It
Build only what's required now. Future-proofing without clear requirements creates unnecessary complexity.

#### DRY - Don't Repeat Yourself
Knowledge should have a single, authoritative representation. But remember: duplication is better than the wrong abstraction.

#### Single Responsibility
Each component does one thing well. If you need "and" to describe it, split it.

#### Fail Fast
Detect and report errors immediately with clear messages. Don't let problems propagate silently.

#### Explicit Over Implicit
Code should clearly express intent. No magic, no surprises. Reading code should reveal its purpose.

### Design Principles (Apply with Context)

#### Rule of Three
1. First instance: write inline
2. Second instance: duplicate it
3. Third instance: consider abstracting

#### Least Astonishment
Code should behave as developers expect. Follow conventions. Avoid clever tricks.

#### Separation of Concerns
Different aspects (data, logic, presentation) in different places. Mix responsibilities only when simplicity demands it.

#### Convention Over Configuration
Use sensible defaults. Configure only what differs from the norm.

### FAIR Data Principles (When Handling Research Data)

- **Findable**: Persistent identifiers and metadata
- **Accessible**: Clear retrieval protocols
- **Interoperable**: Standard formats and vocabularies
- **Reusable**: Licenses and provenance

### 🚫 Anti-Patterns

Avoid these signs of overengineering:
- Abstractions with single implementations
- Indirection without purpose
- Premature optimization without measurements
- Features beyond requirements
- Frameworks when standard library suffices

### ✅ Progressive Complexity

Start left, move right only when needed:
```
Function → Class → Module → Package
Dictionary → DataClass → Domain Model
Direct Call → Callback → Event System
Hardcoded → Config → Environment Variable
```

### Decision Framework

Ask in order:
1. Can it be simpler?
2. Is complexity warranted? (Document why)
3. Can this decision be deferred?

When principles conflict: **Correct > Simple > Clean > Flexible**

Remember: The best code is code that doesn't exist. The second best is simple code that works.

## 🔧 Technology Stack

- **Backend**: Python/Flask (may migrate to FastAPI)
- **Database**: Supabase (PostgreSQL)
- **Frontend**: HTML templates with static assets
- **Testing**: pytest
- **Package Management**: uv with pyproject.toml

**Note**: Existing code may not follow these standards. Prioritize principles over existing patterns.

## 📝 Git Workflow

**Fork Information**:
- Original: `https://github.com/SheratonMV/FAIRDatabase`
- Working Fork: `https://github.com/seijispieker/FAIRDatabase` (current)

**Rules**:
- Never push to original repository
- Never create PRs to original without explicit instruction
- Always work in fork

## 📁 Project Structure

```
FAIRDatabase/
├── backend/           # Flask app + CLAUDE.md
│   ├── src/          # Application modules
│   │   ├── auth/            # Authentication
│   │   ├── dashboard/       # Dashboard
│   │   ├── data/            # Data management
│   │   ├── privacy/         # Privacy features
│   │   ├── main/            # Main/home routes
│   │   └── anonymization/   # Privacy & anonymization
│   ├── tests/        # Test suite
│   ├── app.py        # Application entry point
│   ├── config.py     # Configuration
│   └── pyproject.toml # Dependencies
├── frontend/          # Templates + CLAUDE.md
│   ├── templates/    # Jinja2 templates
│   └── public/       # Logo images
├── static/            # Static assets (CSS, JS)
├── supabase/          # Database config
└── .devcontainer/     # Dev container + CLAUDE.md
```

---

**Living Document**: Update as needed while maintaining core principles.