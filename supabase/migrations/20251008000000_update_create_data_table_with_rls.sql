-- ============================================================================
-- Update create_data_table RPC Function with Full RLS Support
-- ============================================================================
-- This migration updates the create_data_table function to match the security
-- features of the psycopg2 implementation, making it production-ready.
--
-- Changes from previous version:
-- 1. Enable Row Level Security (RLS) on created tables
-- 2. Create RLS policies for authenticated users (read-only) and service_role (full access)
-- 3. Revoke direct access from anon role
-- 4. Revoke write access from authenticated (enforce read-only via RLS)
-- 5. Grant SELECT to authenticated, ALL to service_role
-- 6. Add NOTIFY pgrst for schema cache reload
-- 7. Update function signature to accept column_names array (consistent naming)
--
-- IMPORTANT: This function is now PRODUCTION-READY and should be used instead
-- of direct psycopg2 table creation to maintain pure Supabase patterns.

-- Drop old function signature to avoid "function name is not unique" error
DROP FUNCTION IF EXISTS public.create_data_table(TEXT, TEXT[], TEXT, TEXT);

CREATE OR REPLACE FUNCTION public.create_data_table(
  p_schema_name TEXT,
  p_table_name TEXT,
  p_column_names TEXT[],
  p_id_column TEXT
)
RETURNS BOOLEAN AS $$
DECLARE
  v_cols_def TEXT;
  v_sql TEXT;
  v_col TEXT;
  v_full_table_name TEXT;
BEGIN
  -- Validate schema exists (standardized to use '_realtime')
  IF p_schema_name NOT IN ('_realtime') THEN
    RAISE EXCEPTION 'Invalid schema name: %. Only _realtime is allowed.', p_schema_name;
  END IF;

  -- Build full table name for later use
  v_full_table_name := format('%I.%I', p_schema_name, p_table_name);

  -- Build column definitions
  v_cols_def := '';
  FOREACH v_col IN ARRAY p_column_names
  LOOP
    IF v_cols_def != '' THEN
      v_cols_def := v_cols_def || ', ';
    END IF;
    -- Sanitize column name and add TEXT type
    v_cols_def := v_cols_def || format('%I TEXT', v_col);
  END LOOP;

  -- ============================================================================
  -- 1. CREATE TABLE
  -- ============================================================================
  v_sql := format(
    'CREATE TABLE IF NOT EXISTS %I.%I (
      rowid SERIAL PRIMARY KEY,
      %I TEXT NOT NULL,
      %s
    )',
    p_schema_name,
    p_table_name,
    p_id_column,
    v_cols_def
  );
  EXECUTE v_sql;

  -- ============================================================================
  -- 2. CREATE INDEX on ID column for performance
  -- ============================================================================
  EXECUTE format(
    'CREATE INDEX IF NOT EXISTS idx_%I_%I ON %I.%I(%I)',
    p_table_name, p_id_column, p_schema_name, p_table_name, p_id_column
  );

  -- ============================================================================
  -- 3. ENABLE ROW LEVEL SECURITY
  -- ============================================================================
  EXECUTE format('ALTER TABLE %s ENABLE ROW LEVEL SECURITY', v_full_table_name);

  -- ============================================================================
  -- 4. DROP EXISTING POLICIES (for idempotency)
  -- ============================================================================
  EXECUTE format('DROP POLICY IF EXISTS "authenticated_users_view_data" ON %s', v_full_table_name);
  EXECUTE format('DROP POLICY IF EXISTS "service_role_full_data_access" ON %s', v_full_table_name);

  -- ============================================================================
  -- 5. CREATE RLS POLICIES
  -- ============================================================================

  -- Policy: Authenticated users can view all data (read-only)
  EXECUTE format(
    'CREATE POLICY "authenticated_users_view_data"
    ON %s
    FOR SELECT
    TO authenticated
    USING (true)',
    v_full_table_name
  );

  -- Policy: Service role has full access (read + write)
  EXECUTE format(
    'CREATE POLICY "service_role_full_data_access"
    ON %s
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true)',
    v_full_table_name
  );

  -- ============================================================================
  -- 6. REVOKE DIRECT ACCESS from anon
  -- ============================================================================
  EXECUTE format('REVOKE ALL ON TABLE %s FROM anon', v_full_table_name);

  -- ============================================================================
  -- 7. REVOKE WRITE ACCESS from authenticated (read-only via RLS)
  -- ============================================================================
  EXECUTE format(
    'REVOKE INSERT, UPDATE, DELETE ON TABLE %s FROM authenticated',
    v_full_table_name
  );

  -- ============================================================================
  -- 8. GRANT PERMISSIONS
  -- ============================================================================

  -- Grant SELECT to authenticated (enforced by RLS policy)
  EXECUTE format('GRANT SELECT ON TABLE %s TO authenticated', v_full_table_name);

  -- Grant all permissions to service role
  EXECUTE format('GRANT ALL ON TABLE %s TO service_role', v_full_table_name);
  EXECUTE format(
    'GRANT USAGE, SELECT ON SEQUENCE %I.%I_rowid_seq TO service_role',
    p_schema_name, p_table_name
  );

  -- ============================================================================
  -- 9. REVOKE SEQUENCE ACCESS from anon and authenticated
  -- ============================================================================
  EXECUTE format(
    'REVOKE ALL ON SEQUENCE %I.%I_rowid_seq FROM anon, authenticated',
    p_schema_name, p_table_name
  );

  -- ============================================================================
  -- 10. NOTIFY PostgREST to reload schema cache
  -- ============================================================================
  NOTIFY pgrst, 'reload schema';

  RETURN TRUE;

EXCEPTION WHEN OTHERS THEN
  RAISE EXCEPTION 'Failed to create table %: %', p_table_name, SQLERRM;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER
SET search_path = public, _realtime;

-- ============================================================================
-- GRANT EXECUTE PERMISSIONS
-- ============================================================================
-- Allow service_role to call this function (table creation is admin operation)
GRANT EXECUTE ON FUNCTION public.create_data_table(TEXT, TEXT, TEXT[], TEXT) TO service_role;

-- ============================================================================
-- COMMENTS
-- ============================================================================
COMMENT ON FUNCTION public.create_data_table IS
'Creates a dynamic data table in _realtime schema with full RLS configuration.
Uses SECURITY DEFINER with proper RLS policies for authenticated (read-only)
and service_role (full access). Includes schema cache reload notification.
This function replaces direct psycopg2 table creation for pure Supabase patterns.';
