-- ============================================================================
-- FAIRDatabase Schema and Row Level Security
-- ============================================================================
-- Creates _realtime schema, metadata_tables with user isolation, and RLS policies

-- ============================================================================
-- STEP 1: CREATE _REALTIME SCHEMA
-- ============================================================================

CREATE SCHEMA IF NOT EXISTS _realtime;

-- Set search path to include _realtime schema
ALTER DATABASE postgres SET search_path TO public, _realtime;

-- ============================================================================
-- STEP 2: CREATE METADATA_TABLES WITH USER_ID
-- ============================================================================

-- Metadata tracking table for uploaded data files with user-level isolation
CREATE TABLE IF NOT EXISTS _realtime.metadata_tables (
  id SERIAL PRIMARY KEY,
  table_name TEXT NOT NULL,
  main_table TEXT NOT NULL,
  description TEXT,
  origin TEXT,
  user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_metadata_table_name ON _realtime.metadata_tables(table_name);
CREATE INDEX IF NOT EXISTS idx_metadata_main_table ON _realtime.metadata_tables(main_table);
CREATE INDEX IF NOT EXISTS idx_metadata_user_id ON _realtime.metadata_tables(user_id);

COMMENT ON COLUMN _realtime.metadata_tables.user_id IS 'User who uploaded this dataset. FK to auth.users(id).';

-- ============================================================================
-- STEP 3: ENABLE ROW LEVEL SECURITY
-- ============================================================================

ALTER TABLE _realtime.metadata_tables ENABLE ROW LEVEL SECURITY;

-- ============================================================================
-- STEP 4: CREATE RLS POLICIES FOR USER-LEVEL ISOLATION
-- ============================================================================

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

-- Policy: Service role has full access (admin operations)
CREATE POLICY "service_role_full_metadata_access"
ON _realtime.metadata_tables
FOR ALL
TO service_role
USING (true)
WITH CHECK (true);

-- ============================================================================
-- STEP 5: GRANT PERMISSIONS
-- ============================================================================

-- Grant schema usage
GRANT USAGE ON SCHEMA _realtime TO authenticated, service_role;

-- Revoke all from anon (no anonymous access to research data)
REVOKE ALL ON TABLE _realtime.metadata_tables FROM anon;

-- Grant SELECT to authenticated (RLS policies enforce user isolation)
GRANT SELECT ON TABLE _realtime.metadata_tables TO authenticated;

-- Grant INSERT to authenticated (RLS enforces user_id match)
GRANT INSERT ON TABLE _realtime.metadata_tables TO authenticated;

-- Grant full access to service_role
GRANT ALL ON TABLE _realtime.metadata_tables TO service_role;
GRANT ALL ON SEQUENCE _realtime.metadata_tables_id_seq TO service_role;

-- Grant sequence usage to authenticated for inserts
GRANT USAGE ON SEQUENCE _realtime.metadata_tables_id_seq TO authenticated;

-- Set default privileges for future tables in _realtime schema
ALTER DEFAULT PRIVILEGES IN SCHEMA _realtime
GRANT SELECT ON TABLES TO authenticated;

ALTER DEFAULT PRIVILEGES IN SCHEMA _realtime
GRANT ALL ON TABLES TO service_role;

ALTER DEFAULT PRIVILEGES IN SCHEMA _realtime
GRANT ALL ON SEQUENCES TO service_role;

-- ============================================================================
-- DOCUMENTATION
-- ============================================================================

COMMENT ON SCHEMA _realtime IS 'Schema for dynamically created data tables with user-level isolation';
COMMENT ON TABLE _realtime.metadata_tables IS 'Tracks uploaded datasets with user ownership for RLS isolation';
COMMENT ON POLICY "users_view_own_metadata" ON _realtime.metadata_tables IS 'Users can only view their own uploaded datasets';
COMMENT ON POLICY "service_role_full_metadata_access" ON _realtime.metadata_tables IS 'Backend (service role) has full access for admin operations';
