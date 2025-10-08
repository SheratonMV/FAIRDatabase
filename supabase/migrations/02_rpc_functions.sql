-- ============================================================================
-- FAIRDatabase RPC Functions
-- ============================================================================
-- Secure database operations with user-level data isolation
-- All functions use SECURITY DEFINER with explicit search_path

-- ============================================================================
-- INFORMATION SCHEMA FUNCTIONS
-- ============================================================================

-- Search for tables containing a specific column (case-insensitive)
CREATE OR REPLACE FUNCTION public.search_tables_by_column(
  p_column_name TEXT,
  p_schema_name TEXT DEFAULT '_realtime'
)
RETURNS TABLE(table_name TEXT)
SECURITY DEFINER
SET search_path = public, _realtime
AS $$
  SELECT DISTINCT t.table_name::TEXT
  FROM information_schema.tables t
  JOIN information_schema.columns c
    ON t.table_name = c.table_name
    AND t.table_schema = c.table_schema
  WHERE c.column_name ILIKE '%' || p_column_name || '%'
    AND t.table_schema = p_schema_name
    AND t.table_type = 'BASE TABLE'
  ORDER BY 1;
$$ LANGUAGE sql;

-- Get column information for a table
CREATE OR REPLACE FUNCTION public.get_table_columns(
  p_table_name TEXT,
  p_schema_name TEXT DEFAULT '_realtime'
)
RETURNS TABLE(
  column_name TEXT,
  data_type TEXT,
  is_nullable TEXT
)
SECURITY DEFINER
SET search_path = public, _realtime
AS $$
  SELECT
    column_name::TEXT,
    data_type::TEXT,
    is_nullable::TEXT
  FROM information_schema.columns
  WHERE table_name = p_table_name
    AND table_schema = p_schema_name
  ORDER BY ordinal_position;
$$ LANGUAGE sql;

-- Check if table exists
CREATE OR REPLACE FUNCTION public.table_exists(
  p_table_name TEXT,
  p_schema_name TEXT DEFAULT '_realtime'
)
RETURNS BOOLEAN
SECURITY DEFINER
SET search_path = public, _realtime
AS $$
  SELECT EXISTS (
    SELECT 1
    FROM information_schema.tables
    WHERE table_name = p_table_name
      AND table_schema = p_schema_name
  );
$$ LANGUAGE sql;

-- Get all tables in schema
CREATE OR REPLACE FUNCTION public.get_all_tables(
  p_schema_name TEXT DEFAULT '_realtime'
)
RETURNS TABLE(table_name TEXT)
SECURITY DEFINER
SET search_path = public, _realtime
AS $$
  SELECT table_name::TEXT
  FROM information_schema.tables
  WHERE table_schema = p_schema_name
    AND table_type = 'BASE TABLE'
  ORDER BY table_name;
$$ LANGUAGE sql;

-- ============================================================================
-- DATA QUERY FUNCTIONS WITH USER ISOLATION
-- ============================================================================

-- Select from dynamic table with automatic user isolation
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

  -- If table has user_id and user is authenticated, filter by user_id
  IF v_has_user_id_column AND v_user_id IS NOT NULL THEN
    RETURN QUERY EXECUTE format(
      'SELECT row_to_json(t)::JSONB FROM %I.%I t WHERE user_id = %L LIMIT %s',
      p_schema_name, p_table_name, v_user_id, p_row_limit
    );
  ELSE
    -- Service role sees all data
    RETURN QUERY EXECUTE format(
      'SELECT row_to_json(t)::JSONB FROM %I.%I t LIMIT %s',
      p_schema_name, p_table_name, p_row_limit
    );
  END IF;
END;
$$ LANGUAGE plpgsql;

-- Update table row with automatic user isolation
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

  -- Build SET clause from JSONB (prevent user_id tampering)
  v_set_clause := '';
  FOR v_key, v_value IN SELECT * FROM jsonb_each_text(p_updates)
  LOOP
    IF v_key = 'user_id' THEN
      RAISE EXCEPTION 'Cannot update user_id column';
    END IF;

    IF v_set_clause != '' THEN
      v_set_clause := v_set_clause || ', ';
    END IF;
    v_set_clause := v_set_clause || format('%I = %L', v_key, v_value);
  END LOOP;

  -- Build UPDATE with user isolation
  IF v_has_user_id_column AND v_user_id IS NOT NULL THEN
    v_sql := format(
      'UPDATE %I.%I SET %s WHERE rowid = %L AND user_id = %L',
      p_schema_name, p_table_name, v_set_clause, p_row_id, v_user_id
    );
  ELSE
    -- Service role can update any row
    v_sql := format(
      'UPDATE %I.%I SET %s WHERE rowid = %L',
      p_schema_name, p_table_name, v_set_clause, p_row_id
    );
  END IF;

  EXECUTE v_sql;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'No rows updated. Row may not exist or you lack permission.';
  END IF;

  RETURN TRUE;
EXCEPTION
  WHEN OTHERS THEN
    RAISE EXCEPTION 'Update failed: %', SQLERRM;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- METADATA FUNCTIONS
-- ============================================================================

-- Insert metadata with automatic user_id capture
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
  -- Get current user ID
  v_user_id := auth.uid();

  -- Require authentication
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

-- ============================================================================
-- TABLE CREATION FUNCTION
-- ============================================================================

