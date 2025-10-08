# Backend Development Guide

## Database Usage Patterns

### Supabase Client

The Supabase client is initialized in `config.py` as `supabase_extension`.

#### Query Execution Convention

**ALWAYS call `.execute()` explicitly on Supabase queries.**

```python
from config import supabase_extension

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

# ✅ Auth operations return results directly (no .execute() needed)
user = supabase_extension.client.auth.sign_in_with_password(email, password)
```

#### Helper: `safe_rpc_call()`

Prefer this helper for RPC operations (handles `.execute()` and error logging):

```python
from config import supabase_extension

# Instead of: supabase_extension.client.rpc('function', params).execute()
data = supabase_extension.safe_rpc_call('function_name', {'param': 'value'})
```

**Chaining Format**: Use parentheses for multi-line queries:

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

#### Async Support (Flask 3.1+)

Flask 3.1+ supports async route handlers. Use async clients for I/O-bound operations that benefit from concurrency.

**Async Clients**:

```python
from config import supabase_extension

# Async client with anon key (respects RLS)
@app.route('/async-data')
async def async_data():
    client = await supabase_extension.async_client
    response = await client.rpc('get_all_tables', {}).execute()
    return jsonify(response.data)

# Async service role client for admin operations
@app.route('/admin-async-data')
async def admin_async_data():
    client = await supabase_extension.async_service_role_client
    response = await client.rpc('admin_function', {}).execute()
    return jsonify(response.data)
```

**Helper: `async_safe_rpc_call()`**

Prefer this helper for async RPC operations (handles `.execute()` and error logging):

```python
from config import supabase_extension

@app.route('/async-endpoint')
async def async_endpoint():
    # Automatically handles async client creation and error handling
    data = await supabase_extension.async_safe_rpc_call('function_name', {'param': 'value'})
    return jsonify(data)
```

**When to Use Async**:
- Multiple independent database queries that can run concurrently
- External API calls combined with database operations
- Long-running I/O operations
- High-concurrency scenarios

**Important Notes**:
- Async routes require Flask 3.1+
- Cannot mix sync/async in the same route
- psycopg2 operations remain synchronous
- Test suite runs with 180s timeout to accommodate async operations

### psycopg2 (Bulk Inserts Only)

Used exclusively for bulk data inserts for performance.

**Table Creation**: Use `create_data_table` RPC function instead

```python
from config import supabase_extension

# Create table via Supabase RPC (service_role required)
supabase_extension.service_role_client.rpc('create_data_table', {
    'p_schema_name': '_realtime',
    'p_table_name': 'my_table',
    'p_column_names': ['col1', 'col2', 'col3'],
    'p_id_column': 'patient_id'
}).execute()
```

**Bulk Inserts**: Use psycopg2 for large datasets

```python
from flask import g
from config import get_db
from psycopg2.extras import execute_values

conn = g.db  # Get connection from Flask context
with conn.cursor() as cur:
    # Batch insert for performance
    execute_values(
        cur,
        """
        INSERT INTO _realtime.my_table (patient_id, col1, col2)
        VALUES %s
        """,
        [(val1, val2, val3), (val1, val2, val3), ...]
    )

conn.commit()
```

### TypedDict Return Types

RPC functions return TypedDict types for better type safety:

```python
from typing import TypedDict

class TableInfo(TypedDict):
    table_name: str
    table_type: str

# Usage
tables: list[TableInfo] = supabase_extension.safe_rpc_call(
    'get_all_tables',
    {'schema_name': '_realtime'}
)
```

See `config.py` for all defined RPC return types.

## Supabase RPC Functions

All functions use `SECURITY DEFINER` to access `_realtime` schema.

### Metadata Functions

```python
# Get all tables in schema
tables = supabase_extension.safe_rpc_call('get_all_tables', {'schema_name': '_realtime'})

# Get columns for a table
columns = supabase_extension.safe_rpc_call('get_table_columns', {
    'table_name': 'my_table',
    'schema_name': '_realtime'
})

# Check if table exists
exists = supabase_extension.safe_rpc_call('table_exists', {
    'table_name': 'my_table',
    'schema_name': '_realtime'
})

# Find tables with specific column
tables = supabase_extension.safe_rpc_call('search_tables_by_column', {
    'column_name': 'patient_id',
    'schema_name': '_realtime'
})
```

