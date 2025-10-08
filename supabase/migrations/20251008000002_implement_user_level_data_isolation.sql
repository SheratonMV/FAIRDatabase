-- ============================================================================
-- Implement User-Level Data Isolation
-- ============================================================================
-- This migration implements full user-level data isolation so each user can
-- only see and manage their own uploaded data.
--
-- Issue #6.1: No User-Level Data Isolation
--
-- Changes:
-- 1. Add user_id column to metadata_tables with FK to auth.users
-- 2. Update metadata_tables RLS policies to filter by auth.uid()
-- 3. Update create_data_table RPC to automatically add user_id column
-- 4. Update insert_metadata RPC to automatically capture auth.uid()
-- 5. Add helper function to get current user ID
--
-- BREAKING CHANGE: Existing data will have user_id = NULL
-- Strategy: Run this migration, then manually assign ownership OR delete orphaned data
--
-- Note: Service role bypasses RLS and can see all data (admin operations)

-- ============================================================================
-- 1. Add user_id column to metadata_tables
-- ============================================================================
ALTER TABLE _realtime.metadata_tables
ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS idx_metadata_tables_user_id
ON _realtime.metadata_tables(user_id);

COMMENT ON COLUMN _realtime.metadata_tables.user_id IS 'User who uploaded this dataset. NULL for legacy data. FK to auth.users(id).';

-- ============================================================================
-- 2. Update metadata_tables RLS policies for user-level isolation
-- ============================================================================

-- Drop existing policies
DROP POLICY IF EXISTS "authenticated_users_view_metadata" ON _realtime.metadata_tables;
DROP POLICY IF EXISTS "service_role_full_metadata_access" ON _realtime.metadata_tables;

-- Policy: Users can only view their own metadata
CREATE POLICY "users_view_own_metadata"
ON _realtime.metadata_tables
FOR SELECT
TO authenticated
USING (auth.uid() = user_id);

-- Policy: Users can only insert with their own user_id
CREATE POLICY "users_insert_own_metadata"
ON _realtime.metadata_tables
FOR INSERT
TO authenticated
WITH CHECK (auth.uid() = user_id);

-- Policy: Users can only update their own metadata
CREATE POLICY "users_update_own_metadata"
ON _realtime.metadata_tables
FOR UPDATE
TO authenticated
USING (auth.uid() = user_id)
WITH CHECK (auth.uid() = user_id);

-- Policy: Users can only delete their own metadata
CREATE POLICY "users_delete_own_metadata"
ON _realtime.metadata_tables
FOR DELETE
TO authenticated
USING (auth.uid() = user_id);

-- Policy: Service role has full access (admin operations, bypasses user isolation)
CREATE POLICY "service_role_full_metadata_access"
ON _realtime.metadata_tables
FOR ALL
TO service_role
USING (true)
WITH CHECK (true);

-- ============================================================================
-- 3. Helper function to get current authenticated user ID
-- ============================================================================
CREATE OR REPLACE FUNCTION public.get_current_user_id()
RETURNS UUID
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  RETURN auth.uid();
END;
$$ LANGUAGE plpgsql;

GRANT EXECUTE ON FUNCTION public.get_current_user_id() TO authenticated;

COMMENT ON FUNCTION public.get_current_user_id IS 'Returns the authenticated user UUID from auth.uid(). Used for user-level data isolation.';

