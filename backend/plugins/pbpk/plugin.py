"""PBPK plugin manifest. See docs/PLUGIN_GUIDE.md §5.

Lifetime PBPK simulation: parameter sets, simulation runs, and binary run
artifacts (jpg/png/mp4/vtk). Migrated from src/model/ (migration plan Phase 4).

``url_prefix`` is kept at ``/model`` for backward compatibility — the existing
frontend issues hardcoded ``/model/*`` fetch calls.
"""
from kernel.plugin import Plugin

from .routes import routes

PLUGIN = Plugin(
    name="pbpk",
    version="0.1.0",
    url_prefix="/model",
    blueprint=routes,

    sql_migrations=[
        "sql/001_schema.sql",
        # 002_catalogue.sql adds the _fd.pbpk_models (catalogue),
        # _fd.pbpk_thresholds (regulatory thresholds), and the
        # study_slug / compound / engine / content_hash columns on
        # _fd.pbpk_simulation_runs. Without this migration the
        # catalogue and run-comparison features fail with
        # UndefinedTable. The seed values for the EFSA 2020 group
        # TWI plasma equivalent (6.9 ng/mL for PFOA and PFOS) are
        # included in the migration and applied idempotently.
        "sql/002_catalogue.sql",
        # 003_ontology.sql creates _fd.pbpk_iri_labels (OLS4 label cache) and
        # _fd.pbpk_cv_terms (per-study SBML CV-term inventory). Populated by
        # ontology.seed_ontology_terms() at first ensure_seeded() call.
        "sql/003_ontology.sql",
    ],

    # Importable module names — verified by the loader at boot. Installed via
    # ``plugins/pbpk/requirements.txt`` (pip dist names: ``scipy``,
    # ``python-libsbml``).
    required_packages=["scipy", "libsbml"],

    storage_buckets=[{
        "id": "pbpk-artifacts",            # MUST start with "<name>-"
        "public": False,
        "size_limit": 200 * 1024 * 1024,   # 200 MB — keep in sync with routes
        # ``kernel.storage.upload_stream`` rejects any content_type outside
        # this set. Mirrors the in-route ``_ARTIFACT_TYPES`` whitelist; .vtk/
        # .vtu/.vtp arrive as application/octet-stream and are distinguished
        # by extension inside the route.
        "mime_whitelist": {
            "image/jpeg",
            "image/png",
            "video/mp4",
            "application/octet-stream",
        },
    }],

    # Some routes are open to any authenticated user (UI, scenario list,
    # parameter-set catalog); row-level run/artifact routes are admin/curator/
    # accessor. visualizer reaches only the open routes, never row-level data.
    roles_required=("admin", "curator", "accessor", "visualizer"),

    templates_dir="templates",
    # One flat sidebar entry — the studies switcher lives inside the plugin
    # pages (templates/pbpk/_studies_tabs.html), not in the global sidebar.
    nav={"label": "PBK Module", "icon": "flask", "path": "catalogue"},
)
