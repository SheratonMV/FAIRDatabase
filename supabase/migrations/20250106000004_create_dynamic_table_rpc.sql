-- RPC function to create data tables dynamically
-- This replaces pg_create_data_table from Python code

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
