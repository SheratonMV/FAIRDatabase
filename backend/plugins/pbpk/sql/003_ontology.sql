-- 003_ontology.sql
-- Ontology term tables for the PBK module.
--
-- _fd.pbpk_iri_labels  — shared IRI → label cache (populated by EBI OLS4 at seed time)
-- _fd.pbpk_cv_terms    — per-study element → IRI CV-term inventory (extracted from SBML)
--
-- Applied idempotently by the plugin loader; safe to re-run on an existing DB.

CREATE TABLE IF NOT EXISTS _fd.pbpk_iri_labels (
    iri        TEXT PRIMARY KEY,
    ontology   TEXT,           -- 'PBPKO' | 'CHEBI' | 'UBERON' | 'NCBITaxon' | …
    local_id   TEXT,           -- 'PBPKO:00488', 'CHEBI:35924', etc.
    label      TEXT,           -- NULL until resolved via OLS4
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS _fd.pbpk_cv_terms (
    id           BIGSERIAL PRIMARY KEY,
    study_slug   TEXT        NOT NULL,
    element_id   TEXT        NOT NULL,
    element_type TEXT        NOT NULL,   -- 'compartment' | 'species' | 'parameter' | 'reaction' | 'model'
    qualifier    TEXT        NOT NULL,   -- 'BQB_IS' | 'BQB_HAS_PART' | 'BQB_HAS_PROPERTY' | etc.
    iri          TEXT        NOT NULL REFERENCES _fd.pbpk_iri_labels(iri),
    UNIQUE (study_slug, element_id, qualifier, iri)
);

CREATE INDEX IF NOT EXISTS pbpk_cv_terms_slug_idx ON _fd.pbpk_cv_terms(study_slug);
CREATE INDEX IF NOT EXISTS pbpk_cv_terms_iri_idx  ON _fd.pbpk_cv_terms(iri);