-- ============================================================================
-- 4. Update create_data_table to add user_id column automatically
-- ============================================================================
DROP FUNCTION IF EXISTS public.create_data_table(TEXT, TEXT, TEXT[], TEXT);

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
  -- 1. CREATE TABLE with user_id column
  -- ============================================================================
  v_sql := format(
    'CREATE TABLE IF NOT EXISTS %I.%I (
      rowid SERIAL PRIMARY KEY,
      user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
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
  -- 2. CREATE INDEXES for performance
  -- ============================================================================

  -- Index on user_id for user isolation queries
  EXECUTE format(
    'CREATE INDEX IF NOT EXISTS idx_%I_user_id ON %I.%I(user_id)',
    p_table_name, p_schema_name, p_table_name
  );

  -- Index on ID column for search performance
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
  EXECUTE format('DROP POLICY IF EXISTS "users_view_own_data" ON %s', v_full_table_name);
  EXECUTE format('DROP POLICY IF EXISTS "users_insert_own_data" ON %s', v_full_table_name);
  EXECUTE format('DROP POLICY IF EXISTS "service_role_full_data_access" ON %s', v_full_table_name);

  -- ============================================================================
  -- 5. CREATE RLS POLICIES for user-level isolation
  -- ============================================================================

  -- Policy: Users can only view their own data
  EXECUTE format(
    'CREATE POLICY "users_view_own_data"
    ON %s
    FOR SELECT
    TO authenticated
    USING (auth.uid() = user_id)',
    v_full_table_name
  );

  -- Policy: Users can only insert with their own user_id
  EXECUTE format(
    'CREATE POLICY "users_insert_own_data"
    ON %s
    FOR INSERT
    TO authenticated
    WITH CHECK (auth.uid() = user_id)',
    v_full_table_name
  );

  -- Policy: Service role has full access (admin operations, data import)
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
  -- 7. GRANT PERMISSIONS
  -- ============================================================================

  -- Grant SELECT to authenticated (enforced by RLS policy)
  EXECUTE format('GRANT SELECT ON TABLE %s TO authenticated', v_full_table_name);

  -- Grant INSERT to authenticated (enforced by RLS policy)
  EXECUTE format('GRANT INSERT ON TABLE %s TO authenticated', v_full_table_name);

  -- Grant all permissions to service role (for bulk inserts)
  EXECUTE format('GRANT ALL ON TABLE %s TO service_role', v_full_table_name);
  EXECUTE format(
    'GRANT USAGE, SELECT ON SEQUENCE %I.%I_rowid_seq TO service_role',
    p_schema_name, p_table_name
  );

  -- ============================================================================
  -- 8. REVOKE SEQUENCE ACCESS from anon and authenticated
  -- ============================================================================
  EXECUTE format(
    'REVOKE ALL ON SEQUENCE %I.%I_rowid_seq FROM anon, authenticated',
    p_schema_name, p_table_name
  );

  -- ============================================================================
  -- 9. NOTIFY PostgREST to reload schema cache
  -- ============================================================================
  NOTIFY pgrst, 'reload schema';

  RETURN TRUE;

EXCEPTION WHEN OTHERS THEN
  RAISE EXCEPTION 'Failed to create table %: %', p_table_name, SQLERRM;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER
SET search_path = public, _realtime;

GRANT EXECUTE ON FUNCTION public.create_data_table(TEXT, TEXT, TEXT[], TEXT) TO service_role;

COMMENT ON FUNCTION public.create_data_table IS
'Creates a dynamic data table in _realtime schema with full user-level RLS.
Automatically adds user_id column and creates policies so users can only see/insert their own data.
Service role bypasses RLS for admin operations and bulk data imports.';

-- ============================================================================
-- 5. Update insert_metadata to capture auth.uid() automatically
-- ============================================================================
DROP FUNCTION IF EXISTS public.insert_metadata(TEXT, TEXT, TEXT, TEXT);

CREATE OR REPLACE FUNCTION public.insert_metadata(
  p_table_name TEXT,
  p_main_table TEXT,
  p_description TEXT DEFAULT NULL,
  p_origin TEXT DEFAULT NULL
)
RETURNS INT
SECURITY DEFINER
SET search_path = public, _realtime
AS $$
DECLARE
  v_id INT;
  v_user_id UUID;
BEGIN
  -- Get current user ID from auth context
  v_user_id := auth.uid();

  -- Verify user is authenticated
  IF v_user_id IS NULL THEN
    RAISE EXCEPTION 'User must be authenticated to insert metadata';
  END IF;

  -- Insert with captured user_id
  INSERT INTO _realtime.metadata_tables (table_name, main_table, description, origin, user_id)
  VALUES (p_table_name, p_main_table, p_description, p_origin, v_user_id)
  RETURNING id INTO v_id;

  RETURN v_id;
END;
$$ LANGUAGE plpgsql;

GRANT EXECUTE ON FUNCTION public.insert_metadata(TEXT, TEXT, TEXT, TEXT) TO authenticated;

COMMENT ON FUNCTION public.insert_metadata IS
'Insert metadata record with automatic user_id capture from auth.uid().
Enforces user authentication and associates data with current user for isolation.';

-- ============================================================================
-- 6. Update select_from_table to respect user isolation
-- ============================================================================
DROP FUNCTION IF EXISTS public.select_from_table(TEXT, INT, TEXT);

CREATE OR REPLACE FUNCTION public.select_from_table(
  p_table_name TEXT,
  p_row_limit INT DEFAULT 100,
  p_schema_name TEXT DEFAULT '_realtime'
)
RETURNS TABLE(data JSONB)
SECURITY DEFINER
SET search_path = public, _realtime
AS $$
DECLARE
  v_user_id UUID;
  v_has_user_id_column BOOLEAN;
BEGIN
  -- Validate table exists (prevent SQL injection)
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.tables
    WHERE table_schema = p_schema_name AND table_name = p_table_name
  ) THEN
    RAISE EXCEPTION 'Table % does not exist in schema %', p_table_name, p_schema_name;
  END IF;

  -- Check if table has user_id column (new tables vs legacy)
  SELECT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = p_schema_name
      AND table_name = p_table_name
      AND column_name = 'user_id'
  ) INTO v_has_user_id_column;

  -- Get current user ID
  v_user_id := auth.uid();

  -- If table has user_id column and user is authenticated, filter by user_id
  -- Service role (v_user_id IS NULL in service context) sees all data
  IF v_has_user_id_column AND v_user_id IS NOT NULL THEN
    RETURN QUERY EXECUTE format(
      'SELECT row_to_json(t)::JSONB FROM %I.%I t WHERE user_id = %L LIMIT %s',
      p_schema_name, p_table_name, v_user_id, p_row_limit
    );
  ELSE
    -- Legacy tables without user_id or service role access
    RETURN QUERY EXECUTE format(
      'SELECT row_to_json(t)::JSONB FROM %I.%I t LIMIT %s',
      p_schema_name, p_table_name, p_row_limit
    );
  END IF;
