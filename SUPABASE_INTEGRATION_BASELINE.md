# Supabase Integration Baseline - Current State

> 📋 **Companion Document**: See [SUPABASE_INTEGRATION_GUIDE.md](./SUPABASE_INTEGRATION_GUIDE.md) for implementation guide
>
> 🔒 **Status**: FROZEN - This is a Day 0 snapshot, not updated during migration
>
> 🎯 **Purpose**: Historical reference and audit trail for decision-making

**Date**: 2025-10-06
**Status**: Phase 0 Complete
**Confidence Level**: HIGH - All major systems verified

---

## Executive Summary

**Current State**: Supabase is **PARTIALLY INTEGRATED** - Auth is working, but database operations still use raw psycopg2.

**Key Finding**: This is NOT a "migration to Supabase" - it's "completing Supabase integration" that was already started.

**Migration Scope**: Much smaller than original plan assumed. Focus on:
1. Migrating database operations from psycopg2 to Supabase client
2. Optionally migrating file storage to Supabase Storage
3. Auth is already using Supabase (no migration needed)

---

## 1. Supabase Usage

**Current State**: PARTIAL (Auth working, database not using Supabase client)

**Evidence**:
- ✅ Supabase in dependencies: YES (`supabase>=2.15.1` in pyproject.toml)
- ✅ Supabase imports found: 4 files using Supabase (config.py, app.py, auth/form.py, tests/conftest.py)
- ✅ Supabase client initialized: YES (in `config.py` via `Supabase` class)
- ✅ Local Supabase configured: YES (`supabase/` directory exists with config.toml)
- ✅ CLI available: YES (via `npx supabase`)
- ✅ Supabase Auth in use: YES (sign_in_with_password, sign_up)

**What's Working**:
```python
# config.py - Supabase client properly initialized
supabase_extension = Supabase()
# Lazy-loaded client in Flask g context

# auth/form.py - Authentication uses Supabase
supabase_extension.client.auth.sign_in_with_password(...)
supabase_extension.client.auth.sign_up(...)
```

**What's NOT Using Supabase**:
- Database queries (using psycopg2 directly)
- File storage (using local filesystem)

---

## 2. Database Setup

**Database Type**: PostgreSQL v17 (per config.toml)
**Hosted Where**: Local Supabase instance (127.0.0.1:54322)
**Connection Method**: **DUAL SYSTEM** - Both psycopg2 AND Supabase available (but only psycopg2 used for queries)

**Evidence**:
- Connection code: `backend/config.py:202-209` (psycopg2.connect)
- **Total database operations**: **16 execute() calls** (verified via grep)
  - `src/dashboard/helpers.py`: 5 operations (CREATE SCHEMA, CREATE TABLE, INSERT)
  - `src/dashboard/routes.py`: 11 operations (SELECT, UPDATE, information_schema queries)
- **Schema used**: `_realtime` (custom schema, NOT public)
- **Tables pattern**: Dynamic chunked tables for CSV data (e.g., `_realtime.{table_name}`)
- **Special SQL features**: Uses `psycopg2.sql.SQL()` for dynamic table names (3 instances)

**Connection Pattern**:
```python
# Current (psycopg2):
conn = get_db()  # Returns psycopg2 connection
cursor = conn.cursor()
cursor.execute("SELECT ...")
results = cursor.fetchall()

# Supabase client exists but is NOT used for database queries:
supabase_extension.client  # Only used for .auth operations
```

**Database Operations Breakdown**:

**`src/dashboard/helpers.py`** (5 operations):
- Line 27: CREATE SCHEMA `_realtime`
- Line 28-39: CREATE TABLE `_realtime.metadata_tables`
- Line 74-82: CREATE TABLE for chunked data tables
- Line 120-127: INSERT INTO `_realtime.metadata_tables`
- Line 184-190: INSERT INTO chunked data tables

