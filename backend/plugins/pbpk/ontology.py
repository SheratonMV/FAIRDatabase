"""ontology.py — CV-term extraction and ontology label enrichment for PBK models.

Parses SBML-encoded CV-term annotations (bqbiol:is, bqbiol:hasPart, etc.) from
the four bundled FAIR SBML files using libsbml, normalises IRIs to a canonical
(ontology, local_id) form, and resolves human-readable labels via the EBI OLS4
REST API. Results are stored in two DB tables:

  _fd.pbpk_iri_labels   — IRI → ontology + local_id + label  (shared cache)
  _fd.pbpk_cv_terms     — per-study element → IRI mappings

Called once per process from catalogue.ensure_seeded(); subsequent boots skip
the SBML parse and OLS calls because all IRIs are already in the DB.
"""
from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING
from urllib.parse import quote as _urlquote

import libsbml
import requests

if TYPE_CHECKING:
    import psycopg2

log = logging.getLogger(__name__)

_OLS4_BASE = "https://www.ebi.ac.uk/ols4/api/terms"
_OLS_TIMEOUT = 2  # seconds per term lookup

# Maps the first matching prefix to (ontology_name, local_id_builder)
_IRI_PREFIXES: list[tuple[str, str, str]] = [
    # (prefix_to_match, ontology_label, local_id_format_hint)
    ("http://purl.obolibrary.org/obo/PBPKO_",  "PBPKO",    "PBPKO"),
    ("http://purl.obolibrary.org/obo/UBERON_", "UBERON",   "UBERON"),
    ("http://purl.obolibrary.org/obo/GO_",     "GO",       "GO"),
    ("http://purl.obolibrary.org/obo/BTO_",    "BTO",      "BTO"),
    ("http://purl.obolibrary.org/obo/",        "OBO",      "OBO"),
    ("https://identifiers.org/CHEBI:",         "CHEBI",    "CHEBI"),
    ("http://identifiers.org/CHEBI:",          "CHEBI",    "CHEBI"),
    ("https://identifiers.org/taxonomy/",      "NCBITaxon","NCBITaxon"),
    ("http://identifiers.org/taxonomy/",       "NCBITaxon","NCBITaxon"),
]


def normalise_iri(iri: str) -> dict:
    """Return {iri, ontology, local_id} from a raw IRI string.

    Examples
    --------
    'http://purl.obolibrary.org/obo/PBPKO_00488'
        → {ontology: 'PBPKO', local_id: 'PBPKO:00488'}
    'https://identifiers.org/CHEBI:35924'
        → {ontology: 'CHEBI', local_id: 'CHEBI:35924'}
    'https://identifiers.org/taxonomy/9606'
        → {ontology: 'NCBITaxon', local_id: 'NCBITaxon:9606'}
    """
    for prefix, ontology, label_prefix in _IRI_PREFIXES:
        if iri.startswith(prefix):
            local_part = iri[len(prefix):]
            # OBO PURLs use underscores: PBPKO_00488 → PBPKO:00488
            if "_" in local_part and ontology not in ("NCBITaxon",):
                local_id = local_part.replace("_", ":", 1)
            else:
                local_id = f"{label_prefix}:{local_part}"
            return {"iri": iri, "ontology": ontology, "local_id": local_id}
    # Unknown prefix — derive a short form from the last path segment
    local_id = re.split(r"[/#]", iri.rstrip("/"))[-1]
    return {"iri": iri, "ontology": "UNKNOWN", "local_id": local_id}


def extract_cv_terms(sbml_path: str) -> list[dict]:
    """Walk all elements in the SBML file and collect every CV-term resource IRI.

    Returns a list of dicts with keys:
        element_id, element_type, qualifier, iri
    """
    reader = libsbml.SBMLReader()
    doc = reader.readSBMLFromFile(sbml_path)
    if doc.getNumErrors() > 0:
        for i in range(doc.getNumErrors()):
            e = doc.getError(i)
            if e.getSeverity() >= libsbml.LIBSBML_SEV_ERROR:
                log.warning("SBML parse error in %s: %s", sbml_path, e.getMessage())

    model = doc.getModel()
    if model is None:
        log.error("No model found in %s", sbml_path)
        return []

    terms: list[dict] = []

    def _collect(element, element_type: str) -> None:
        eid = element.getId() or ""
        n = element.getNumCVTerms()
        for i in range(n):
            cvt = element.getCVTerm(i)
            # Determine qualifier string
            qt = cvt.getQualifierType()
            if qt == libsbml.BIOLOGICAL_QUALIFIER:
                q = libsbml.BiolQualifierType_toString(
                    cvt.getBiologicalQualifierType()
                )
            elif qt == libsbml.MODEL_QUALIFIER:
                q = libsbml.ModelQualifierType_toString(
                    cvt.getModelQualifierType()
                )
            else:
                q = "unknown"
            for j in range(cvt.getNumResources()):
                iri = cvt.getResourceURI(j)
                if iri:
                    terms.append({
                        "element_id": eid,
                        "element_type": element_type,
                        "qualifier": q or "unknown",
                        "iri": iri,
                    })

    # Model-level annotations
    _collect(model, "model")

    for i in range(model.getNumCompartments()):
        _collect(model.getCompartment(i), "compartment")
    for i in range(model.getNumSpecies()):
        _collect(model.getSpecies(i), "species")
    for i in range(model.getNumParameters()):
        _collect(model.getParameter(i), "parameter")
    for i in range(model.getNumReactions()):
        _collect(model.getReaction(i), "reaction")

    return terms


