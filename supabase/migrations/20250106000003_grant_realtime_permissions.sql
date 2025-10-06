-- Grant permissions on _realtime schema to service_role and anon
-- This allows Supabase API to access the schema

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
