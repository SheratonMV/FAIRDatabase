"""catalogue.py — DB helpers for the PBK model catalogue, regulatory thresholds,
and extended run history.

The catalogue is seeded from _MODEL_SEEDS at first request via seed_models().
All functions use g.db (the per-request psycopg2 connection established by
app.before_request).
"""
from __future__ import annotations

import hashlib as _hashlib
import json
import pathlib
from typing import Any

import psycopg2.extras
from flask import g

# ── Model seed data ───────────────────────────────────────────────────────────
# One entry per bundled study. slug must match studies/__init__.py::STUDIES keys.

_MODEL_SEEDS: list[dict[str, Any]] = [
    {
        "slug": "ratier",
        "readiness": "ready",
        "capabilities": ["timecourse", "breastfeeding_scenarios", "validation_data"],
        "label": "Ratier et al. (2024) — Lifetime PFAS PBPK",
        "description": (
            "Whole-body lifetime PFAS pharmacokinetic model for mother–child pairs, "
            "covering transplacental transfer, lactation, and postnatal childhood accumulation. "
            "Originally developed by Beaudouin et al. and extended by Ratier et al. (2024) "
            "for the HELIX birth cohort."
        ),
        "chemicals": ["PFOA", "PFOS"],
        "population": "Pregnant women and infants (HELIX cohort)",
        "life_stage": "Pregnancy → lactation → childhood (0–6.77 yr)",
        "reference_doi": "10.1016/j.envint.2024.108621",
        "sbml_file": "Ratier2024FAIR.xml",
        "applicability": {
            "domain": "Maternal dietary PFAS exposure; transplacental transfer; infant accumulation",
            "calibration_range": "Birth year 1990–2020; PFOA half-life 2–5 yr; dietary intake 0.1–2 ng/kg/min",
            "limitations": [
                "Breast-milk intake pathway (C_milk) not yet activated — all 4 breastfeeding scenarios return identical infant C_ven",
                "Calibrated on HELIX cohort (European children); extrapolation to other cohorts requires re-parameterisation",
                "No mechanistic hepatic metabolism (first-order clearance only)",
            ],
            "regulatory_status": "PARC project reference model; research use",
        },
        "fair_badges": {
            "F1_uuid_runs": True,
            "F1_zenodo_doi": True,
            "F1_zenodo_doi_value": "10.5281/zenodo.20447876",
            "F2_run_metadata": True,
            "A1_rest_api": True,
            "I1_sbml_l3v2": True,
            "I3_uses_fair_vocabularies": True,
            "I3_ontologies": ["PBPKO", "UBERON", "CHEBI", "NCBITaxon"],
            "R1_params_in_db": True,
            "R1_1_open_license": True,
            "R1_1_license_spdx": "CC-BY-4.0",
            "R1_2_provenance": True,
            "R1_3_sbml_standard": True,
        },
    },
    {
        "slug": "rovira",
        "readiness": "review",
        "capabilities": ["timecourse", "pregnancy", "validation_data"],
        "label": "Rovira et al. (2019) — PFAS Pregnancy PBPK",
        "description": (
            "Multi-route exposure PFAS PBPK model for the Spanish INMA pregnancy cohort. "
            "Combines food-frequency-questionnaire dietary exposure with drinking water and "
            "indoor dust routes. Reports maternal plasma and cord-blood PFAS at two gestational "
            "snapshots: GW12 and GW38."
        ),
        "chemicals": ["PFOA", "PFOS"],
        "population": "Pregnant women (INMA cohort, Spain)",
        "life_stage": "Pregnancy (GW0–GW38); output at GW12 and GW38",
        "reference_doi": "10.1016/j.envres.2019.05.040",
        "sbml_file": "Rovira2019FAIR.xml",
        "applicability": {
            "domain": "Maternal multi-route PFAS exposure during pregnancy; cord-blood at delivery",
            "calibration_range": "Initial maternal plasma 1–10 ng/mL; body weight 50–80 kg",
            "limitations": [
                "Only 2 output time points (GW12, GW38) — no continuous gestational trajectory",
                "No postnatal infant trajectory",
                "Near-unity fetal/maternal transfer ratio may overestimate at high maternal concentrations",
            ],
            "regulatory_status": "Research use; referenced in EFSA PFAS opinion 2020",
        },
        "fair_badges": {
            "F1_uuid_runs": True,
            "F1_zenodo_doi": True,
            "F1_zenodo_doi_value": "10.5281/zenodo.20447876",
            "F2_run_metadata": True,
            "A1_rest_api": True,
            "I1_sbml_l3v2": True,
            "I3_uses_fair_vocabularies": True,
            "I3_ontologies": ["PBPKO", "UBERON", "CHEBI", "NCBITaxon"],
            "R1_params_in_db": True,
            "R1_1_open_license": True,
            "R1_1_license_spdx": "CC-BY-4.0",
            "R1_2_provenance": True,
            "R1_3_sbml_standard": True,
        },
    },
    {
        "slug": "verner",
        "readiness": "ready",
        "capabilities": ["timecourse", "montecarlo", "breastfeeding_scenarios", "validation_data"],
        "label": "Verner 2015 / Ouidir et al. (2025) — PFOS Monte Carlo PBPK",
        "description": (
            "Population-level Monte Carlo PBPK model for PFOS maternal and fetal exposure during "
            "pregnancy. Parameterised from Verner et al. (2015) and applied to the NICHD Nuage "
            "cohort by Ouidir et al. (2025). Propagates parameter uncertainty across n iterations "
            "to produce mean trajectories and percentile bands for gestational months 1–9."
        ),
        "chemicals": ["PFOA", "PFOS"],
        "population": "Pregnant women (NICHD Nuage cohort, USA)",
        "life_stage": "Pregnancy (gestational months 1–9)",
        "reference_doi": "10.1016/j.envres.2025.121814",
        "sbml_file": "Ouidir2025FAIR.xml",
        "applicability": {
            "domain": "Population-level maternal and fetal PFOS exposure during pregnancy",
            "calibration_range": "PFOS half-life 4–7 yr; initial plasma 2–25 ng/mL; n_iter ≥ 50",
            "limitations": [
                "Default n_iter=50 is low for extreme-percentile characterisation; recommend ≥1000 for production",
                "No postnatal trajectory; output ends at delivery",
                "PFOS only — not validated for PFOA or short-chain PFAS",
            ],
            "regulatory_status": "Research use; EFSA 2020 PFAS opinion reference",
        },
        "fair_badges": {
            "F1_uuid_runs": True,
            "F1_zenodo_doi": True,
            "F1_zenodo_doi_value": "10.5281/zenodo.20447876",
            "F2_run_metadata": True,
            "A1_rest_api": True,
            "I1_sbml_l3v2": True,
            "I3_uses_fair_vocabularies": True,
            "I3_ontologies": ["PBPKO", "UBERON", "CHEBI", "NCBITaxon"],
            "R1_params_in_db": True,
            "R1_1_open_license": True,
            "R1_1_license_spdx": "CC-BY-4.0",
            "R1_2_provenance": True,
            "R1_3_sbml_standard": True,
        },
    },
    {
        "slug": "generic",
        "readiness": "experimental",
        "capabilities": ["timecourse", "breastfeeding_scenarios", "pregnancy", "child"],
        "label": "Generic PFAS PBPK",
        "description": (
            "General-purpose PFAS PBPK model covering the full pregnancy and early-childhood "
            "period (GW0 to 12 years). Parameterised for PFOA and PFOS with pre-computed tissue "
            "partition coefficients. Intended for exploratory scenario analysis outside validated "
            "cohort-specific parameterisations."
        ),
        "chemicals": ["PFOA", "PFOS"],
        "population": "General adult/child population (not cohort-specific)",
        "life_stage": "Pregnancy (GW0–GW40) → childhood (0–12 yr)",
        "reference_doi": "10.5281/zenodo.20447876",
        "sbml_file": "GenericPBKFAIR.xml",
        "applicability": {
            "domain": "Exploratory PFAS pharmacokinetics across the full life span",
            "calibration_range": "General reference physiology; see SBML parameter notes",
            "limitations": [
                "Generic parameterisation — not validated against a specific cohort or dataset",
                "Exploratory use only; not suitable for regulatory submissions without re-parameterisation",
            ],
            "regulatory_status": "Exploratory / research only",
        },
        "fair_badges": {
            "F1_uuid_runs": True,
            "F1_zenodo_doi": True,
            "F1_zenodo_doi_value": "10.5281/zenodo.20447876",
            "F2_run_metadata": True,
            "A1_rest_api": True,
            "I1_sbml_l3v2": True,
            "I3_uses_fair_vocabularies": True,
            "I3_ontologies": ["PBPKO", "UBERON", "CHEBI", "NCBITaxon"],
            "R1_params_in_db": True,
            "R1_1_open_license": True,
            "R1_1_license_spdx": "CC-BY-4.0",
            "R1_2_provenance": True,
            "R1_3_sbml_standard": True,
        },
    },
]

