-- ============================================================================
-- FAIRDatabase Initial Schema Setup
-- ============================================================================
-- Creates the _realtime schema, metadata tracking table, and base permissions
-- Consolidates: create_realtime_schema, create_metadata_tables, grant_realtime_permissions

-- ============================================================================
-- STEP 1: CREATE _REALTIME SCHEMA
-- ============================================================================

-- Create custom schema for realtime data
CREATE SCHEMA IF NOT EXISTS _realtime;

-- Set search path to include _realtime schema
-- Note: This affects the database globally, allowing easy access to _realtime tables
ALTER DATABASE postgres SET search_path TO public, _realtime;

-- ============================================================================
-- STEP 2: CREATE METADATA TABLES
-- ============================================================================

-- Metadata tracking table for uploaded data files
-- Tracks information about chunked data tables
CREATE TABLE IF NOT EXISTS _realtime.metadata_tables (
  id SERIAL PRIMARY KEY,
  table_name TEXT NOT NULL,
  main_table TEXT NOT NULL,
  description TEXT,
  origin TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Index on table_name for faster lookups
CREATE INDEX IF NOT EXISTS idx_metadata_table_name ON _realtime.metadata_tables(table_name);

-- Index on main_table for grouping related chunks
CREATE INDEX IF NOT EXISTS idx_metadata_main_table ON _realtime.metadata_tables(main_table);

-- ============================================================================
-- STEP 3: GRANT BASE PERMISSIONS
-- ============================================================================

-- Grant usage on schema
GRANT USAGE ON SCHEMA _realtime TO anon, authenticated, service_role;

-- Grant all privileges on all tables in the schema
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA _realtime TO anon, authenticated, service_role;

-- Grant all privileges on all sequences in the schema
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA _realtime TO anon, authenticated, service_role;

-- Grant privileges on future tables (for tables created later)
ALTER DEFAULT PRIVILEGES IN SCHEMA _realtime
GRANT ALL ON TABLES TO anon, authenticated, service_role;

-- Grant privileges on future sequences (for sequences created later)
ALTER DEFAULT PRIVILEGES IN SCHEMA _realtime
GRANT ALL ON SEQUENCES TO anon, authenticated, service_role;

-- ============================================================================
-- DOCUMENTATION
-- ============================================================================

-- Data tables are created dynamically in the application via psycopg2
-- because they have:
-- 1. Dynamic table names based on uploaded files
-- 2. Dynamic column names based on CSV headers
-- 3. Variable number of columns (chunked into groups of 1200)
--
-- Expected schema pattern for dynamic tables:
-- CREATE TABLE IF NOT EXISTS _realtime.{table_name} (
--   rowid SERIAL PRIMARY KEY,
--   {patient_col} TEXT NOT NULL,
--   {dynamic_columns...} TEXT
-- );
