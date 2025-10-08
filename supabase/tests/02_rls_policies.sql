-- ============================================================================
-- Row Level Security (RLS) Policy Tests
-- ============================================================================
-- Tests RLS policies for metadata_tables and dynamic data tables
-- Uses pgTAP: https://pgtap.org/documentation.html#PolicyTesting

BEGIN;

-- Load pgTAP extension
SELECT plan(13);

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

-- Test that required policies exist (user-level isolation)
SELECT policies_are('_realtime', 'metadata_tables',
  ARRAY[
    'users_view_own_metadata',
    'users_insert_own_metadata',
    'users_update_own_metadata',
    'users_delete_own_metadata',
    'service_role_full_metadata_access'
  ],
  'metadata_tables should have 5 RLS policies for user-level isolation');

-- ============================================================================
-- TEST 3: USER-LEVEL ISOLATION POLICIES
-- ============================================================================

-- Test SELECT policy
SELECT policy_cmd_is('_realtime', 'metadata_tables', 'users_view_own_metadata', 'SELECT',
  'users_view_own_metadata policy should be for SELECT operations');

SELECT policy_roles_are('_realtime', 'metadata_tables', 'users_view_own_metadata',
  ARRAY['authenticated'],
  'users_view_own_metadata should apply to authenticated role');

-- Test INSERT policy
SELECT policy_cmd_is('_realtime', 'metadata_tables', 'users_insert_own_metadata', 'INSERT',
  'users_insert_own_metadata policy should be for INSERT operations');

SELECT policy_roles_are('_realtime', 'metadata_tables', 'users_insert_own_metadata',
  ARRAY['authenticated'],
  'users_insert_own_metadata should apply to authenticated role');

-- Test UPDATE policy
SELECT policy_cmd_is('_realtime', 'metadata_tables', 'users_update_own_metadata', 'UPDATE',
  'users_update_own_metadata policy should be for UPDATE operations');

-- Test DELETE policy
SELECT policy_cmd_is('_realtime', 'metadata_tables', 'users_delete_own_metadata', 'DELETE',
  'users_delete_own_metadata policy should be for DELETE operations');

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

-- Test authenticated role has SELECT and INSERT permissions (enforced by RLS)
SELECT table_privs_are('_realtime', 'metadata_tables', 'authenticated',
  ARRAY['SELECT', 'INSERT'],
  'authenticated role should have SELECT and INSERT (RLS enforces user isolation)');

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