# Track whether the catalogue has been seeded this process lifetime.
_seeded = False


def ensure_seeded() -> None:
    """Upsert catalogue entries and ontology terms on first request per worker.

    Uses a single SELECT instead of 4 blind UPSERTs on every cold-worker
    start. The process-level ``_seeded`` flag still short-circuits the
    SELECT on subsequent requests within the same worker lifetime.
    """
    global _seeded
    if _seeded:
        return
    cur = g.db.cursor()
    try:
        cur.execute("SELECT COUNT(*) FROM _fd.pbpk_models")
        count = cur.fetchone()[0]
    finally:
        cur.close()
    if count < len(_MODEL_SEEDS):
        seed_models()
    _seed_ontology_terms()
    _seeded = True


def _seed_ontology_terms() -> None:
    """Seed CV terms for all models that have no rows yet in _fd.pbpk_cv_terms."""
    from .ontology import seed_ontology_terms  # local import avoids circular

    _plugin_dir = pathlib.Path(__file__).parent
    for m in _MODEL_SEEDS:
        slug = m["slug"]
        sbml_path = _plugin_dir / "studies" / slug / m["sbml_file"]
        if not sbml_path.exists():
            continue
        cur = g.db.cursor()
        try:
            cur.execute(
                "SELECT COUNT(*) FROM _fd.pbpk_cv_terms WHERE study_slug = %s",
                (slug,),
            )
            already = cur.fetchone()[0]
        finally:
            cur.close()
        if already == 0:
            seed_ontology_terms(slug, str(sbml_path), g.db)