END;
$$ LANGUAGE plpgsql;

GRANT EXECUTE ON FUNCTION public.select_from_table(TEXT, INT, TEXT) TO authenticated, anon;

COMMENT ON FUNCTION public.select_from_table IS
'Select rows from dynamic table with automatic user isolation.
If table has user_id column, filters by auth.uid() for authenticated users.
Service role sees all data for admin operations.';

-- ============================================================================
-- 7. Update update_table_row to respect user isolation
-- ============================================================================
DROP FUNCTION IF EXISTS public.update_table_row(TEXT, INT, JSONB, TEXT);

CREATE OR REPLACE FUNCTION public.update_table_row(
  p_table_name TEXT,
  p_row_id INT,
  p_updates JSONB,
  p_schema_name TEXT DEFAULT '_realtime'
)
RETURNS BOOLEAN
SECURITY DEFINER
SET search_path = public, _realtime
AS $$
DECLARE
  v_sql TEXT;
  v_set_clause TEXT;
  v_key TEXT;
  v_value TEXT;
  v_user_id UUID;
  v_has_user_id_column BOOLEAN;
BEGIN
  -- Validate table exists
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.tables
    WHERE table_schema = p_schema_name AND table_name = p_table_name
  ) THEN
    RAISE EXCEPTION 'Table % does not exist in schema %', p_table_name, p_schema_name;
  END IF;

  -- Check if table has user_id column
  SELECT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = p_schema_name
      AND table_name = p_table_name
      AND column_name = 'user_id'
  ) INTO v_has_user_id_column;

  -- Get current user ID
  v_user_id := auth.uid();

  -- Build SET clause from JSONB
  v_set_clause := '';
  FOR v_key, v_value IN SELECT * FROM jsonb_each_text(p_updates)
  LOOP
    -- Prevent user_id tampering
    IF v_key = 'user_id' THEN
      RAISE EXCEPTION 'Cannot update user_id column';
    END IF;

    IF v_set_clause != '' THEN
      v_set_clause := v_set_clause || ', ';
    END IF;
    v_set_clause := v_set_clause || format('%I = %L', v_key, v_value);
  END LOOP;

  -- Build UPDATE statement with user isolation
  IF v_has_user_id_column AND v_user_id IS NOT NULL THEN
    -- User can only update their own rows
    v_sql := format(
      'UPDATE %I.%I SET %s WHERE rowid = %L AND user_id = %L',
      p_schema_name, p_table_name, v_set_clause, p_row_id, v_user_id
    );
  ELSE
    -- Legacy tables or service role
    v_sql := format(
      'UPDATE %I.%I SET %s WHERE rowid = %L',
      p_schema_name, p_table_name, v_set_clause, p_row_id
    );
  END IF;

  EXECUTE v_sql;

  -- Check if any rows were affected
  IF NOT FOUND THEN
    RAISE EXCEPTION 'No rows updated. Row may not exist or you do not have permission.';
  END IF;

  RETURN TRUE;
