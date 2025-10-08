# FAIRDatabase Supabase - Outstanding Action Items

**Overall Status**: System is architecturally sound and functional. **All Priority 1 critical items are complete and production-ready**. Priority 2 and 3 items below address further optimization and enhancement opportunities.

---

## 🔴 Priority 1: Critical (Production-Ready Requirements)

### ✅ 1. Add Indexes on Dynamic Tables

**Location**: `backend/src/dashboard/helpers.py:92-96`
**Status**: ✅ **COMPLETED**
**Impact**: Optimized query performance on patient-based lookups

Index is created automatically on table creation:
```python
CREATE INDEX IF NOT EXISTS idx_{table_name}_{patient_col}
ON _{schema}.{table_name}({patient_col});
```

---

### ✅ 2. Implement Transaction Management

**Location**: `backend/src/dashboard/routes.py:105-119`
**Status**: ✅ **COMPLETED**
**Impact**: Data integrity ensured - transactions rollback on failure

Transaction management implemented in upload route:
```python
try:
    with conn.cursor() as cur:
        # Table creation and data operations
        ...
    conn.commit()
except Exception as e:
    conn.rollback()
    raise
```

---

### ✅ 3. Document or Remove Unused RPC Function

**Location**: `supabase/migrations/20250107000000_rpc_functions.sql:203-283`
**Status**: ✅ **COMPLETED**
**Issue**: `public.create_data_table()` defined but never used

**Resolution**: Comprehensive documentation added explaining:
- Why function exists (API completeness, future-proofing)
- Why it's not used (PostgREST schema cache limitations)
- What to use instead (psycopg2 direct SQL)
- When it could be used (future PostgREST improvements)

---

### ✅ 4. Implement Batch Inserts

**Location**: `backend/src/dashboard/helpers.py:240-320`
**Status**: ✅ **COMPLETED**
**Impact**: Significantly improved performance for large CSV uploads

Batch inserts implemented using `execute_values`:
```python
from psycopg2.extras import execute_values

execute_values(
    cur,
    f"INSERT INTO _{schema}.{table_name} ({patient_col}, {col_names}) VALUES %s",
    batch_data
)
```

---

## 🟡 Priority 2: Important Improvements

### 5. Increase Test Coverage (Current: 64.48% → Target: >80%)

**Gaps**:
- Error scenario tests for RPC functions
- Edge cases in upload workflow
- Configuration validation tests
- Integration tests for multi-table operations

---

### 6. Enhanced Configuration Validation

**Location**: `backend/config.py`
**Gap**: Missing PostgreSQL connection variable validation

Add:
```python
def validate_config():
    required = {
        'SUPABASE_URL': Config.SUPABASE_URL,
        'SUPABASE_ANON_KEY': Config.SUPABASE_ANON_KEY,
        'POSTGRES_HOST': Config.POSTGRES_HOST,
        'POSTGRES_DB_NAME': Config.POSTGRES_DB_NAME
    }
    missing = [k for k, v in required.items() if not v or not v.strip()]
    if missing:
        raise ValueError(f"Missing required configuration: {', '.join(missing)}")
```

Call in `app.py` at startup.

---

### 7. Add Metadata Query Caching

**Issue**: `get_all_tables`, `get_table_columns` hit DB on every call
**Impact**: Unnecessary database load

Simple in-memory cache:
```python
from functools import lru_cache

@lru_cache(maxsize=128)
def get_cached_tables(cache_key):
    # cache_key includes timestamp rounded to nearest minute
    return supabase_extension.safe_rpc_call('get_all_tables', {'schema_name': '_realtime'})
```

---

## 🟢 Priority 3: Optional Enhancements (Future)

### 8. Supabase Storage Integration
- Store uploaded CSV files in Supabase Storage vs local filesystem
- **When**: Production deployment with distributed systems

### 9. Realtime Subscriptions
- Live dashboard updates for multi-user collaboration
- **When**: Collaborative features become requirement

### 10. OAuth Providers
- Add Google, GitHub authentication
- **When**: User base grows beyond research team

### 11. Proactive Token Refresh
- Refresh auth tokens before expiration vs on 401 errors
- **When**: User experience optimization phase

### 12. Edge Functions
- Offload compute-intensive operations (anonymization, transformations)
- **When**: Backend becomes CPU-bound

---

## Effort Estimates

- **P1 (Production-Ready)**: ✅ **COMPLETED** (All 4 items)
- **P2 (Robustness)**: 6-8 hours
- **P3 (Feature Additions)**: 20-40 hours

**Production-Ready Status**: ✅ **System is production-ready**. All P1 critical items are complete. P2 and P3 are optional optimizations and enhancements.
