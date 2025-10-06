# Supabase Integration Guide - Implementation Reference

**Status**: 🔵 Ready to implement
**Focus**: Phase 4 - Database Migration (psycopg2 → Supabase ecosystem)
**Timeline**: 2-3 weeks (13 days)

---

## Quick Links

- **Baseline Data**: [SUPABASE_INTEGRATION_BASELINE.md](./SUPABASE_INTEGRATION_BASELINE.md) (historical reference)
- **Supabase Docs**: https://supabase.com/docs/reference/python

---

## 🎯 Mission

**Replace 16 psycopg2 database operations** using:
- **3 operations** → Supabase migrations (DDL)
- **11 operations** → PostgreSQL RPC functions (metadata + dynamic queries)
- **2 operations** → Supabase Python client (simple CRUD)

**NOT** migrating everything to Python client - using proper **Supabase ecosystem** (migrations + RPC + client).

---

## ⚠️ Critical Constraints

1. **Custom Schema**: App uses `_realtime` schema (not `public`)
2. **Dynamic Tables**: 3 queries use `sql.SQL()` for table names
3. **Information Schema**: 8 queries access `information_schema` directly
4. **Tests Must Pass**: All existing tests provide safety net

**Solution**: RPC functions in `public` schema with `SECURITY DEFINER` to access `_realtime` schema.

---

## 📦 16 Operations Inventory