def seed_models() -> None:
    """Upsert all _MODEL_SEEDS into _fd.pbpk_models."""
    cur = g.db.cursor()
    try:
        for m in _MODEL_SEEDS:
            cur.execute(
                """
                INSERT INTO _fd.pbpk_models
                    (slug, label, description, chemicals, population,
                     life_stage, reference_doi, sbml_file, applicability, fair_badges,
                     readiness, capabilities)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s)
                ON CONFLICT (slug) DO UPDATE SET
                    label         = EXCLUDED.label,
                    description   = EXCLUDED.description,
                    chemicals     = EXCLUDED.chemicals,
                    population    = EXCLUDED.population,
                    life_stage    = EXCLUDED.life_stage,
                    reference_doi = EXCLUDED.reference_doi,
                    sbml_file     = EXCLUDED.sbml_file,
                    applicability = EXCLUDED.applicability,
                    fair_badges   = EXCLUDED.fair_badges,
                    readiness     = EXCLUDED.readiness,
                    capabilities  = EXCLUDED.capabilities
                """,
                (
                    m["slug"], m["label"], m["description"],
                    m["chemicals"], m["population"], m["life_stage"],
                    m["reference_doi"], m["sbml_file"],
                    json.dumps(m["applicability"]),
                    json.dumps(m["fair_badges"]),
                    m.get("readiness", "experimental"),
                    m.get("capabilities", []),
                ),
            )
        g.db.commit()
    except Exception:
        g.db.rollback()
        raise
    finally:
        cur.close()


def list_models() -> list[dict]:
    ensure_seeded()
    cur = g.db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        """
        SELECT slug, label, description, chemicals, population, life_stage,
               reference_doi, sbml_file, applicability, fair_badges,
               readiness, capabilities
        FROM _fd.pbpk_models
        ORDER BY slug
        """
    )
    rows = cur.fetchall()
    cur.close()
    return [_deser_model(dict(r)) for r in rows]


def fetch_model(slug: str) -> dict | None:
    ensure_seeded()
    cur = g.db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        """
        SELECT slug, label, description, chemicals, population, life_stage,
               reference_doi, sbml_file, applicability, fair_badges,
               readiness, capabilities
        FROM _fd.pbpk_models
        WHERE slug = %s
        """,
        (slug,),
    )
    row = cur.fetchone()
    cur.close()
    return _deser_model(dict(row)) if row else None


def _deser_model(row: dict) -> dict:
    for field in ("applicability", "fair_badges"):
        if isinstance(row.get(field), str):
            row[field] = json.loads(row[field])
    return row


# ── Thresholds ────────────────────────────────────────────────────────────────

def list_thresholds(chemical: str | None = None) -> list[dict]:
    cur = g.db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    if chemical:
        cur.execute(
            """
            SELECT id, chemical, endpoint, value, units, basis, doi, created_at
            FROM _fd.pbpk_thresholds WHERE chemical = %s ORDER BY chemical, endpoint
            """,
            (chemical,),
        )
    else:
        cur.execute(
            """
            SELECT id, chemical, endpoint, value, units, basis, doi, created_at
            FROM _fd.pbpk_thresholds ORDER BY chemical, endpoint
            """
        )
    rows = cur.fetchall()
    cur.close()
    return [_dt(dict(r)) for r in rows]


def create_threshold(chemical: str, endpoint: str, value: float,
                     units: str, basis: str, doi: str) -> int:
    cur = g.db.cursor()
    try:
        cur.execute(
            """
            INSERT INTO _fd.pbpk_thresholds (chemical, endpoint, value, units, basis, doi)
            VALUES (%s, %s, %s, %s, %s, %s) RETURNING id
            """,
            (chemical, endpoint, value, units, basis, doi),
        )
        new_id = cur.fetchone()[0]
        g.db.commit()
    except Exception:
        g.db.rollback()
        raise
    finally:
        cur.close()
    return new_id


