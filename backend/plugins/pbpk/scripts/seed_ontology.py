#!/usr/bin/env python3
"""One-shot seed for the PBK catalogue's ontology CV-terms and OLS4 labels.

``catalogue.ensure_seeded()`` used to trigger this work inline on the first
``/model/catalogue`` request against a fresh database: extracting CV terms
from four SBML files, then making a sequential OLS4 HTTP call (2s timeout
each) for every unique IRI — a multi-minute page load, and one that stalls
hard in air-gapped deployments. Run this once instead, at deploy/boot time,
from the ``backend/`` directory:

    python -m plugins.pbpk.scripts.seed_ontology

Safe to re-run: CV-term inserts are ON CONFLICT DO NOTHING, studies already
seeded are skipped, and any IRI left with ``label IS NULL`` after a prior
OLS4 outage is retried.
"""
from __future__ import annotations

import pathlib
import sys

_BACKEND_DIR = pathlib.Path(__file__).resolve().parents[3]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app import create_app  # noqa: E402
from config import get_db  # noqa: E402
from plugins.pbpk.catalogue import seed_ontology_terms_for_all_models  # noqa: E402
from plugins.pbpk.ontology import retry_unresolved_labels  # noqa: E402


def main() -> None:
    app = create_app()
    with app.app_context():
        from flask import g

        g.db = get_db()
        try:
            seed_ontology_terms_for_all_models()
            n_retried = retry_unresolved_labels(g.db)
            print(f"[seed_ontology] resolved {n_retried} previously-unresolved labels")
        finally:
            g.db.close()


if __name__ == "__main__":
    main()
