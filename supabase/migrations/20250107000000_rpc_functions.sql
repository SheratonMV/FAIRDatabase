-- ============================================================================
-- FAIRDatabase RPC Functions
-- ============================================================================
-- These functions provide secure access to _realtime schema from the public schema
-- All functions use SECURITY DEFINER with explicit search_path for safety

-- ============================================================================
-- INFORMATION SCHEMA FUNCTIONS
-- ============================================================================

-- Get tables containing specific column (supports pattern matching with ILIKE)
-- Used by: routes.py:175-184, routes.py:328-337, routes.py:395-410
CREATE OR REPLACE FUNCTION public.search_tables_by_column(
  search_column TEXT,
  schema_name TEXT DEFAULT '_realtime'
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
  WHERE c.column_name ILIKE '%' || search_column || '%'
    AND t.table_schema = schema_name
    AND t.table_type = 'BASE TABLE'
  ORDER BY 1;
$$ LANGUAGE sql;

-- Get column information for a table
-- Used by: routes.py:197-206, routes.py:508-517
CREATE OR REPLACE FUNCTION public.get_table_columns(
  p_table_name TEXT,
  schema_name TEXT DEFAULT '_realtime'
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
    AND table_schema = schema_name
  ORDER BY ordinal_position;
$$ LANGUAGE sql;

-- Check if table exists
-- Used by: routes.py:481-491
CREATE OR REPLACE FUNCTION public.table_exists(
  p_table_name TEXT,
  schema_name TEXT DEFAULT '_realtime'
)
RETURNS BOOLEAN
SECURITY DEFINER
SET search_path = public, _realtime
AS $$
  SELECT EXISTS (
    SELECT 1
    FROM information_schema.tables
    WHERE table_name = p_table_name
      AND table_schema = schema_name
  );
$$ LANGUAGE sql;

-- Get all tables in schema
-- Used by: routes.py:299-307, routes.py:340-347
CREATE OR REPLACE FUNCTION public.get_all_tables(
  schema_name TEXT DEFAULT '_realtime'
)
RETURNS TABLE(table_name TEXT)
SECURITY DEFINER
SET search_path = public, _realtime
AS $$
  SELECT table_name::TEXT
  FROM information_schema.tables
  WHERE table_schema = schema_name
    AND table_type = 'BASE TABLE'
  ORDER BY table_name;
$$ LANGUAGE sql;

-- ============================================================================
-- DYNAMIC TABLE FUNCTIONS
-- ============================================================================

-- Select from dynamic table (safe with validation)
-- Used by: routes.py:209-216, routes.py:519-525
CREATE OR REPLACE FUNCTION public.select_from_table(
  p_table_name TEXT,
  p_limit INT DEFAULT 100,
  schema_name TEXT DEFAULT '_realtime'
)
RETURNS TABLE(data JSONB)
SECURITY DEFINER
SET search_path = public, _realtime
AS $$
BEGIN
  -- Validate table exists (prevent SQL injection)
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.tables
    WHERE table_schema = schema_name AND table_name = p_table_name
  ) THEN
    RAISE EXCEPTION 'Table % does not exist in schema %', p_table_name, schema_name;
  END IF;

  -- Safe dynamic SQL using format with %I for identifiers
  RETURN QUERY EXECUTE format(
    'SELECT row_to_json(t)::JSONB FROM %I.%I t LIMIT %s',
    schema_name, p_table_name, p_limit
  );
END;
$$ LANGUAGE plpgsql;

-- Update dynamic table row
-- Used by: routes.py:418-425
CREATE OR REPLACE FUNCTION public.update_table_row(
  p_table_name TEXT,
  p_row_id INT,
  p_updates JSONB,
  schema_name TEXT DEFAULT '_realtime'
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
BEGIN
  -- Validate table exists
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.tables
    WHERE table_schema = schema_name AND table_name = p_table_name
  ) THEN
    RAISE EXCEPTION 'Table % does not exist in schema %', p_table_name, schema_name;
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
    'UPDATE %I.%I SET %s WHERE rowid = %L',
    schema_name, p_table_name, v_set_clause, p_row_id
  );

  EXECUTE v_sql;
  RETURN TRUE;
EXCEPTION
  WHEN OTHERS THEN
    RAISE EXCEPTION 'Update failed: %', SQLERRM;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- METADATA FUNCTIONS
-- ============================================================================

-- Insert into metadata table
-- Used by: helpers.py:120-127
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
BEGIN
  INSERT INTO _realtime.metadata_tables (table_name, main_table, description, origin)
  VALUES (p_table_name, p_main_table, p_description, p_origin)
  RETURNING id INTO v_id;

  RETURN v_id;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- DYNAMIC TABLE CREATION (UNUSED - psycopg2 handles this)
-- ============================================================================

-- RPC function to create data tables dynamically
-- Note: This function exists for completeness but is NOT used in production
-- The application uses psycopg2 for table creation to avoid PostgREST schema cache issues
CREATE OR REPLACE FUNCTION public.create_data_table(
  schema_name TEXT,
  p_table_name TEXT,
  p_columns TEXT[],
  p_patient_col TEXT
)
RETURNS BOOLEAN AS $$
DECLARE
  v_cols_def TEXT;
  v_sql TEXT;
  v_col TEXT;
BEGIN
  -- Validate schema exists
  IF schema_name NOT IN ('realtime') THEN
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
    'CREATE TABLE IF NOT EXISTS _%s.%I (
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

  -- Grant permissions on the new table
  EXECUTE format('GRANT ALL ON TABLE _%s.%I TO anon, authenticated, service_role', schema_name, p_table_name);
  EXECUTE format('GRANT USAGE, SELECT ON SEQUENCE _%s.%I_rowid_seq TO anon, authenticated, service_role', schema_name, p_table_name);

  RETURN TRUE;
EXCEPTION WHEN OTHERS THEN
  RAISE EXCEPTION 'Failed to create table: %', SQLERRM;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- ============================================================================
-- GRANT EXECUTE PERMISSIONS
-- ============================================================================

-- Grant execute permissions to authenticated users
-- This allows the Supabase client to call these functions
GRANT EXECUTE ON FUNCTION public.search_tables_by_column(TEXT, TEXT) TO authenticated, anon;
GRANT EXECUTE ON FUNCTION public.get_table_columns(TEXT, TEXT) TO authenticated, anon;
GRANT EXECUTE ON FUNCTION public.table_exists(TEXT, TEXT) TO authenticated, anon;
GRANT EXECUTE ON FUNCTION public.get_all_tables(TEXT) TO authenticated, anon;
GRANT EXECUTE ON FUNCTION public.select_from_table(TEXT, INT, TEXT) TO authenticated, anon;
GRANT EXECUTE ON FUNCTION public.update_table_row(TEXT, INT, JSONB, TEXT) TO authenticated, anon;
GRANT EXECUTE ON FUNCTION public.insert_metadata(TEXT, TEXT, TEXT, TEXT) TO authenticated, anon;
