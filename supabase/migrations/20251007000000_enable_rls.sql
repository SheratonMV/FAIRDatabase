-- ============================================================================
-- FAIRDatabase Row Level Security (RLS) Policies
-- ============================================================================
-- This migration implements comprehensive security policies
--
-- Security Model:
-- 1. metadata_tables: Authenticated users can read, service role can write
-- 2. Dynamic data tables: Authenticated users can read, service role can write
-- 3. Anonymous users: No direct table access (must use RPC functions)
--
-- References:
-- - https://supabase.com/docs/guides/auth/row-level-security

-- ============================================================================
-- STEP 1: ENABLE RLS ON METADATA TABLES
-- ============================================================================

-- Enable RLS on the metadata tracking table
ALTER TABLE _realtime.metadata_tables ENABLE ROW LEVEL SECURITY;

-- ============================================================================
-- STEP 2: CREATE RLS POLICIES FOR METADATA_TABLES
-- ============================================================================

-- Policy: Authenticated users can view all metadata
-- This allows researchers to discover available datasets
CREATE POLICY "authenticated_users_view_metadata"
  ON _realtime.metadata_tables
  FOR SELECT
  TO authenticated
  USING (true);

-- Policy: Service role has full access to metadata
-- This allows the backend to insert/update/delete metadata entries
CREATE POLICY "service_role_full_metadata_access"
  ON _realtime.metadata_tables
  FOR ALL
  TO service_role
  USING (true)
  WITH CHECK (true);

-- ============================================================================
-- STEP 3: REVOKE DIRECT TABLE ACCESS FROM ANON AND AUTHENTICATED
-- ============================================================================

-- Revoke direct table access from anon (they should not access tables directly)
-- They must use RPC functions which have SECURITY DEFINER and additional validation
REVOKE ALL ON TABLE _realtime.metadata_tables FROM anon;

-- Revoke write access from authenticated (they can only read via SELECT policy above)
-- Write operations must go through service role via backend
REVOKE INSERT, UPDATE, DELETE ON TABLE _realtime.metadata_tables FROM authenticated;

-- Keep SELECT access via RLS policy, but ensure it's explicit
GRANT SELECT ON TABLE _realtime.metadata_tables TO authenticated;

-- ============================================================================
-- STEP 4: UPDATE RPC FUNCTION GRANTS
-- ============================================================================

-- Revoke anon access from RPC functions that should require authentication
-- Anonymous users should not be able to query or modify research data
REVOKE EXECUTE ON FUNCTION public.search_tables_by_column(TEXT, TEXT) FROM anon;
REVOKE EXECUTE ON FUNCTION public.get_table_columns(TEXT, TEXT) FROM anon;
REVOKE EXECUTE ON FUNCTION public.table_exists(TEXT, TEXT) FROM anon;
REVOKE EXECUTE ON FUNCTION public.get_all_tables(TEXT) FROM anon;
REVOKE EXECUTE ON FUNCTION public.select_from_table(TEXT, INT, TEXT) FROM anon;
REVOKE EXECUTE ON FUNCTION public.update_table_row(TEXT, INT, JSONB, TEXT) FROM anon;
REVOKE EXECUTE ON FUNCTION public.insert_metadata(TEXT, TEXT, TEXT, TEXT) FROM anon;

-- Grant to service_role explicitly for backend operations
-- Note: Function signature updated to match standardized parameter order (schema_name last with default)
GRANT EXECUTE ON FUNCTION public.create_data_table(TEXT, TEXT[], TEXT, TEXT) TO service_role;

-- ============================================================================
-- STEP 5: CREATE HELPER FUNCTION FOR DYNAMIC TABLE RLS
-- ============================================================================

-- Helper function to enable RLS on dynamically created data tables
-- This should be called after create_data_table()
CREATE OR REPLACE FUNCTION public.enable_table_rls(
  p_table_name TEXT,
  schema_name TEXT DEFAULT '_realtime'
)
RETURNS BOOLEAN
SECURITY DEFINER
SET search_path = public, _realtime
AS $$
DECLARE
  v_sql TEXT;
BEGIN
  -- Validate table exists
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.tables
    WHERE table_schema = schema_name AND table_name = p_table_name
  ) THEN
    RAISE EXCEPTION 'Table % does not exist in schema %', p_table_name, schema_name;
  END IF;

  -- Enable RLS on the table
  v_sql := format('ALTER TABLE %I.%I ENABLE ROW LEVEL SECURITY', schema_name, p_table_name);
  EXECUTE v_sql;

  -- Create policy: Authenticated users can view all data
  v_sql := format(
    'CREATE POLICY "authenticated_users_view_data" ON %I.%I FOR SELECT TO authenticated USING (true)',
    schema_name, p_table_name
  );
  EXECUTE v_sql;

  -- Create policy: Service role has full access
  v_sql := format(
    'CREATE POLICY "service_role_full_data_access" ON %I.%I FOR ALL TO service_role USING (true) WITH CHECK (true)',
    schema_name, p_table_name
  );
  EXECUTE v_sql;

  -- Revoke direct access from anon
  v_sql := format('REVOKE ALL ON TABLE %I.%I FROM anon', schema_name, p_table_name);
  EXECUTE v_sql;

  -- Revoke write access from authenticated
  v_sql := format('REVOKE INSERT, UPDATE, DELETE ON TABLE %I.%I FROM authenticated', schema_name, p_table_name);
  EXECUTE v_sql;

  -- Grant SELECT to authenticated (enforced by RLS policy)
  v_sql := format('GRANT SELECT ON TABLE %I.%I TO authenticated', schema_name, p_table_name);
  EXECUTE v_sql;

  RETURN TRUE;
