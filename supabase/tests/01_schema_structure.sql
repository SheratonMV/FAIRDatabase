-- ============================================================================
-- Schema Structure Tests
-- ============================================================================
-- Tests database schema setup, tables, columns, and indexes
-- Uses pgTAP: https://pgtap.org/documentation.html

BEGIN;

-- Load pgTAP extension
SELECT plan(19);

-- ============================================================================
-- TEST 1: SCHEMA EXISTENCE
-- ============================================================================

-- Test that _realtime schema exists
SELECT has_schema('_realtime',
  '_realtime schema should exist for storing application data');

-- ============================================================================
-- TEST 2: METADATA_TABLES TABLE STRUCTURE
-- ============================================================================

-- Test that metadata_tables table exists in _realtime schema
SELECT has_table('_realtime', 'metadata_tables',
  'metadata_tables table should exist in _realtime schema');

-- Test required columns exist with correct types
SELECT has_column('_realtime', 'metadata_tables', 'id',
  'metadata_tables should have id column');

SELECT has_column('_realtime', 'metadata_tables', 'table_name',
  'metadata_tables should have table_name column');

SELECT has_column('_realtime', 'metadata_tables', 'main_table',
  'metadata_tables should have main_table column');

SELECT has_column('_realtime', 'metadata_tables', 'description',
  'metadata_tables should have description column');

SELECT has_column('_realtime', 'metadata_tables', 'origin',
  'metadata_tables should have origin column');

SELECT has_column('_realtime', 'metadata_tables', 'created_at',
  'metadata_tables should have created_at column');

SELECT has_column('_realtime', 'metadata_tables', 'user_id',
  'metadata_tables should have user_id column for data isolation');

-- Test column types
SELECT col_type_is('_realtime', 'metadata_tables', 'id', 'integer',
  'id column should be integer type');

SELECT col_type_is('_realtime', 'metadata_tables', 'table_name', 'text',
  'table_name column should be text type');

SELECT col_type_is('_realtime', 'metadata_tables', 'main_table', 'text',
  'main_table column should be text type');

SELECT col_type_is('_realtime', 'metadata_tables', 'user_id', 'uuid',
  'user_id column should be uuid type');

-- ============================================================================
-- TEST 3: PRIMARY KEY AND INDEXES
-- ============================================================================

-- Test primary key constraint
SELECT has_pk('_realtime', 'metadata_tables',
  'metadata_tables should have a primary key');

-- Test that id is the primary key
SELECT col_is_pk('_realtime', 'metadata_tables', 'id',
  'id should be the primary key of metadata_tables');

-- Test indexes exist for performance
SELECT has_index('_realtime', 'metadata_tables', 'idx_metadata_table_name',
  'Index on table_name should exist for faster lookups');

SELECT has_index('_realtime', 'metadata_tables', 'idx_metadata_main_table',
  'Index on main_table should exist for grouping related chunks');

SELECT has_index('_realtime', 'metadata_tables', 'idx_metadata_user_id',
  'Index on user_id should exist for user isolation queries');

-- ============================================================================
-- TEST 4: ROW LEVEL SECURITY
-- ============================================================================

-- Test that RLS is enabled on metadata_tables
-- Using direct query since row_security_is may not be available in all pgTAP versions
SELECT is(
  (SELECT relrowsecurity FROM pg_class WHERE oid = '_realtime.metadata_tables'::regclass),
  true,
  'RLS should be enabled on metadata_tables'
);

-- Finish tests
SELECT * FROM finish();

ROLLBACK;