### Data Access Functions

```python
# Select from dynamic table (returns list of dicts)
rows = supabase_extension.safe_rpc_call('select_from_table', {
    'table_name': 'my_table_p1',
    'row_limit': 100,
    'schema_name': '_realtime'
})

# Update a row (by rowid, not id)
success = supabase_extension.safe_rpc_call('update_table_row', {
    'table_name': 'my_table_p1',
    'row_id': 42,
    'updates': {'column_name': 'new_value'},
    'schema_name': '_realtime'
})
```

### Helper Functions

```python
# Insert metadata record
supabase_extension.safe_rpc_call('insert_metadata', {
    'table_name': 'my_table',
    'main_table_name': 'main_table_name',
    'description': 'Description text',
    'origin': 'Origin text'
})
```

## Testing

```bash
# Run all tests
cd backend
uv run pytest

# Run specific test file
uv run pytest tests/dashboard/test_routes.py -v

# Run with coverage
uv run pytest --cov=src
```

## Code Organization

```
backend/
├── src/
│   ├── auth/              # Authentication routes and logic
│   ├── dashboard/         # Dashboard routes and helpers
│   │   ├── routes.py      # Dashboard endpoints
│   │   └── helpers.py     # DB operations and utilities
│   ├── data/              # Data management
│   ├── privacy/           # Privacy features
│   ├── main/              # Home/landing pages
│   └── anonymization/     # Anonymization logic
├── tests/                 # Test suite
├── app.py                 # Flask app entry point
└── config.py              # Configuration and Supabase setup
```

## Flask Patterns

### Database Connection Lifecycle

**Connection Strategy**: Direct connections relying on Supabase pooler

The application uses direct `psycopg2.connect()` calls without app-level connection pooling. This approach leverages Supabase's Supavisor connection pooler (Session mode, port 5432) for efficient connection management at the infrastructure level.

**Benefits**:
- Eliminates duplicate pooling layers
- Leverages Supabase's intelligent connection sharing and monitoring
- Simpler application code with fewer moving parts
- Automatic connection reuse across requests via Supabase pooler

```python
# In app.py
from config import get_db, teardown_db

@app.before_request
def before_request():
    # Connection created lazily on first g.db access
    # Each request gets a new connection from Supabase pooler
    pass

@app.teardown_appcontext
def teardown_db_handler(exception):
    teardown_db(exception)  # Closes connection, returned to Supabase pooler
```

**Per-request lifecycle**:
1. Request starts → no connection yet
2. First `g.db` access → `psycopg2.connect()` called (Supabase pooler provides connection)
3. Request completes → `teardown_db()` closes connection (returned to Supabase pooler)
4. Next request → new connection from pooler (may be same underlying connection, pooled by Supabase)

**Production configuration**: Use Session mode pooler (`pooler.supabase.com:5432`) for persistent backends like Flask. Transaction mode (port 6543) is only for serverless functions.

### Route Pattern

```python
from flask import Blueprint, jsonify
from config import supabase_extension

bp = Blueprint('my_module', __name__, url_prefix='/my-module')

@bp.route('/endpoint')
def my_endpoint():
    try:
        data = supabase_extension.safe_rpc_call('function_name', {})
        return jsonify(data), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
```

## Common Pitfalls

1. **Forgetting `.execute()`**: Supabase queries don't run without it
2. **Wrong schema**: Remember to use `_realtime` schema, not `public`
3. **Using `id` instead of `rowid`**: Dynamic tables use `rowid` as primary key
4. **Not committing**: Remember `conn.commit()` after psycopg2 bulk insert operations
5. **Wrong client for table creation**: Use `service_role_client` for `create_data_table`, not regular client

---

**Note**: This guide reflects current patterns. Follow CLAUDE.md principles when extending.
