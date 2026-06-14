-- 002_catalogue.sql — Model catalogue, regulatory thresholds, and run extensions.
-- Idempotent: uses IF NOT EXISTS and ADD COLUMN IF NOT EXISTS throughout.
-- Applied after 001_schema.sql by the plugin loader.

-- -------------------------------------------------------------------------
-- Model catalogue: one row per bundled PBPK study (slug = primary key).
-- Seeded/upserted at first request by catalogue.py::seed_models().
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS _fd.pbpk_models (
    slug          TEXT PRIMARY KEY,
    label         TEXT NOT NULL,
    description   TEXT NOT NULL DEFAULT '',
    chemicals     TEXT[] NOT NULL DEFAULT '{}',
    population    TEXT NOT NULL DEFAULT '',
    life_stage    TEXT NOT NULL DEFAULT '',
    reference_doi TEXT NOT NULL DEFAULT '',
    sbml_file     TEXT NOT NULL DEFAULT '',
    applicability JSONB NOT NULL DEFAULT '{}'::jsonb,
    fair_badges   JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at    TIMESTAMP NOT NULL DEFAULT NOW()
);

-- -------------------------------------------------------------------------
-- Regulatory thresholds: plasma concentration limits per chemical / basis.
-- Pre-seeded with EFSA 2020 group TWI-derived values.
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS _fd.pbpk_thresholds (
    id         SERIAL PRIMARY KEY,
    chemical   TEXT NOT NULL,
    endpoint   TEXT NOT NULL DEFAULT 'plasma',
    value      DOUBLE PRECISION NOT NULL,
    units      TEXT NOT NULL DEFAULT 'ng/mL',
    basis      TEXT NOT NULL DEFAULT '',
    doi        TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- EFSA 2020 group TWI plasma thresholds (PFOA + PFOS, same value as per group TWI).
-- EFSA CONTAM Panel (2020). doi:10.2903/j.efsa.2020.6223.
-- 4.4 ng/kg bw/week group TWI → ~6.9 ng/mL steady-state plasma (via PBK, adults).
INSERT INTO _fd.pbpk_thresholds (chemical, endpoint, value, units, basis, doi)
SELECT 'PFOA', 'plasma', 6.9, 'ng/mL',
       'EFSA 2020 group TWI (4.4 ng/kg bw/week for PFOS+PFOA+PFNA+PFHxS); plasma equivalent via adult PBK',
       '10.2903/j.efsa.2020.6223'
WHERE NOT EXISTS (
    SELECT 1 FROM _fd.pbpk_thresholds WHERE chemical = 'PFOA' AND doi = '10.2903/j.efsa.2020.6223'
);

INSERT INTO _fd.pbpk_thresholds (chemical, endpoint, value, units, basis, doi)
SELECT 'PFOS', 'plasma', 6.9, 'ng/mL',
       'EFSA 2020 group TWI (4.4 ng/kg bw/week for PFOS+PFOA+PFNA+PFHxS); plasma equivalent via adult PBK',
       '10.2903/j.efsa.2020.6223'
WHERE NOT EXISTS (
    SELECT 1 FROM _fd.pbpk_thresholds WHERE chemical = 'PFOS' AND doi = '10.2903/j.efsa.2020.6223'
);

-- -------------------------------------------------------------------------
-- Extend simulation runs with study-level provenance columns.
-- -------------------------------------------------------------------------
ALTER TABLE _fd.pbpk_simulation_runs
    ADD COLUMN IF NOT EXISTS study_slug   TEXT,
    ADD COLUMN IF NOT EXISTS compound     TEXT,
    ADD COLUMN IF NOT EXISTS engine       TEXT NOT NULL DEFAULT 'scipy_lsoda',
    ADD COLUMN IF NOT EXISTS content_hash TEXT;

CREATE INDEX IF NOT EXISTS pbpk_runs_study_slug_idx
    ON _fd.pbpk_simulation_runs(study_slug);
CREATE INDEX IF NOT EXISTS pbpk_runs_content_hash_idx
    ON _fd.pbpk_simulation_runs(content_hash);

-- -------------------------------------------------------------------------
-- Model catalogue extensions: readiness tier and capability tags.
-- Added after initial schema — idempotent via ADD COLUMN IF NOT EXISTS.
-- -------------------------------------------------------------------------
ALTER TABLE _fd.pbpk_models
    ADD COLUMN IF NOT EXISTS readiness    TEXT     NOT NULL DEFAULT 'experimental',
    ADD COLUMN IF NOT EXISTS capabilities TEXT[]   NOT NULL DEFAULT '{}';