def _dt(row: dict) -> dict:
    if row.get("created_at") is not None:
        row["created_at"] = row["created_at"].isoformat()
    return row


# ── Extended run helpers ──────────────────────────────────────────────────────

def create_study_run(
    study_slug: str,
    scenario: str,
    compound: str | None,
    created_by: str,
    owner_id: str | None = None,
    engine: str = "scipy_lsoda",
    content_hash: str | None = None,
) -> int:
    """Insert a new simulation run for a bundled study (param_set_id=NULL)."""
    cur = g.db.cursor()
    try:
        cur.execute(
            """
            INSERT INTO _fd.pbpk_simulation_runs
                (study_slug, scenario, compound, engine, content_hash,
                 status, created_by, owner_id)
            VALUES (%s, %s, %s, %s, %s, 'pending', %s, %s)
            RETURNING id
            """,
            (study_slug, scenario or "", compound, engine,
             content_hash, created_by, owner_id),
        )
        row = cur.fetchone()
        g.db.commit()
    except Exception:
        g.db.rollback()
        raise
    finally:
        cur.close()
    return row[0]


def canonical_hash(slug: str, payload: dict) -> str:
    """SHA-256 of canonical JSON(slug + sorted payload). Used as cache key."""
    data = json.dumps({"slug": slug, **payload}, sort_keys=True, separators=(",", ":"))
    return _hashlib.sha256(data.encode()).hexdigest()


def find_cached_run(content_hash: str) -> int | None:
    """Return the id of a successful run with this hash, or None."""
    cur = g.db.cursor()
    cur.execute(
        """
        SELECT id FROM _fd.pbpk_simulation_runs
        WHERE content_hash = %s AND status = 'done'
        ORDER BY created_at DESC LIMIT 1
        """,
        (content_hash,),
    )
    row = cur.fetchone()
    cur.close()
    return row[0] if row else None


def fetch_runs_for_compare(run_ids: list[int], user_id: str, role: str) -> list[dict]:
    """Fetch multiple completed runs for side-by-side comparison.

    Only returns runs with status='done'. Admins see any run; other roles are
    restricted to their own runs (owner_id match). Returns runs ordered by
    creation date so overlay datasets have a deterministic order.
    """
    if not run_ids:
        return []
    placeholders = ",".join(["%s"] * len(run_ids))
    cur = g.db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    if role == "admin":
        cur.execute(
            f"""
            SELECT id, study_slug, scenario, compound, engine, status,
                   summary, timeseries, created_by, created_at
            FROM _fd.pbpk_simulation_runs
            WHERE id IN ({placeholders}) AND status = 'done'
            ORDER BY created_at
            """,
            run_ids,
        )
    else:
        cur.execute(
            f"""
            SELECT id, study_slug, scenario, compound, engine, status,
                   summary, timeseries, created_by, created_at
            FROM _fd.pbpk_simulation_runs
            WHERE id IN ({placeholders}) AND status = 'done'
              AND owner_id = %s
            ORDER BY created_at
            """,
            [*run_ids, user_id],
        )
    rows = cur.fetchall()
    cur.close()
    out = []
    for row in rows:
        r = dict(row)
        if isinstance(r.get("summary"), str):
            r["summary"] = json.loads(r["summary"])
        if isinstance(r.get("timeseries"), str):
            r["timeseries"] = json.loads(r["timeseries"])
        if r.get("created_at") is not None:
            r["created_at"] = r["created_at"].isoformat()
        out.append(r)
    return out


def list_run_history(user_id: str, role: str, limit: int = 50) -> list[dict]:
    """Return recent simulation runs visible to this user, newest first."""
    cur = g.db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    if role == "admin":
        cur.execute(
            """
            SELECT id, study_slug, param_set_id, scenario, compound, engine,
                   status, summary, created_by, created_at
            FROM _fd.pbpk_simulation_runs
            ORDER BY created_at DESC LIMIT %s
            """,
            (limit,),
        )
    else:
        cur.execute(
            """
            SELECT id, study_slug, param_set_id, scenario, compound, engine,
                   status, summary, created_by, created_at
            FROM _fd.pbpk_simulation_runs
            WHERE owner_id = %s
            ORDER BY created_at DESC LIMIT %s
            """,
            (user_id, limit),
        )
    rows = cur.fetchall()
    cur.close()
    out = []
    for row in rows:
        r = dict(row)
        if isinstance(r.get("summary"), str):
            r["summary"] = json.loads(r["summary"])
        if r.get("created_at") is not None:
            r["created_at"] = r["created_at"].isoformat()
        out.append(r)
    return out