def _resolve_one(iri: str) -> str | None:
    """Call OLS4 and return the preferred label for iri, or None on failure."""
    try:
        resp = requests.get(
            _OLS4_BASE,
            params={"iri": iri},
            timeout=_OLS_TIMEOUT,
            headers={"Accept": "application/json"},
        )
        if resp.status_code == 200:
            data = resp.json()
            return data["_embedded"]["terms"][0]["label"]
    except Exception:
        pass
    return None


def resolve_labels_batch(conn, iris: list[str]) -> None:
    """Resolve each IRI in *iris* via OLS4 and upsert into _fd.pbpk_iri_labels.

    IRIs already present with a non-NULL label are skipped. IRIs where OLS4
    returns no label are stored with label=NULL (will be retried next time a
    new IRI is added to the table).
    """
    if not iris:
        return

    # Find which of the provided IRIs are already fully resolved
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT iri FROM _fd.pbpk_iri_labels WHERE iri = ANY(%s) AND label IS NOT NULL",
            (iris,),
        )
        already_resolved = {r[0] for r in cur.fetchall()}
    finally:
        cur.close()

    to_resolve = [i for i in iris if i not in already_resolved]
    if not to_resolve:
        return

    log.info("Resolving %d new IRI labels via OLS4 …", len(to_resolve))
    resolved = 0
    for iri in to_resolve:
        norm = normalise_iri(iri)
        label = _resolve_one(iri)
        if label:
            resolved += 1
        cur = conn.cursor()
        try:
            cur.execute(
                """
                INSERT INTO _fd.pbpk_iri_labels (iri, ontology, local_id, label)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (iri) DO UPDATE SET
                    label      = COALESCE(EXCLUDED.label, _fd.pbpk_iri_labels.label),
                    fetched_at = now()
                """,
                (iri, norm["ontology"], norm["local_id"], label),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            log.warning("DB error upserting label for IRI %s", iri, exc_info=True)
        finally:
            cur.close()

    log.info("OLS4 resolution complete: %d/%d labels resolved", resolved, len(to_resolve))


def seed_ontology_terms(slug: str, sbml_path: str, conn) -> int:
    """Extract CV terms from *sbml_path*, persist to DB, and resolve labels.

    Idempotent — ON CONFLICT DO NOTHING means re-running is safe. Returns the
    number of new cv_term rows inserted.
    """
    terms = extract_cv_terms(sbml_path)
    if not terms:
        log.warning("No CV terms extracted from %s", sbml_path)
        return 0

    # Collect unique IRIs and pre-insert stubs into _fd.pbpk_iri_labels so the
    # FK constraint on pbpk_cv_terms is satisfied.
    unique_iris = list({t["iri"] for t in terms})
    cur = conn.cursor()
    try:
        for iri in unique_iris:
            norm = normalise_iri(iri)
            cur.execute(
                """
                INSERT INTO _fd.pbpk_iri_labels (iri, ontology, local_id)
                VALUES (%s, %s, %s)
                ON CONFLICT (iri) DO NOTHING
                """,
                (iri, norm["ontology"], norm["local_id"]),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        log.error("Failed inserting IRI label stubs for %s", slug, exc_info=True)
        return 0
    finally:
        cur.close()

    # Bulk-insert CV-term rows
    inserted = 0
    cur = conn.cursor()
    try:
        for t in terms:
            cur.execute(
                """
                INSERT INTO _fd.pbpk_cv_terms
                    (study_slug, element_id, element_type, qualifier, iri)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (study_slug, element_id, qualifier, iri) DO NOTHING
                """,
                (slug, t["element_id"], t["element_type"], t["qualifier"], t["iri"]),
            )
            if cur.rowcount:
                inserted += 1
        conn.commit()
    except Exception:
        conn.rollback()
        log.error("Failed inserting CV terms for %s", slug, exc_info=True)
        return 0
    finally:
        cur.close()

    log.info("Seeded %d CV terms for study '%s' (%d unique IRIs)", inserted, slug, len(unique_iris))

    # Resolve labels for any IRIs not yet labelled
    resolve_labels_batch(conn, unique_iris)

    return inserted