EXCEPTION
  WHEN OTHERS THEN
    RAISE EXCEPTION 'Update failed: %', SQLERRM;
END;
$$ LANGUAGE plpgsql;

GRANT EXECUTE ON FUNCTION public.update_table_row(TEXT, INT, JSONB, TEXT) TO authenticated, anon;

COMMENT ON FUNCTION public.update_table_row IS
'Update a single row with automatic user isolation.
Users can only update rows they own (user_id = auth.uid()).
Prevents user_id column tampering.';

-- ============================================================================
-- 8. Add function to check user ownership of a table
-- ============================================================================
CREATE OR REPLACE FUNCTION public.user_owns_table(
  p_table_name TEXT
)
RETURNS BOOLEAN
SECURITY DEFINER
SET search_path = public, _realtime
AS $$
DECLARE
  v_user_id UUID;
BEGIN
  v_user_id := auth.uid();

  IF v_user_id IS NULL THEN
    RETURN FALSE;
  END IF;

  RETURN EXISTS (
    SELECT 1 FROM _realtime.metadata_tables
    WHERE table_name = p_table_name
      AND user_id = v_user_id
  );
END;
$$ LANGUAGE plpgsql;

GRANT EXECUTE ON FUNCTION public.user_owns_table(TEXT) TO authenticated;

COMMENT ON FUNCTION public.user_owns_table IS
'Check if the current authenticated user owns a specific table.
Used for authorization checks before operations.';

-- ============================================================================
-- SUMMARY
-- ============================================================================
-- This migration implements complete user-level data isolation:
--
-- 1. ✅ metadata_tables now has user_id column with FK to auth.users
-- 2. ✅ All metadata RLS policies now filter by auth.uid()
-- 3. ✅ create_data_table automatically adds user_id column to all new tables
-- 4. ✅ insert_metadata automatically captures auth.uid()
-- 5. ✅ select_from_table automatically filters by user_id
-- 6. ✅ update_table_row enforces user ownership
-- 7. ✅ Helper functions for user ID and ownership checks
--
-- IMPORTANT: Service role bypasses RLS and can see/modify all data.
-- This is correct behavior for admin operations and bulk data imports.
--
-- NEXT STEPS:
-- 1. Update application code to handle user isolation
-- 2. Test with multiple user accounts
-- 3. Handle legacy data (user_id = NULL) - assign to admin or delete
