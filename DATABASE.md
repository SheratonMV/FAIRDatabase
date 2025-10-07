# Database Architecture

## Overview

FAIRDatabase uses **PostgreSQL via Supabase** with a pragmatic hybrid approach:
- **Supabase** for migrations, RPC functions, and static table operations
- **psycopg2** for dynamic table creation (due to PostgREST limitations)

## Database Stack

- **Provider**: Supabase (PostgreSQL 17)
- **Local Development**: Docker via `npx supabase start`
- **Connection Details**:
  - Database: `postgres://postgres:postgres@127.0.0.1:54322/postgres`
  - Studio: `http://127.0.0.1:54323`
  - API: `http://127.0.0.1:54321`

## Schema Structure

### Custom Schema: `_realtime`

All application data lives in the `_realtime` schema (not `public`):
- Isolates app data from Supabase system tables
- Enabled in `supabase/config.toml` via `schemas = ["public", "graphql_public", "_realtime"]`

**Core Tables:**
- `_realtime.metadata_tables` - Tracks uploaded CSV files and their metadata
- `_realtime.<dataset>_p1`, `_realtime.<dataset>_p2`, etc. - Dynamic data tables (chunked by 1200 columns)

## Hybrid Architecture Rationale

### Why Not 100% Supabase?

**PostgREST Schema Cache Limitation:**
Supabase's REST API layer (PostgREST) caches database schema for performance. Dynamically created tables aren't immediately visible to the API, even with `NOTIFY pgrst, 'reload schema'` commands.

**Impact:**
You cannot use Supabase client to insert into a table immediately after creating it via RPC or migration.

**Solution:**
Use direct psycopg2 connections for the dynamic table workflow (create + insert), then use Supabase RPC for all subsequent queries.

### What Uses What

| Operation | Tool | Location | Reason |
|-----------|------|----------|--------|
| Schema setup | Supabase migrations | `supabase/migrations/` | Version controlled DDL |
| Static table inserts | Supabase client | `helpers.py:pg_insert_metadata()` | Clean API, type-safe |
| Metadata queries | Supabase RPC | `routes.py` (11 operations) | Security, encapsulation |
| Dynamic table creation | psycopg2 | `helpers.py:pg_create_data_table()` | Immediate DDL execution |
| Dynamic table inserts | psycopg2 | `helpers.py:pg_insert_data_rows()` | No cache issues |

## Supabase RPC Functions

All functions use `SECURITY DEFINER` to access `_realtime` schema from `public` schema.

### Metadata Functions

```sql
-- Get all tables in schema
SELECT * FROM public.get_all_tables('_realtime');

-- Get columns for a table
SELECT * FROM public.get_table_columns('my_table', '_realtime');

-- Check if table exists
SELECT public.table_exists('my_table', '_realtime');

-- Find tables containing a specific column
SELECT * FROM public.search_tables_by_column('patient_id', '_realtime');
```

### Data Access Functions

```sql
-- Select from dynamic table (returns JSONB)
SELECT * FROM public.select_from_table('my_table_p1', 100, '_realtime');

-- Update a row (by rowid, not id)
SELECT public.update_table_row(
  'my_table_p1',
  42,  -- rowid
  '{"column_name": "new_value"}'::jsonb,
  '_realtime'
);
```

### Helper Functions

```sql
-- Insert metadata record
SELECT public.insert_metadata(
  'my_table',
  'main_table_name',
  'Description text',
  'Origin text'
);

-- Create data table (exists but not used - psycopg2 handles this)
SELECT public.create_data_table(
  '_realtime',
  'new_table',
  ARRAY['col1', 'col2'],
  'patient_id'
);
```

## Python Usage Patterns

### Supabase Client

```python
from config import supabase_extension

# Query via RPC
response = supabase_extension.client.rpc('get_all_tables', {
    'schema_name': '_realtime'
}).execute()
tables = response.data

# Insert into static table
response = (
    supabase_extension.client
    .schema('_realtime')
    .table('metadata_tables')
    .insert({'table_name': 'my_table', ...})
    .execute()
)
```

### Query Execution Convention

**IMPORTANT**: Always call `.execute()` explicitly on Supabase queries for clarity and consistency.

#### When `.execute()` is Required

```python
# ✅ RPC calls - ALWAYS use .execute()
response = supabase_extension.client.rpc('function_name', params).execute()

# ✅ Table queries - ALWAYS use .execute()
response = (
    supabase_extension.client
    .schema('_realtime')
    .table('metadata_tables')
    .select('*')
    .execute()
)

# ✅ Insert/Update/Delete - ALWAYS use .execute()
response = (
    supabase_extension.client
    .table('my_table')
    .insert({'key': 'value'})
    .execute()
)
```

