-- Schema Migration: _realtime → _fd
-- Run with: psql -f migrate_schema.sql

-- Create _fd schema
CREATE SCHEMA IF NOT EXISTS _fd;

-- Create metadata_tables
CREATE TABLE IF NOT EXISTS _fd.metadata_tables (
    id SERIAL PRIMARY KEY,
    table_name TEXT NOT NULL,
    main_table TEXT NOT NULL,
    description TEXT,
    origin TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create sample_metadata
CREATE TABLE IF NOT EXISTS _fd.sample_metadata (
    id SERIAL PRIMARY KEY,
    parent_table TEXT NOT NULL,
    sample_id TEXT NOT NULL,
    metadata_field TEXT NOT NULL,
    metadata_value TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(parent_table, sample_id, metadata_field)
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_sample_metadata_parent ON _fd.sample_metadata(parent_table);
CREATE INDEX IF NOT EXISTS idx_sample_metadata_sample ON _fd.sample_metadata(sample_id);

-- Migrate metadata tables (only if source exists)
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = '_realtime'
        AND table_name = 'metadata_tables'
    ) THEN
        INSERT INTO _fd.metadata_tables (table_name, main_table, description, origin, created_at)
        SELECT table_name, main_table, description, origin, created_at
        FROM _realtime.metadata_tables
        ON CONFLICT DO NOTHING;
        RAISE NOTICE 'Migrated metadata_tables';
    ELSE
        RAISE NOTICE 'No _realtime.metadata_tables found - skipping migration';
    END IF;
END $$;

-- Migrate all data tables
DO $$
DECLARE
    tbl RECORD;
BEGIN
    FOR tbl IN
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = '_realtime'
        AND table_name NOT IN ('metadata_tables', 'sample_metadata')
    LOOP
        EXECUTE format('CREATE TABLE IF NOT EXISTS _fd.%I (LIKE _realtime.%I INCLUDING ALL)', tbl.table_name, tbl.table_name);
        EXECUTE format('INSERT INTO _fd.%I SELECT * FROM _realtime.%I ON CONFLICT DO NOTHING', tbl.table_name, tbl.table_name);
        RAISE NOTICE 'Migrated table: %', tbl.table_name;
    END LOOP;
END $$;
