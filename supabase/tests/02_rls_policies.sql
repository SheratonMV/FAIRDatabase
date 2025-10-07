-- ============================================================================
-- Row Level Security (RLS) Policy Tests
-- ============================================================================
-- Tests RLS policies for metadata_tables and dynamic data tables
-- Uses pgTAP: https://pgtap.org/documentation.html#PolicyTesting

BEGIN;

-- Load pgTAP extension
SELECT plan(9);

-- ============================================================================
-- TEST 1: RLS ENABLED ON METADATA_TABLES
-- ============================================================================

-- Verify RLS is enabled (also tested in schema tests, but critical for security)
-- Using direct query since row_security_is may not be available in all pgTAP versions
SELECT is(
  (SELECT relrowsecurity FROM pg_class WHERE oid = '_realtime.metadata_tables'::regclass),
  true,
  'RLS must be enabled on metadata_tables for security'
);

-- ============================================================================
-- TEST 2: METADATA_TABLES POLICIES EXIST
-- ============================================================================

-- Test that required policies exist
SELECT policies_are('_realtime', 'metadata_tables',
  ARRAY['authenticated_users_view_metadata', 'service_role_full_metadata_access'],
  'metadata_tables should have exactly two RLS policies');

-- ============================================================================
-- TEST 3: AUTHENTICATED_USERS_VIEW_METADATA POLICY
-- ============================================================================

-- Test policy exists and is for SELECT operations
SELECT policy_cmd_is('_realtime', 'metadata_tables', 'authenticated_users_view_metadata', 'SELECT',
  'authenticated_users_view_metadata policy should be for SELECT operations');

-- Test policy applies to authenticated role
SELECT policy_roles_are('_realtime', 'metadata_tables', 'authenticated_users_view_metadata',
  ARRAY['authenticated'],
  'authenticated_users_view_metadata should apply to authenticated role');

-- ============================================================================
-- TEST 4: SERVICE_ROLE_FULL_METADATA_ACCESS POLICY
-- ============================================================================

-- Test policy exists and is for ALL operations
SELECT policy_cmd_is('_realtime', 'metadata_tables', 'service_role_full_metadata_access', 'ALL',
  'service_role_full_metadata_access policy should be for ALL operations');

-- Test policy applies to service_role
SELECT policy_roles_are('_realtime', 'metadata_tables', 'service_role_full_metadata_access',
  ARRAY['service_role'],
  'service_role_full_metadata_access should apply to service_role');

-- ============================================================================
-- TEST 5: PERMISSION VERIFICATION
-- ============================================================================

-- Test authenticated role has SELECT permission (via RLS policy)
-- Note: authenticated also has REFERENCES, TRIGGER, TRUNCATE from initial GRANT ALL
-- Only INSERT, UPDATE, DELETE were explicitly revoked in RLS migration
SELECT table_privs_are('_realtime', 'metadata_tables', 'authenticated',
  ARRAY['SELECT', 'REFERENCES', 'TRIGGER', 'TRUNCATE'],
  'authenticated role should have SELECT and administrative permissions on metadata_tables');

-- Test anon role has NO permissions (revoked for security)
SELECT table_privs_are('_realtime', 'metadata_tables', 'anon', ARRAY[]::text[],
  'anon role should have NO permissions on metadata_tables');

-- Test service_role has full permissions
SELECT table_privs_are('_realtime', 'metadata_tables', 'service_role',
  ARRAY['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE', 'REFERENCES', 'TRIGGER'],
  'service_role should have full permissions on metadata_tables');

-- Finish tests
SELECT * FROM finish();

ROLLBACK;
