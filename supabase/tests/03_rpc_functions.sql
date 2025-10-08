-- ============================================================================
-- RPC Function Tests
-- ============================================================================
-- Tests all RPC functions for existence, signatures, security, and basic functionality
-- Uses pgTAP: https://pgtap.org/documentation.html#FunctionTesting

BEGIN;

-- Load pgTAP extension
SELECT plan(35);

-- ============================================================================
-- TEST 1: INFORMATION SCHEMA FUNCTIONS EXIST
-- ============================================================================

-- Test search_tables_by_column exists with correct signature
SELECT has_function('public', 'search_tables_by_column', ARRAY['text', 'text'],
  'search_tables_by_column(text, text) function should exist');

SELECT function_returns('public', 'search_tables_by_column', ARRAY['text', 'text'], 'setof text',
  'search_tables_by_column should return setof text');

-- Test get_table_columns exists with correct signature
SELECT has_function('public', 'get_table_columns', ARRAY['text', 'text'],
  'get_table_columns(text, text) function should exist');

SELECT function_returns('public', 'get_table_columns', ARRAY['text', 'text'], 'setof record',
  'get_table_columns should return setof record');

-- Test table_exists exists with correct signature
SELECT has_function('public', 'table_exists', ARRAY['text', 'text'],
  'table_exists(text, text) function should exist');

SELECT function_returns('public', 'table_exists', ARRAY['text', 'text'], 'boolean',
  'table_exists should return a boolean');

-- Test get_all_tables exists with correct signature
SELECT has_function('public', 'get_all_tables', ARRAY['text'],
  'get_all_tables(text) function should exist');

SELECT function_returns('public', 'get_all_tables', ARRAY['text'], 'setof text',
  'get_all_tables should return setof text');

-- ============================================================================
-- TEST 2: DYNAMIC TABLE FUNCTIONS EXIST
-- ============================================================================

-- Test select_from_table exists with correct signature
SELECT has_function('public', 'select_from_table', ARRAY['text', 'integer', 'text'],
  'select_from_table(text, integer, text) function should exist');

SELECT function_returns('public', 'select_from_table', ARRAY['text', 'integer', 'text'], 'setof jsonb',
  'select_from_table should return setof jsonb');

-- Test update_table_row exists with correct signature
SELECT has_function('public', 'update_table_row', ARRAY['text', 'integer', 'jsonb', 'text'],
  'update_table_row(text, integer, jsonb, text) function should exist');

SELECT function_returns('public', 'update_table_row', ARRAY['text', 'integer', 'jsonb', 'text'], 'boolean',
  'update_table_row should return a boolean');

-- ============================================================================
-- TEST 3: METADATA FUNCTIONS EXIST
-- ============================================================================

-- Test insert_metadata exists with correct signature
SELECT has_function('public', 'insert_metadata', ARRAY['text', 'text', 'text', 'text'],
  'insert_metadata(text, text, text, text) function should exist');

SELECT function_returns('public', 'insert_metadata', ARRAY['text', 'text', 'text', 'text'], 'integer',
  'insert_metadata should return an integer (the new id)');

-- ============================================================================
-- TEST 4: TABLE CREATION FUNCTIONS EXIST
-- ============================================================================

-- Test create_data_table exists with correct signature
SELECT has_function('public', 'create_data_table', ARRAY['text', 'text', 'text[]', 'text'],
  'create_data_table(text, text, text[], text) function should exist');

SELECT function_returns('public', 'create_data_table', ARRAY['text', 'text', 'text[]', 'text'], 'boolean',
  'create_data_table should return a boolean');

-- ============================================================================
-- TEST 5: HELPER FUNCTIONS EXIST
-- ============================================================================

-- Test get_current_user_id exists
SELECT has_function('public', 'get_current_user_id', ARRAY[]::text[],
  'get_current_user_id() function should exist');

SELECT function_returns('public', 'get_current_user_id', ARRAY[]::text[], 'uuid',
  'get_current_user_id should return uuid');

-- Test user_owns_table exists
SELECT has_function('public', 'user_owns_table', ARRAY['text'],
  'user_owns_table(text) function should exist');