> Source: [BASELINE.md § 2](./SUPABASE_INTEGRATION_BASELINE.md#2-database-setup)

### Type 1: DDL → Migrations (3 ops)
- `helpers.py:27` - CREATE SCHEMA `_realtime`
- `helpers.py:28-39` - CREATE TABLE `_realtime.metadata_tables`
- `helpers.py:74-82` - CREATE TABLE (chunked data)

### Type 2: Metadata → RPC (8 ops)
- `routes.py:175-184` - SELECT columns (display)
- `routes.py:197-206` - SELECT columns (display)
- `routes.py:299-307` - SELECT tables (search)
- `routes.py:328-337` - SELECT by column (search)
- `routes.py:340-347` - SELECT tables (search)
- `routes.py:395-410` - SELECT by column (update)
- `routes.py:481-491` - CHECK table exists (preview)
- `routes.py:508-517` - SELECT columns (preview)

### Type 3: Dynamic → RPC (3 ops)
- `routes.py:209-216` - SELECT with dynamic table
- `routes.py:418-425` - UPDATE with dynamic table
- `routes.py:519-525` - SELECT preview with dynamic table

### Type 4: Simple CRUD → Client or RPC (2 ops)
- `helpers.py:120-127` - INSERT INTO metadata_tables
- `helpers.py:184-190` - INSERT INTO data tables

---

## 🛠️ Implementation Steps

### Step 1: DDL to Migrations (Days 1-2)

**Goal**: Move CREATE SCHEMA/TABLE from Python to SQL migrations

#### 1.1 Create Migration Files

```bash
# Ensure directory exists
mkdir -p supabase/migrations
```

**File**: `supabase/migrations/20250106000000_create_realtime_schema.sql`
```sql
-- Create custom schema
CREATE SCHEMA IF NOT EXISTS _realtime;

-- Set search path to include _realtime
ALTER DATABASE postgres SET search_path TO public, _realtime;
```

**File**: `supabase/migrations/20250106000001_create_metadata_tables.sql`
```sql
-- Metadata tracking table
CREATE TABLE IF NOT EXISTS _realtime.metadata_tables (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  table_name TEXT NOT NULL UNIQUE,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_metadata_table_name ON _realtime.metadata_tables(table_name);
```

**File**: `supabase/migrations/20250106000002_create_data_table_template.sql`
```sql
-- Template for chunked data tables (actual creation may need to be dynamic)
-- This migration documents the expected schema
-- Note: Dynamic table creation may still happen in app or via RPC
```

#### 1.2 Apply Migrations

```bash
# Apply all pending migrations
npx supabase db reset
# OR incremental
npx supabase migration up
```

#### 1.3 Verify

```bash
# Check schema exists
psql -h 127.0.0.1 -p 54322 -U postgres -d postgres \
  -c "\dn _realtime"

# Check table exists
psql -h 127.0.0.1 -p 54322 -U postgres -d postgres \
  -c "\dt _realtime.metadata_tables"
```

#### 1.4 Update Python Code

**Remove from `backend/src/dashboard/helpers.py`**:
- Line 27: `CREATE SCHEMA` statement
- Lines 28-39: `CREATE TABLE metadata_tables` statement
- Lines 74-82: `CREATE TABLE` for data (or move to RPC if dynamic)

---

### Step 2: Create RPC Functions (Days 3-5)

**Goal**: Wrap complex queries in PostgreSQL functions

#### 2.1 Information Schema Functions

**File**: `supabase/migrations/20250107000000_create_rpc_functions.sql`

```sql
-- Get tables containing specific column
CREATE OR REPLACE FUNCTION public.search_tables_by_column(
  search_column TEXT,
  schema_name TEXT DEFAULT '_realtime'
)
RETURNS TABLE(table_name TEXT) AS $$
  SELECT t.table_name::TEXT
  FROM information_schema.tables t
  JOIN information_schema.columns c ON t.table_name = c.table_name
  WHERE c.column_name = search_column
    AND t.table_schema = schema_name
    AND t.table_type = 'BASE TABLE';
$$ LANGUAGE sql SECURITY DEFINER;

-- Get column information for a table
CREATE OR REPLACE FUNCTION public.get_table_columns(
  p_table_name TEXT,
  schema_name TEXT DEFAULT '_realtime'
)
RETURNS TABLE(
  column_name TEXT,
  data_type TEXT,
  is_nullable TEXT
) AS $$
  SELECT
    column_name::TEXT,
    data_type::TEXT,
    is_nullable::TEXT
  FROM information_schema.columns
  WHERE table_name = p_table_name
    AND table_schema = schema_name
  ORDER BY ordinal_position;
$$ LANGUAGE sql SECURITY DEFINER;

-- Check if table exists
CREATE OR REPLACE FUNCTION public.table_exists(
  p_table_name TEXT,
  schema_name TEXT DEFAULT '_realtime'
)
RETURNS BOOLEAN AS $$
  SELECT EXISTS (
    SELECT 1
    FROM information_schema.tables
    WHERE table_name = p_table_name
      AND table_schema = schema_name
  );
$$ LANGUAGE sql SECURITY DEFINER;

-- Get all tables in schema
CREATE OR REPLACE FUNCTION public.get_all_tables(
  schema_name TEXT DEFAULT '_realtime'
)
RETURNS TABLE(table_name TEXT) AS $$
  SELECT table_name::TEXT
  FROM information_schema.tables
  WHERE table_schema = schema_name
    AND table_type = 'BASE TABLE'
  ORDER BY table_name;
$$ LANGUAGE sql SECURITY DEFINER;
```

#### 2.2 Dynamic Table Functions

**Add to same migration file**:

```sql
-- Select from dynamic table (safe)
CREATE OR REPLACE FUNCTION public.select_from_table(
  p_table_name TEXT,
  p_limit INT DEFAULT 100
)
RETURNS TABLE(data JSONB) AS $$
BEGIN
  -- Validate table exists (prevent injection)
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.tables
    WHERE table_schema = '_realtime' AND table_name = p_table_name
  ) THEN
    RAISE EXCEPTION 'Table % does not exist', p_table_name;
  END IF;

  -- Safe dynamic SQL
  RETURN QUERY EXECUTE format(
    'SELECT row_to_json(t)::JSONB FROM _realtime.%I t LIMIT %s',
    p_table_name, p_limit
  );
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Update dynamic table row
CREATE OR REPLACE FUNCTION public.update_table_row(
  p_table_name TEXT,
  p_row_id UUID,
  p_updates JSONB
)
RETURNS BOOLEAN AS $$
DECLARE
  v_sql TEXT;
  v_set_clause TEXT;
  v_key TEXT;
  v_value TEXT;
BEGIN
  -- Validate table exists
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.tables
    WHERE table_schema = '_realtime' AND table_name = p_table_name
  ) THEN
    RAISE EXCEPTION 'Table % does not exist', p_table_name;
  END IF;

  -- Build SET clause from JSONB
  v_set_clause := '';
  FOR v_key, v_value IN SELECT * FROM jsonb_each_text(p_updates)
  LOOP
    IF v_set_clause != '' THEN
      v_set_clause := v_set_clause || ', ';
    END IF;
    v_set_clause := v_set_clause || format('%I = %L', v_key, v_value);
  END LOOP;

  -- Execute update
  v_sql := format(
    'UPDATE _realtime.%I SET %s WHERE id = %L',
    p_table_name, v_set_clause, p_row_id
  );

  EXECUTE v_sql;
  RETURN TRUE;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Insert into metadata (if needed as RPC fallback)
CREATE OR REPLACE FUNCTION public.insert_metadata(
  p_table_name TEXT
)
RETURNS UUID AS $$
DECLARE
  v_id UUID;
BEGIN
  INSERT INTO _realtime.metadata_tables (table_name)
  VALUES (p_table_name)
  RETURNING id INTO v_id;

  RETURN v_id;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;
```

#### 2.3 Apply & Test Functions

```bash
# Apply migration
npx supabase migration up

# Test RPC function via psql
psql -h 127.0.0.1 -p 54322 -U postgres -d postgres \
  -c "SELECT * FROM public.get_all_tables()"

# Test from Python
python3 -c "
from config import supabase_extension
supabase = supabase_extension.client
result = supabase.rpc('get_all_tables').execute()
print(result.data)
"
```

---

### Step 3: Migrate Simple CRUD (Days 6-7)

**Goal**: Replace 2 INSERT operations

#### 3.1 Test Schema Prefix Approach

```python
# In helpers.py:120-127 replacement
# TRY THIS FIRST:
from config import supabase_extension
supabase = supabase_extension.client

try:
    # Option A: Schema prefix (test if this works)
    response = supabase.table("_realtime.metadata_tables").insert({
        "table_name": table_name
    }).execute()

    print(f"✅ Schema prefix works! ID: {response.data[0]['id']}")

except Exception as e:
    print(f"❌ Schema prefix failed: {e}")

    # Option B: Fallback to RPC
    response = supabase.rpc("insert_metadata", {
        "p_table_name": table_name
    }).execute()

    print(f"✅ RPC fallback works! ID: {response.data}")
```

#### 3.2 Update Code Based on Test Results

**If schema prefix works** (unlikely but possible):
```python
# helpers.py:120-127
response = supabase.table("_realtime.metadata_tables").insert({
    "table_name": table_name
}).execute()
metadata_id = response.data[0]['id']
```

**If RPC needed** (more likely):
```python
# helpers.py:120-127
response = supabase.rpc("insert_metadata", {
    "p_table_name": table_name
}).execute()
metadata_id = response.data
```

#### 3.3 Test INSERT Operations

```bash
# Run relevant tests
cd backend
uv run pytest tests/dashboard/test_helpers.py -v -k insert
```

---

### Step 4: Update Routes to Use RPC (Days 8-9)

**Goal**: Replace 11 psycopg2 queries with RPC calls

#### 4.1 Replace Pattern

**Before** (routes.py:175-184):
```python
cursor.execute("""
    SELECT t.table_name
    FROM information_schema.tables t
    JOIN information_schema.columns c ON t.table_name = c.table_name
    WHERE c.column_name = %s
""", (column_name,))
results = cursor.fetchall()
```

**After**:
```python
from config import supabase_extension
supabase = supabase_extension.client

response = supabase.rpc("search_tables_by_column", {
    "search_column": column_name
}).execute()
results = response.data  # List of dicts with 'table_name' key
```

#### 4.2 Conversion Table

| Current Location | RPC Function | Python Call |
|------------------|--------------|-------------|
| routes.py:175-184 | `search_tables_by_column` | `supabase.rpc('search_tables_by_column', {'search_column': col})` |
| routes.py:197-206 | `get_table_columns` | `supabase.rpc('get_table_columns', {'p_table_name': table})` |
| routes.py:209-216 | `select_from_table` | `supabase.rpc('select_from_table', {'p_table_name': table})` |
| routes.py:299-307 | `get_all_tables` | `supabase.rpc('get_all_tables')` |
| routes.py:328-337 | `search_tables_by_column` | `supabase.rpc('search_tables_by_column', {'search_column': col})` |
| routes.py:340-347 | `get_all_tables` | `supabase.rpc('get_all_tables')` |
| routes.py:395-410 | `search_tables_by_column` | `supabase.rpc('search_tables_by_column', {'search_column': col})` |
| routes.py:418-425 | `update_table_row` | `supabase.rpc('update_table_row', {'p_table_name': t, 'p_row_id': id, 'p_updates': data})` |
| routes.py:481-491 | `table_exists` | `supabase.rpc('table_exists', {'p_table_name': table})` |
| routes.py:508-517 | `get_table_columns` | `supabase.rpc('get_table_columns', {'p_table_name': table})` |
| routes.py:519-525 | `select_from_table` | `supabase.rpc('select_from_table', {'p_table_name': table})` |

#### 4.3 Error Handling Pattern

```python
try:
    response = supabase.rpc('function_name', params).execute()
    results = response.data
except Exception as e:
    current_app.logger.error(f"RPC call failed: {e}")
    flash("Database operation failed", "danger")
    return []
```

---

## 🧪 Testing Strategy

### Per-Operation Testing

After each migration:
```bash
# Run specific test
cd backend
uv run pytest tests/dashboard/test_routes.py::test_specific_route -v

# Run all dashboard tests
uv run pytest tests/dashboard/ -v
```

### Integration Testing (Days 10-11)

```bash
# Full test suite
uv run pytest

# With coverage
uv run pytest --cov=src --cov-report=term-missing

# Coverage threshold: 45% (per pytest.ini)
```

### Manual Test Checklist

- [ ] Login works
- [ ] File upload works
- [ ] Dashboard displays data
- [ ] Search by column works
- [ ] Update record works
- [ ] Table preview works
- [ ] No console errors

---

## 🧹 Cleanup (Days 12-13)

### Remove psycopg2

**1. Remove from config.py:**
```python
# DELETE these functions:
def init_db()
def get_db()
def teardown_db(exception)
```

**2. Remove from app.py:**
```python
# DELETE:
app.teardown_appcontext(teardown_db)

@app.before_request
def before_request():
    g.db = get_db()
```

**3. Remove dependency:**
```bash
cd backend
uv remove psycopg2-binary
```

**4. Verify no imports remain:**
```bash
grep -r "psycopg2" backend/src/
# Should return nothing
```

---

## 📊 Progress Tracker

**Track as you go** - update this section:

### DDL Migrations (0/3)
- [ ] `helpers.py:27` - CREATE SCHEMA
- [ ] `helpers.py:28-39` - CREATE TABLE metadata
- [ ] `helpers.py:74-82` - CREATE TABLE data

### RPC Functions Created (7/7 unique)
- [x] `search_tables_by_column()`
- [x] `get_table_columns()`
- [x] `table_exists()`
- [x] `get_all_tables()`
- [x] `select_from_table()`
- [x] `update_table_row()`
- [x] `insert_metadata()`

### Routes Migrated (0/11)
- [ ] routes.py:175-184
- [ ] routes.py:197-206
- [ ] routes.py:209-216
- [ ] routes.py:299-307
- [ ] routes.py:328-337
- [ ] routes.py:340-347
- [ ] routes.py:395-410
- [ ] routes.py:418-425
- [ ] routes.py:481-491
- [ ] routes.py:508-517
- [ ] routes.py:519-525

### Simple CRUD Migrated (0/2)
- [ ] helpers.py:120-127 - INSERT metadata
- [ ] helpers.py:184-190 - INSERT data

### Cleanup (0/4)
- [ ] psycopg2 dependency removed
- [ ] get_db() removed
- [ ] DDL code removed from helpers.py
- [ ] All tests passing

**Total Progress**: 7/27 tasks (Step 2 Complete ✅)

---

## 🚀 Getting Started

### Prerequisites Check

```bash
# 1. Create branch
git checkout -b feature/supabase-integration

# 2. Verify Supabase CLI
npx supabase --version

# 3. Start local Supabase
npx supabase start

# 4. Check DB connection
psql -h 127.0.0.1 -p 54322 -U postgres -d postgres -c "SELECT version()"

# 5. Run tests (should pass)
cd backend && uv run pytest
```

### First Actions (Right Now)

1. **Read DDL code** from helpers.py:
   ```bash
   # Lines 27, 28-39, 74-82
   ```

2. **Create first migration**:
   ```bash
   touch supabase/migrations/20250106000000_create_realtime_schema.sql
   ```

3. **Start implementing Step 1** (DDL to migrations)

---

## 📝 Git Strategy

```bash
# Commit after each step
git add .
git commit -m "feat: migrate CREATE SCHEMA to Supabase migration"
git commit -m "feat: create RPC functions for metadata queries"
git commit -m "feat: replace routes.py:175-184 with RPC call"

# Push regularly
git push origin feature/supabase-integration
```

---

## 🆘 Quick Reference

### Current Pattern (psycopg2)
```python
conn = get_db()
cursor = conn.cursor()
cursor.execute("SELECT ...", params)
results = cursor.fetchall()
```

### New Pattern (Supabase RPC)
```python
from config import supabase_extension
supabase = supabase_extension.client
response = supabase.rpc('function_name', params).execute()
results = response.data
```

### Test RPC via psql
```bash
psql -h 127.0.0.1 -p 54322 -U postgres -d postgres \
  -c "SELECT * FROM public.function_name('param')"
```

### Apply Migrations
```bash
npx supabase db reset      # Full reset
npx supabase migration up  # Incremental
```

---

**Ready to start? Begin with Step 1 (DDL to Migrations).**

Good luck! 🎯
