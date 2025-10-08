# Supabase Configuration

## Local Development

Start local Supabase instance:

```bash
npx supabase start
```

This starts Docker containers with:
- **Database**: `postgres://postgres:postgres@127.0.0.1:54322/postgres`
- **Studio**: `http://127.0.0.1:54323`
- **API**: `http://127.0.0.1:54321`

## Migrations

### Apply Migrations

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

### Existing Migrations

1. `00_enable_pgtap.sql` - Enables pgTAP extension for database testing
2. `01_schema_and_rls.sql` - Creates `_realtime` schema, `metadata_tables` table with user_id, and RLS policies for user-level data isolation
3. `02_rpc_functions.sql` - Creates all RPC functions (10 total) with user isolation built-in

## RPC Functions

All functions defined in `migrations/02_rpc_functions.sql`.

### Information Schema Functions

- `search_tables_by_column(p_column_name, p_schema_name)` - Find tables with specific column (case-insensitive)
- `get_table_columns(p_table_name, p_schema_name)` - Get column info for table
- `table_exists(p_table_name, p_schema_name)` - Check if table exists
- `get_all_tables(p_schema_name)` - List all tables in schema

### Data Query Functions (User Isolation Built-in)

- `select_from_table(p_table_name, p_row_limit, p_schema_name)` - Query dynamic table (filters by user_id)
- `update_table_row(p_table_name, p_row_id, p_updates, p_schema_name)` - Update row (enforces user ownership)

### Metadata Functions

- `insert_metadata(p_table_name, p_main_table, p_description, p_origin)` - Insert metadata with automatic user_id capture

### Table Creation (Service Role Only)

- `create_data_table(p_schema_name, p_table_name, p_column_names, p_id_column)` - Create dynamic table with:
  - user_id column for data isolation
  - Indexes on user_id and ID column
  - Full RLS policies (users see only their data)
  - Proper permissions
  - PostgREST schema cache reload

### Helper Functions

- `get_current_user_id()` - Returns authenticated user UUID
- `user_owns_table(p_table_name)` - Check if user owns a table

**Security Model**: All functions use `SECURITY DEFINER`. Only authenticated users have EXECUTE permissions. Service role bypasses RLS for admin operations.

All parameter names use `p_` prefix for consistency.

## Schema Configuration

The `_realtime` schema is enabled in `config.toml`:

```toml
[api]
schemas = ["public", "graphql_public", "_realtime"]
```

This allows PostgREST to serve the `_realtime` schema via the API.

## Testing Migrations

### Via psql

```bash
PGPASSWORD=postgres psql -h 127.0.0.1 -p 54322 -U postgres -d postgres \
  -c "SELECT * FROM public.get_all_tables('_realtime');"
```

### Via Python

```bash
cd backend
uv run python3 -c "
from config import supabase_extension
result = supabase_extension.client.rpc('get_all_tables', {
    'schema_name': '_realtime'
}).execute()
print(result.data)
"
```

### Via pytest

```bash
cd backend
uv run pytest tests/dashboard/ -v
```

## Database Testing with pgTAP

FAIRDatabase uses [pgTAP](https://pgtap.org/) for database-level testing. Tests are located in `supabase/tests/`.

### Running pgTAP Tests

```bash
# Run all database tests
npx supabase test db

# Reset database and run tests
npx supabase db reset && npx supabase test db
```

### Test Files

1. **`01_schema_structure.sql`** - Schema, table, and index tests (19 tests)
   - Verifies `_realtime` schema exists
   - Tests `metadata_tables` structure including `user_id` column
   - Checks primary keys and indexes (including `idx_metadata_user_id`)
   - Validates RLS is enabled

2. **`02_rls_policies.sql`** - Row Level Security policy tests (12 tests)
   - Verifies user-level isolation policies (5 policies)
   - Tests permissions for `authenticated` and `service_role`
   - Validates policy commands (SELECT, INSERT, UPDATE, DELETE, ALL)
   - Ensures anon has no access

3. **`03_rpc_functions.sql`** - RPC function tests (35 tests)
   - Tests all 10 RPC functions exist with correct signatures
   - Validates function return types
   - Checks permissions (authenticated only, service_role for admin)
   - Tests basic functionality with sample data
   - Includes helper functions (`get_current_user_id`, `user_owns_table`)

**Test Coverage**: 67 tests across 3 files (19 + 13 + 35)

### Writing New pgTAP Tests

```sql
BEGIN;
SELECT plan(5);  -- Number of tests

-- Your tests here
SELECT has_table('_realtime', 'new_table', 'new_table should exist');
-- ...

SELECT * FROM finish();
ROLLBACK;
```

See [pgTAP documentation](https://pgtap.org/documentation.html) for available test functions.

## Production Deployment

When deploying to Supabase production:

1. Link project: `npx supabase link --project-ref <ref>`
2. Push migrations: `npx supabase db push`
3. Verify in Supabase Studio

**Note**: Never push migrations to production without testing locally first.

---

**Reminder**: Migrations are one-way. Always test with `db reset` before pushing to production.
