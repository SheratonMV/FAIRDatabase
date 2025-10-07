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

1. `20250105000000_enable_pgtap.sql` - Enables pgTAP extension for database testing
2. `20250106000000_initial_schema.sql` - Creates `_realtime` schema, `metadata_tables` table, and base permissions
3. `20250107000000_rpc_functions.sql` - Creates all RPC functions (11 total)
4. `20251007000000_enable_rls.sql` - Enables row-level security and updates `create_data_table()` RPC

## RPC Functions

All functions defined in `migrations/20250107000000_rpc_functions.sql`.

### Metadata Operations

- `get_all_tables(schema_name)` - List all tables in schema
- `get_table_columns(table_name, schema_name)` - Get column info for table
- `table_exists(table_name, schema_name)` - Check if table exists
- `search_tables_by_column(column_name, schema_name)` - Find tables with specific column

### Data Operations

- `select_from_table(table_name, row_limit, schema_name)` - Query dynamic table
- `update_table_row(table_name, row_id, updates, schema_name)` - Update row by rowid
- `insert_metadata(table_name, main_table_name, description, origin)` - Insert metadata record
- `create_data_table(schema_name, table_name, column_names, id_column)` - Create table (unused - psycopg2 handles this)

All functions use `SECURITY DEFINER` to access `_realtime` schema from `public`.

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

1. **`01_schema_structure.sql`** - Schema, table, and index tests
   - Verifies `_realtime` schema exists
   - Tests `metadata_tables` structure and columns
   - Checks primary keys and indexes
   - Validates RLS is enabled

2. **`02_rls_policies.sql`** - Row Level Security policy tests
   - Verifies RLS policies exist and are correctly configured
   - Tests permissions for `anon`, `authenticated`, and `service_role`
   - Validates policy commands (SELECT, ALL, etc.)

3. **`03_rpc_functions.sql`** - RPC function tests
   - Tests all 11 RPC functions exist with correct signatures
   - Validates function return types
   - Checks permissions for different roles
   - Tests basic functionality with sample data

**Test Coverage**: 58 tests across 3 files

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