EXCEPTION
  WHEN OTHERS THEN
    RAISE EXCEPTION 'Failed to enable RLS: %', SQLERRM;
END;
$$ LANGUAGE plpgsql;

-- Grant execute to service_role only (this is an administrative function)
GRANT EXECUTE ON FUNCTION public.enable_table_rls(TEXT, TEXT) TO service_role;

-- ============================================================================
-- STEP 6: UPDATE create_data_table TO AUTO-ENABLE RLS
-- ============================================================================

-- Update the create_data_table function to automatically enable RLS on new tables
-- This updates the function created in 20250107000000_rpc_functions.sql to add RLS support
CREATE OR REPLACE FUNCTION public.create_data_table(
  p_table_name TEXT,
  p_columns TEXT[],
  p_patient_col TEXT,
  schema_name TEXT DEFAULT '_realtime'
)
RETURNS BOOLEAN AS $$
DECLARE
  v_cols_def TEXT;
  v_sql TEXT;
  v_col TEXT;
BEGIN
  -- Validate schema exists (standardized to use '_realtime' like other RPC functions)
  IF schema_name NOT IN ('_realtime') THEN
    RAISE EXCEPTION 'Invalid schema name: %', schema_name;
  END IF;

  -- Build column definitions
  v_cols_def := '';
  FOREACH v_col IN ARRAY p_columns
  LOOP
    IF v_cols_def != '' THEN
      v_cols_def := v_cols_def || ', ';
    END IF;
    -- Sanitize column name and add TEXT type
    v_cols_def := v_cols_def || format('%I TEXT', v_col);
  END LOOP;

  -- Build CREATE TABLE statement
  v_sql := format(
    'CREATE TABLE IF NOT EXISTS %I.%I (
      rowid SERIAL PRIMARY KEY,
      %I TEXT NOT NULL,
      %s
    )',
    schema_name,
    p_table_name,
    p_patient_col,
    v_cols_def
  );

  -- Execute the CREATE TABLE
  EXECUTE v_sql;

  -- Create index on patient column for better query performance
  EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%I_%I ON %I.%I(%I)',
                 p_table_name, p_patient_col, schema_name, p_table_name, p_patient_col);

  -- Enable RLS on the new table
  v_sql := format('ALTER TABLE %I.%I ENABLE ROW LEVEL SECURITY', schema_name, p_table_name);
  EXECUTE v_sql;

  -- Create policy: Authenticated users can view all data
  v_sql := format(
    'CREATE POLICY "authenticated_users_view_data" ON %I.%I FOR SELECT TO authenticated USING (true)',
    schema_name, p_table_name
  );
  EXECUTE v_sql;

  -- Create policy: Service role has full access
  v_sql := format(
    'CREATE POLICY "service_role_full_data_access" ON %I.%I FOR ALL TO service_role USING (true) WITH CHECK (true)',
    schema_name, p_table_name
  );
  EXECUTE v_sql;

  -- Revoke direct access from anon
  v_sql := format('REVOKE ALL ON TABLE %I.%I FROM anon', schema_name, p_table_name);
  EXECUTE v_sql;

  -- Revoke write access from authenticated (they can only read)
  v_sql := format('REVOKE INSERT, UPDATE, DELETE ON %I.%I FROM authenticated', schema_name, p_table_name);
  EXECUTE v_sql;

  -- Grant SELECT to authenticated (enforced by RLS policy)
  v_sql := format('GRANT SELECT ON TABLE %I.%I TO authenticated', schema_name, p_table_name);
  EXECUTE v_sql;

  -- Grant all permissions to service role
  EXECUTE format('GRANT ALL ON TABLE %I.%I TO service_role', schema_name, p_table_name);

  -- Grant sequence access to service_role only (for insertions)
  EXECUTE format('REVOKE ALL ON SEQUENCE %I.%I_rowid_seq FROM anon, authenticated', schema_name, p_table_name);
  EXECUTE format('GRANT USAGE, SELECT ON SEQUENCE %I.%I_rowid_seq TO service_role', schema_name, p_table_name);

  RETURN TRUE;
EXCEPTION WHEN OTHERS THEN
  RAISE EXCEPTION 'Failed to create table: %', SQLERRM;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- ============================================================================
-- DOCUMENTATION
-- ============================================================================

COMMENT ON POLICY "authenticated_users_view_metadata" ON _realtime.metadata_tables IS
  'Allows authenticated users to view metadata for dataset discovery';

COMMENT ON POLICY "service_role_full_metadata_access" ON _realtime.metadata_tables IS
  'Allows backend (service role) to manage metadata entries';

COMMENT ON FUNCTION public.enable_table_rls(TEXT, TEXT) IS
  'Helper function to enable RLS on dynamically created data tables. Should be called after table creation.';