#### When `.execute()` is NOT Required

```python
# ✅ Auth operations return results directly
user = supabase_extension.client.auth.sign_in_with_password(email, password)
session = supabase_extension.client.auth.refresh_session(token)
users = supabase_extension.client.auth.admin.list_users()
```

#### Recommended Helper: `safe_rpc_call()`

For RPC operations, use the `safe_rpc_call()` helper which provides consistent error handling:

```python
from config import supabase_extension

# Replaces: supabase_extension.client.rpc('function', params).execute()
data = supabase_extension.safe_rpc_call('function_name', {'param': 'value'})

# Automatically handles:
# - .execute() chaining
# - Exception catching and logging
# - Consistent error responses
```

**Chaining Format**: Use parentheses for multi-line queries to improve readability:

```python
# Good - clear chaining
response = (
    supabase_extension.client
    .rpc('get_all_tables')
    .execute()
)

# Also acceptable - single line for simple queries
response = supabase_extension.client.rpc('get_all_tables').execute()
```

### psycopg2 (Dynamic Tables Only)

```python
from flask import g
from config import get_db

conn = g.db  # Get connection from Flask context
with conn.cursor() as cur:
    # Create table
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS _realtime.my_table (
            rowid SERIAL PRIMARY KEY,
            patient_id TEXT NOT NULL,
            ...
        );
    """)

    # Grant permissions for Supabase
    cur.execute(f"""
        GRANT ALL ON TABLE _realtime.my_table
        TO anon, authenticated, service_role;
    """)

    # Insert data
    cur.execute(f"""
        INSERT INTO _realtime.my_table (patient_id, ...)
        VALUES (%s, %s, ...);
    """, [values])

conn.commit()
```

## Migrations

### Apply All Migrations

```bash
# Full reset (drops all data)
npx supabase db reset

# Incremental (applies new migrations only)
npx supabase migration up
```

### Create New Migration

```bash
npx supabase migration new migration_name

# Edit: supabase/migrations/<timestamp>_migration_name.sql
```

### Migration Files

1. `20250106000000_create_realtime_schema.sql` - Creates `_realtime` schema
2. `20250106000001_create_metadata_tables.sql` - Creates `metadata_tables` table
3. `20250106000002_create_data_table_template.sql` - Documents data table schema
4. `20250106000003_grant_realtime_permissions.sql` - Grants permissions to Supabase roles
5. `20250106000004_create_dynamic_table_rpc.sql` - Creates `create_data_table()` RPC (not used)
6. `20250107000000_create_rpc_functions.sql` - Creates all 8 RPC functions

## Testing

```bash
# Run dashboard tests (includes DB operations)
cd backend
uv run pytest tests/dashboard/ -v

# Test specific RPC via psql
PGPASSWORD=postgres psql -h 127.0.0.1 -p 54322 -U postgres -d postgres \
  -c "SELECT * FROM public.get_all_tables('_realtime');"

# Test via Python
uv run python3 -c "
from config import supabase_extension
result = supabase_extension.client.rpc('get_all_tables', {
    'schema_name': '_realtime'
}).execute()
print(result.data)
"
```

## Troubleshooting

### "Table does not exist" after creation

**Cause**: PostgREST cache hasn't refreshed
**Solution**: Use psycopg2 for immediate operations after table creation

### "Permission denied for schema _realtime"

**Cause**: Missing grants
**Solution**: Run migration `20250106000003_grant_realtime_permissions.sql` or grant manually:

```sql
GRANT USAGE ON SCHEMA _realtime TO anon, authenticated, service_role;
GRANT ALL ON ALL TABLES IN SCHEMA _realtime TO anon, authenticated, service_role;
```

### RPC function returns empty results

**Cause**: Wrong schema parameter or table doesn't exist
**Solution**: Verify with `\dt _realtime.*` in psql

## Future Considerations

**If Dynamic Tables Become Static:**
If the app evolves to use a fixed schema (no runtime table creation), psycopg2 could be fully removed and all operations migrated to Supabase.

**Performance:**
RPC functions add minimal overhead (<10ms) compared to direct queries. Acceptable for metadata operations.

## References

- **Supabase Docs**: https://supabase.com/docs
- **PostgREST Cache**: https://postgrest.org/en/stable/references/schema_cache.html
- **Memory**: See `supabase_hybrid_architecture` memory for detailed architecture explanation