**`src/dashboard/routes.py`** (11 operations):
- Line 175-184: SELECT from information_schema.columns (search by column - display)
- Line 197-206: SELECT column names from information_schema.columns (display)
- Line 209-216: SELECT data from dynamic table (uses sql.SQL - display)
- Line 299-307: SELECT all table names from information_schema.tables (search)
- Line 328-337: SELECT tables matching column search (information_schema - search)
- Line 340-347: SELECT all table names (information_schema - search)
- Line 395-410: SELECT tables by column (information_schema - update)
- Line 418-425: UPDATE dynamic table (uses sql.SQL - update)
- Line 481-491: SELECT to check table existence (information_schema - table_preview)
- Line 508-517: SELECT column information (information_schema - table_preview)
- Line 519-525: SELECT data preview (uses sql.SQL - table_preview)

---

## 3. Authentication System

**Auth Method**: **HYBRID** - Supabase Auth for credentials + Flask Sessions for state
**User Storage**: Supabase Auth (via auth.sign_up)
**Password Hashing**: Supabase (automatic)

**Evidence**:
- Login flow: `backend/src/auth/form.py:53-61` (Supabase sign_in → Flask session)
- Protected routes count: 8 routes using `@login_required()`
- Session management: Flask sessions (NOT JWT-based)
- Decorator: `backend/src/auth/decorators.py:5-21` (checks `session["user"]`)

**Authentication Flow**:
```
1. User submits login → LoginHandler
2. Supabase validates credentials (sign_in_with_password)
3. On success: Store user_id in Flask session
   session["email"] = self.email
   session["user"] = signup_resp.user.id
4. Protected routes check: if "user" not in session → redirect
5. Logout: session.clear()
```

**Key Insight**:
- ✅ Using Supabase for credential validation (good!)
- ❌ NOT using Supabase JWT tokens (using Flask sessions instead)
- ❌ Original plan assumed custom auth → FALSE, already using Supabase Auth!

**Session Usage Locations**:
- Authentication state: `session["user"]`, `session["email"]`
- Application state: `session["uploaded_filepath"]`, `session["quasi_identifiers"]`, etc.
- Extensive session usage for multi-step workflows

---

## 4. File Storage

**Storage Location**: Local filesystem (`UPLOAD_FOLDER`)
**Upload Endpoints**: 2 main endpoints (`/dashboard/upload`, `/data/data_generalization`)
**Download Endpoints**: Via table preview/display (file deleted after processing)

**Evidence**:
- Upload folder: `/workspaces/FAIRDatabase/backend/uploads` (configured in .env)
- File upload code: `backend/src/dashboard/routes.py:90-128`
- File handling: `backend/src/data/form.py:76-108`
- File validation: Extension check only (`.csv`)

**Upload Flow**:
```
1. File uploaded via request.files
2. Saved to UPLOAD_FOLDER with timestamp
3. Processed (parsed, chunked, inserted into DB)
4. File deleted from disk after processing
```

**Validation**:
- Extension check: Only CSV allowed
- File size: MAX_CONTENT_LENGTH = 16MB (160000000 bytes)
- NO content-type validation
- NO virus scanning

---

## 5. Application Structure

**Routes Count**: 16 routes (estimated)
**Protected Routes**: 8 routes with `@login_required()`
**Public Routes**: Login, signup, index, logout

**Blueprints**:
- `main_routes` (/) - Home, index
- `auth_routes` (/auth) - Login, signup, logout
- `dashboard_routes` (/dashboard) - Upload, search, display, update, table_preview
- `data_routes` (/data) - Data generalization workflow
- `privacy_routes` (/privacy) - Privacy processing

**Key Files**:
- `backend/app.py` - Application factory
- `backend/config.py` - Config, Supabase client, DB connection
- `backend/src/auth/` - Auth routes, forms, decorators
- `backend/src/dashboard/` - Main data operations
- `backend/src/data/` - Data generalization workflow
- `backend/src/privacy/` - Privacy enforcement
- `backend/src/anonymization/` - K-anonymity, t-closeness, etc.