-- Create dynamic data table with full RLS configuration
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
  -- Validate schema
  IF p_schema_name NOT IN ('_realtime') THEN
    RAISE EXCEPTION 'Invalid schema: %. Only _realtime is allowed.', p_schema_name;
  END IF;

  v_full_table_name := format('%I.%I', p_schema_name, p_table_name);

  -- Build column definitions
  v_cols_def := '';
  FOREACH v_col IN ARRAY p_column_names
  LOOP
    IF v_cols_def != '' THEN
      v_cols_def := v_cols_def || ', ';
    END IF;
    v_cols_def := v_cols_def || format('%I TEXT', v_col);
  END LOOP;

  -- Create table with user_id column
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

  -- Create indexes
  EXECUTE format(
    'CREATE INDEX IF NOT EXISTS idx_%I_user_id ON %I.%I(user_id)',
    p_table_name, p_schema_name, p_table_name
  );

  EXECUTE format(
    'CREATE INDEX IF NOT EXISTS idx_%I_%I ON %I.%I(%I)',
    p_table_name, p_id_column, p_schema_name, p_table_name, p_id_column
  );

  -- Enable RLS
  EXECUTE format('ALTER TABLE %s ENABLE ROW LEVEL SECURITY', v_full_table_name);

  -- Drop existing policies (idempotency)
  EXECUTE format('DROP POLICY IF EXISTS "users_view_own_data" ON %s', v_full_table_name);
  EXECUTE format('DROP POLICY IF EXISTS "users_insert_own_data" ON %s', v_full_table_name);
  EXECUTE format('DROP POLICY IF EXISTS "service_role_full_data_access" ON %s', v_full_table_name);

  -- Create RLS policies
  EXECUTE format(
    'CREATE POLICY "users_view_own_data" ON %s FOR SELECT TO authenticated USING (auth.uid() = user_id)',
    v_full_table_name
  );

  EXECUTE format(
    'CREATE POLICY "users_insert_own_data" ON %s FOR INSERT TO authenticated WITH CHECK (auth.uid() = user_id)',
    v_full_table_name
  );

  EXECUTE format(
    'CREATE POLICY "service_role_full_data_access" ON %s FOR ALL TO service_role USING (true) WITH CHECK (true)',
    v_full_table_name
  );

  -- Revoke direct access from anon
  EXECUTE format('REVOKE ALL ON TABLE %s FROM anon', v_full_table_name);

  -- Grant permissions
  EXECUTE format('GRANT SELECT, INSERT ON TABLE %s TO authenticated', v_full_table_name);
  EXECUTE format('GRANT ALL ON TABLE %s TO service_role', v_full_table_name);
  EXECUTE format('GRANT USAGE, SELECT ON SEQUENCE %I.%I_rowid_seq TO service_role', p_schema_name, p_table_name);
  EXECUTE format('REVOKE ALL ON SEQUENCE %I.%I_rowid_seq FROM anon, authenticated', p_schema_name, p_table_name);

  -- Notify PostgREST to reload schema
  NOTIFY pgrst, 'reload schema';

  RETURN TRUE;

EXCEPTION WHEN OTHERS THEN
  RAISE EXCEPTION 'Failed to create table %: %', p_table_name, SQLERRM;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER
SET search_path = public, _realtime;

-- ============================================================================
-- HELPER FUNCTIONS
-- ============================================================================

-- Get current authenticated user ID
CREATE OR REPLACE FUNCTION public.get_current_user_id()
RETURNS UUID
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  RETURN auth.uid();
END;
$$ LANGUAGE plpgsql;

-- Check if user owns a table
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

-- ============================================================================
-- GRANT EXECUTE PERMISSIONS
-- ============================================================================

-- Information schema functions (authenticated users only)
GRANT EXECUTE ON FUNCTION public.search_tables_by_column(TEXT, TEXT) TO authenticated;
GRANT EXECUTE ON FUNCTION public.get_table_columns(TEXT, TEXT) TO authenticated;
GRANT EXECUTE ON FUNCTION public.table_exists(TEXT, TEXT) TO authenticated;
GRANT EXECUTE ON FUNCTION public.get_all_tables(TEXT) TO authenticated;

-- Data functions (authenticated users only)
GRANT EXECUTE ON FUNCTION public.select_from_table(TEXT, INT, TEXT) TO authenticated;
GRANT EXECUTE ON FUNCTION public.update_table_row(TEXT, INT, JSONB, TEXT) TO authenticated;
GRANT EXECUTE ON FUNCTION public.insert_metadata(TEXT, TEXT, TEXT, TEXT) TO authenticated;

-- Table creation (service role only - admin operation)
GRANT EXECUTE ON FUNCTION public.create_data_table(TEXT, TEXT, TEXT[], TEXT) TO service_role;

-- Helper functions (authenticated users only)
GRANT EXECUTE ON FUNCTION public.get_current_user_id() TO authenticated;
GRANT EXECUTE ON FUNCTION public.user_owns_table(TEXT) TO authenticated;

-- ============================================================================
-- COMMENTS
-- ============================================================================

COMMENT ON FUNCTION public.search_tables_by_column IS 'Search for tables containing a column matching the pattern (case-insensitive)';
COMMENT ON FUNCTION public.get_table_columns IS 'Get column information for a specific table';
COMMENT ON FUNCTION public.table_exists IS 'Check if a table exists in the schema';
COMMENT ON FUNCTION public.get_all_tables IS 'Get all tables in the specified schema';
COMMENT ON FUNCTION public.select_from_table IS 'Select rows from dynamic table with automatic user isolation';
COMMENT ON FUNCTION public.update_table_row IS 'Update a single row with automatic user isolation and user_id tamper protection';
COMMENT ON FUNCTION public.insert_metadata IS 'Insert metadata record with automatic user_id capture from auth.uid()';
COMMENT ON FUNCTION public.create_data_table IS 'Creates dynamic data table with full user-level RLS configuration';
COMMENT ON FUNCTION public.get_current_user_id IS 'Returns authenticated user UUID from auth.uid()';
COMMENT ON FUNCTION public.user_owns_table IS 'Check if current user owns a specific table';