SELECT function_returns('public', 'user_owns_table', ARRAY['text'], 'boolean',
  'user_owns_table should return a boolean');

-- ============================================================================
-- TEST 6: FUNCTION PERMISSIONS
-- ============================================================================

-- NOTE: Only authenticated users have access to RPC functions.
-- Anonymous users have no EXECUTE permissions for security.

-- Verify authenticated users have EXECUTE on information schema functions
SELECT function_privs_are('public', 'search_tables_by_column', ARRAY['text', 'text'], 'authenticated', ARRAY['EXECUTE'],
  'authenticated should have EXECUTE permission on search_tables_by_column');

SELECT function_privs_are('public', 'get_table_columns', ARRAY['text', 'text'], 'authenticated', ARRAY['EXECUTE'],
  'authenticated should have EXECUTE permission on get_table_columns');

SELECT function_privs_are('public', 'table_exists', ARRAY['text', 'text'], 'authenticated', ARRAY['EXECUTE'],
  'authenticated should have EXECUTE permission on table_exists');

SELECT function_privs_are('public', 'get_all_tables', ARRAY['text'], 'authenticated', ARRAY['EXECUTE'],
  'authenticated should have EXECUTE permission on get_all_tables');

-- Verify authenticated users have EXECUTE on data functions
SELECT function_privs_are('public', 'select_from_table', ARRAY['text', 'integer', 'text'], 'authenticated', ARRAY['EXECUTE'],
  'authenticated should have EXECUTE permission on select_from_table');

SELECT function_privs_are('public', 'update_table_row', ARRAY['text', 'integer', 'jsonb', 'text'], 'authenticated', ARRAY['EXECUTE'],
  'authenticated should have EXECUTE permission on update_table_row');

SELECT function_privs_are('public', 'insert_metadata', ARRAY['text', 'text', 'text', 'text'], 'authenticated', ARRAY['EXECUTE'],
  'authenticated should have EXECUTE permission on insert_metadata');

-- service_role should have EXECUTE on create_data_table (admin operation)
SELECT function_privs_are('public', 'create_data_table', ARRAY['text', 'text', 'text[]', 'text'], 'service_role', ARRAY['EXECUTE'],
  'service_role should have EXECUTE permission on create_data_table');

-- authenticated users should have EXECUTE on helper functions
SELECT function_privs_are('public', 'get_current_user_id', ARRAY[]::text[], 'authenticated', ARRAY['EXECUTE'],
  'authenticated should have EXECUTE permission on get_current_user_id');

SELECT function_privs_are('public', 'user_owns_table', ARRAY['text'], 'authenticated', ARRAY['EXECUTE'],
  'authenticated should have EXECUTE permission on user_owns_table');

-- ============================================================================
-- TEST 7: FUNCTIONAL TESTS WITH TEST DATA
-- ============================================================================

-- Test get_all_tables returns metadata_tables
SELECT is(
  (SELECT COUNT(*) > 0 FROM public.get_all_tables('_realtime') WHERE table_name = 'metadata_tables'),
  true,
  'get_all_tables should return metadata_tables table'
);

-- Test table_exists works correctly
SELECT is(
  public.table_exists('metadata_tables', '_realtime'),
  true,
  'table_exists should return true for metadata_tables'
);

SELECT is(
  public.table_exists('nonexistent_table', '_realtime'),
  false,
  'table_exists should return false for nonexistent tables'
);

-- Test get_table_columns returns expected columns for metadata_tables
SELECT is(
  (SELECT COUNT(*) FROM public.get_table_columns('metadata_tables', '_realtime')
   WHERE column_name IN ('id', 'table_name', 'main_table', 'description', 'origin', 'created_at', 'user_id')),
  7::bigint,
  'get_table_columns should return all 7 columns of metadata_tables'
);

-- Test insert_metadata requires authentication
-- Note: pgTAP tests run without authenticated user context
SELECT throws_ok(
  'SELECT public.insert_metadata(''test_table'', ''test_main'', ''test description'', ''test origin'')',
  'P0001',
  'User must be authenticated to insert metadata',
  'insert_metadata should require authentication'
);

-- Finish tests
SELECT * FROM finish();

ROLLBACK;