**Python Files**: 30 files in `backend/src/`

---

## 6. Testing Status

**Tests Exist**: YES
**Tests Pass**: YES (confirmed by user - "All tests pass")
**Coverage**: Target 45% (pytest.ini_options)

**Evidence**: User confirmed all tests passing
**Test Setup**: Uses pytest with fixtures in `tests/conftest.py`
**Test Environment**: `.env.test` with test database configuration

---

## 7. Supabase Configuration Details

**Local Supabase Setup** (verified):
- **Version**: 2.48.3 (via npx)
- **PostgreSQL**: v17 (major_version in config.toml)
- **API Port**: 54321
- **DB Port**: 54322
- **Studio Port**: 54323
- **Enabled Services**:
  - ✅ API (port 54321)
  - ✅ Auth (JWT expiry: 3600s)
  - ✅ Database (PostgreSQL v17)
  - ✅ Studio (port 54323)
  - ✅ Storage (50MiB file limit)
  - ✅ Realtime (enabled)
  - ✅ Edge Runtime (Deno v2)
- **Not Configured**:
  - ❌ No migrations folder exists
  - ❌ No seed.sql file
  - ❌ Connection pooler disabled
  - ❌ No storage buckets defined
  - ❌ Email confirmations disabled

---

## 8. Gaps and Unknowns

**Answered Questions**:
- ✅ Database query count: **16 operations** (verified)
- ✅ Schema used: `_realtime` (custom, not public)
- ✅ Supabase CLI: Available via npx (v2.48.3)

**Remaining Questions**:
- [ ] How many users exist in Supabase Auth currently?
- [ ] Is there a remote Supabase project, or only local?
- [ ] Any production deployment configuration?

**No Blockers Identified**: System is working, tests pass, clear path forward

---

## 9. Conclusions

**Migration Feasibility**: **HIGH** ✅

**Biggest Challenges**:
1. Migrating **16 psycopg2 queries** to Supabase client (manageable scope)
2. Handling dynamic table names with `sql.SQL()` (3 instances need special attention)
3. Working with custom `_realtime` schema (not standard public schema)
4. Testing information_schema queries (6 instances)

**What Original Plan Got WRONG**:
- ❌ Assumed no Supabase integration → Actually partially integrated
- ❌ Assumed custom auth → Actually using Supabase Auth already
- ❌ Assumed no local Supabase → Actually configured and running
- ❌ Assumed Phase 0-5 needed → Actually only Phase 4 (database) really needed

**What Original Plan Got RIGHT**:
- ✅ Conservative approach is warranted
- ✅ Test continuously
- ✅ Document everything
- ✅ Incremental migration

**Recommended Next Steps**:

> 💡 **See [SUPABASE_INTEGRATION_GUIDE.md](./SUPABASE_INTEGRATION_GUIDE.md) for detailed implementation steps**

**HIGH Priority** (Addresses security issues):
1. **Complete database migration** (Phase 4): Migrate psycopg2 → Supabase ecosystem
   - **Approach**: Mix of migrations + RPC + client (NOT just client - see plan!)
   - Impact: Better connection pooling, prepared for RLS, cleaner code
   - Issues addressed: #10 (Database Connection Management)

**MEDIUM Priority** (Nice to have):
2. **File storage migration** (Phase 3): Local FS → Supabase Storage
   - Impact: Better access control, signed URLs, scalability
   - Issues addressed: #6 (Unrestricted File Upload - partial)

**LOW Priority** (Optional):
3. **Auth enhancement** (Phase 5 - MODIFIED): Consider JWT tokens instead of sessions
   - Impact: Stateless auth, better for scaling
   - Issues addressed: #1, #2, #3, #5 (Auth/session issues)
   - **NOTE**: This is OPTIONAL - current Supabase Auth + sessions works fine!

**Decision**: Proceed with **simplified migration plan** focusing on database layer (see PLAN.md for timeline estimates)
