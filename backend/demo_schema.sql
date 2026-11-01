-- backend/volumes/db/demo_schema.sql
-- Demo schema with synthetic microbiome data and RLS policies

-- Create demo schema
CREATE SCHEMA IF NOT EXISTS _demo;

-- Create datasets table
CREATE TABLE IF NOT EXISTS _demo.datasets (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL UNIQUE,
    organ VARCHAR(100),
    cohort VARCHAR(255),
    sample_count INTEGER DEFAULT 0,
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create query_results table for aggregated data
CREATE TABLE IF NOT EXISTS _demo.query_results (
    id SERIAL PRIMARY KEY,
    dataset VARCHAR(255) NOT NULL,
    organism VARCHAR(255),
    taxonomy_id INTEGER,
    sample_type VARCHAR(100),
    abundance FLOAT,
    diversity FLOAT,
    richness INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Enable RLS
ALTER TABLE _demo.datasets ENABLE ROW LEVEL SECURITY;
ALTER TABLE _demo.query_results ENABLE ROW LEVEL SECURITY;

-- Policy: Anyone can read demo data (read-only)
DROP POLICY IF EXISTS demo_read_policy ON _demo.datasets;
CREATE POLICY demo_read_policy ON _demo.datasets
    FOR SELECT USING (true);

DROP POLICY IF EXISTS demo_query_read_policy ON _demo.query_results;
CREATE POLICY demo_query_read_policy ON _demo.query_results
    FOR SELECT USING (true);

-- Read-only role for the demo data. Nothing logs in as it (the public demo
-- API reads through the app's own connection), so it gets no password and
-- cannot log in. It used to be LOGIN with a password written in this file;
-- the ALTER below takes that away on databases created before the change.
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'demo_role') THEN
        CREATE ROLE demo_role NOLOGIN;
    ELSE
        ALTER ROLE demo_role NOLOGIN PASSWORD NULL;
    END IF;
END
$$;

-- Grant SELECT on demo schema to demo_role
GRANT USAGE ON SCHEMA _demo TO demo_role;
GRANT SELECT ON ALL TABLES IN SCHEMA _demo TO demo_role;

-- Insert synthetic demo data (anonymized/synthetic microbiome data)
INSERT INTO _demo.datasets (name, organ, cohort, sample_count, description) VALUES
    ('gut_microbiome', 'gut', 'HMP', 150, 'Synthetic gut microbiome data'),
    ('oral_microbiome', 'oral', 'HMP', 120, 'Synthetic oral microbiome data'),
    ('skin_microbiome', 'skin', 'HMP', 100, 'Synthetic skin microbiome data')
ON CONFLICT (name) DO NOTHING;

-- Insert synthetic query results
INSERT INTO _demo.query_results (dataset, organism, taxonomy_id, sample_type, abundance, diversity, richness) VALUES
    ('gut_microbiome', 'Bacteroides vulgatus', 821, 'feces', 0.15, 2.8, 45),
    ('gut_microbiome', 'Escherichia coli', 562, 'feces', 0.08, 2.8, 45),
    ('gut_microbiome', 'Lactobacillus acidophilus', 1598, 'feces', 0.12, 2.8, 45),
    ('oral_microbiome', 'Streptococcus mutans', 1313, 'saliva', 0.25, 2.1, 30),
    ('oral_microbiome', 'Porphyromonas gingivalis', 831, 'saliva', 0.05, 2.1, 30),
    ('skin_microbiome', 'Propionibacterium acnes', 1747, 'skin', 0.30, 1.9, 25),
    ('skin_microbiome', 'Staphylococcus epidermidis', 1282, 'skin', 0.20, 1.9, 25)
ON CONFLICT DO NOTHING;