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
