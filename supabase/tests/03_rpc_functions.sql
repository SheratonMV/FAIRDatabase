-- ============================================================================
-- RPC Function Tests
-- ============================================================================
-- Tests all RPC functions for existence, signatures, security, and basic functionality
-- Uses pgTAP: https://pgtap.org/documentation.html#FunctionTesting

BEGIN;

-- Load pgTAP extension
SELECT plan(33);

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
SELECT has_function('public', 'create_data_table', ARRAY['text', 'text[]', 'text', 'text'],
  'create_data_table(text, text[], text, text) function should exist');

SELECT function_returns('public', 'create_data_table', ARRAY['text', 'text[]', 'text', 'text'], 'boolean',
  'create_data_table should return a boolean');

-- Test enable_table_rls exists with correct signature
SELECT has_function('public', 'enable_table_rls', ARRAY['text', 'text'],
  'enable_table_rls(text, text) function should exist');

SELECT function_returns('public', 'enable_table_rls', ARRAY['text', 'text'], 'boolean',
  'enable_table_rls should return a boolean');

-- ============================================================================
-- TEST 5: FUNCTION PERMISSIONS
-- ============================================================================

-- NOTE: The RLS migration (20251007000000_enable_rls.sql) attempts to revoke
-- anon access from functions, but PostgreSQL grants are cumulative.
-- Since the initial RPC migration granted EXECUTE to anon, these grants persist.
-- These tests document the CURRENT state for security auditing.

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

-- service_role should have EXECUTE on create_data_table
SELECT function_privs_are('public', 'create_data_table', ARRAY['text', 'text[]', 'text', 'text'], 'service_role', ARRAY['EXECUTE'],
  'service_role should have EXECUTE permission on create_data_table');

-- service_role should have EXECUTE on enable_table_rls
SELECT function_privs_are('public', 'enable_table_rls', ARRAY['text', 'text'], 'service_role', ARRAY['EXECUTE'],
  'service_role should have EXECUTE permission on enable_table_rls');

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
   WHERE column_name IN ('id', 'table_name', 'main_table', 'description', 'origin', 'created_at')),
  6::bigint,
  'get_table_columns should return all 6 columns of metadata_tables'
);

-- Test insert_metadata inserts data and returns id
SELECT is(
  (SELECT public.insert_metadata('test_table', 'test_main', 'test description', 'test origin') > 0),
  true,
  'insert_metadata should insert data and return positive id'
);

-- Verify the inserted data exists
SELECT is(
  (SELECT COUNT(*) FROM _realtime.metadata_tables WHERE table_name = 'test_table'),
  1::bigint,
  'Inserted metadata should be retrievable from metadata_tables'
);

-- Finish tests
SELECT * FROM finish();

ROLLBACK;
