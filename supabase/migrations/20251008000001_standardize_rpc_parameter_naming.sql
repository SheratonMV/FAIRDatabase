-- ============================================================================
-- Standardize RPC Parameter Naming
-- ============================================================================
-- This migration standardizes all RPC function parameter names to use the
-- `p_` prefix consistently across all functions.
--
-- Issue #4.2: RPC Parameter Naming Inconsistency
--
-- Changes:
-- 1. search_tables_by_column: search_column → p_column_name
-- 2. select_from_table: p_limit → p_row_limit (more descriptive)
-- 3. All functions: schema_name → p_schema_name (consistency)
--
-- Note: This is a breaking change. Application code must be updated to use
-- the new parameter names.

-- ============================================================================
-- 1. search_tables_by_column
-- ============================================================================
DROP FUNCTION IF EXISTS public.search_tables_by_column(TEXT, TEXT);

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

-- ============================================================================
-- 2. get_table_columns
-- ============================================================================
DROP FUNCTION IF EXISTS public.get_table_columns(TEXT, TEXT);

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

-- ============================================================================
-- 3. table_exists
-- ============================================================================
DROP FUNCTION IF EXISTS public.table_exists(TEXT, TEXT);

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

-- ============================================================================
-- 4. get_all_tables
-- ============================================================================
DROP FUNCTION IF EXISTS public.get_all_tables(TEXT);

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
-- 5. select_from_table
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
BEGIN
  -- Validate table exists (prevent SQL injection)
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.tables
    WHERE table_schema = p_schema_name AND table_name = p_table_name
  ) THEN
    RAISE EXCEPTION 'Table % does not exist in schema %', p_table_name, p_schema_name;
  END IF;

  -- Safe dynamic SQL using format with %I for identifiers
  RETURN QUERY EXECUTE format(
    'SELECT row_to_json(t)::JSONB FROM %I.%I t LIMIT %s',
    p_schema_name, p_table_name, p_row_limit
  );
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- 6. update_table_row
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
BEGIN
  -- Validate table exists
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.tables
    WHERE table_schema = p_schema_name AND table_name = p_table_name
  ) THEN
    RAISE EXCEPTION 'Table % does not exist in schema %', p_table_name, p_schema_name;
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
    p_schema_name, p_table_name, v_set_clause, p_row_id
  );

  EXECUTE v_sql;
  RETURN TRUE;
EXCEPTION
  WHEN OTHERS THEN
    RAISE EXCEPTION 'Update failed: %', SQLERRM;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- 7. insert_metadata
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
BEGIN
  INSERT INTO _realtime.metadata_tables (table_name, main_table, description, origin)
  VALUES (p_table_name, p_main_table, p_description, p_origin)
  RETURNING id INTO v_id;

  RETURN v_id;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- GRANT EXECUTE PERMISSIONS
-- ============================================================================
GRANT EXECUTE ON FUNCTION public.search_tables_by_column(TEXT, TEXT) TO authenticated, anon;
GRANT EXECUTE ON FUNCTION public.get_table_columns(TEXT, TEXT) TO authenticated, anon;
GRANT EXECUTE ON FUNCTION public.table_exists(TEXT, TEXT) TO authenticated, anon;
GRANT EXECUTE ON FUNCTION public.get_all_tables(TEXT) TO authenticated, anon;
GRANT EXECUTE ON FUNCTION public.select_from_table(TEXT, INT, TEXT) TO authenticated, anon;
GRANT EXECUTE ON FUNCTION public.update_table_row(TEXT, INT, JSONB, TEXT) TO authenticated, anon;
GRANT EXECUTE ON FUNCTION public.insert_metadata(TEXT, TEXT, TEXT, TEXT) TO authenticated, anon;

-- ============================================================================
-- COMMENTS
-- ============================================================================
COMMENT ON FUNCTION public.search_tables_by_column IS 'Search for tables containing a column matching the pattern (case-insensitive). Parameters standardized with p_ prefix.';
COMMENT ON FUNCTION public.get_table_columns IS 'Get column information for a specific table. Parameters standardized with p_ prefix.';
COMMENT ON FUNCTION public.table_exists IS 'Check if a table exists in the schema. Parameters standardized with p_ prefix.';
COMMENT ON FUNCTION public.get_all_tables IS 'Get all tables in the specified schema. Parameters standardized with p_ prefix.';
COMMENT ON FUNCTION public.select_from_table IS 'Select rows from a dynamic table with row limit. Parameters standardized with p_ prefix.';
COMMENT ON FUNCTION public.update_table_row IS 'Update a single row in a dynamic table by rowid. Parameters standardized with p_ prefix.';
COMMENT ON FUNCTION public.insert_metadata IS 'Insert metadata record for a data table. Parameters standardized with p_ prefix.';
