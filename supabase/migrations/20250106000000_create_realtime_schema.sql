-- Create custom schema for realtime data
CREATE SCHEMA IF NOT EXISTS _realtime;

-- Set search path to include _realtime schema
-- Note: This affects the database globally, allowing easy access to _realtime tables
ALTER DATABASE postgres SET search_path TO public, _realtime;
