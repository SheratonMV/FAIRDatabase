# PBPK plugin

Lifetime PBPK (physiologically-based pharmacokinetic) simulation. Migrated from
`src/model/` in Phase 4 of the plugin migration (see
`docs/PLUGIN_MIGRATION_PLAN.md`).

## What it does

- **Parameter sets** — named, versioned input parameter collections
  (`_fd.pbpk_parameter_sets`).
- **Simulation runs** — executes a scenario against a parameter set via the
  `PBKFAIRModel` package, persisting status, summary, and timeseries
  (`_fd.pbpk_simulation_runs`). Study runs are content-hash deduplicated
  (`canonical_hash`/`find_cached_run` in `catalogue.py`) — resubmitting
  identical parameters returns the caller's own prior run instead of
  re-simulating; the cache lookup is scoped to the caller (`owner_id`) for
  non-admins so it cannot be used to read back another user's run.
- **Run artifacts** — binary outputs (jpg/png/mp4/vtk) attached to a run; bytes
  in the `pbpk-artifacts` Supabase bucket, catalog rows in
  `_fd.pbpk_run_artifacts`.
- **Model catalogue** — the four bundled FAIR PBK models (`ratier`, `rovira`,
  `verner`, `generic`) exposed with regulatory thresholds, applicability
  domains, and FAIR badges (`_fd.pbpk_models`, `catalogue.py`).
- **Ontology annotations** — SBML `bqbiol:*` CV-terms extracted per model and
  resolved to human-readable labels via EBI OLS4, cached in
  `_fd.pbpk_cv_terms` / `_fd.pbpk_iri_labels` (`ontology.py`). Seeded out of
  band — see "Ontology seeding" below, not on the request path.
- **Regulatory thresholds** — reference values (e.g. the EFSA 2020 Σ4-PFAS
  serum benchmark) shown as chart reference lines and in a thresholds panel
  (`_fd.pbpk_thresholds`).
- **Run history & comparison** — per-user run history and multi-run
  comparison across the bundled studies (`fetch_runs_for_compare`,
  `list_run_history` in `helpers.py`).

Mounted at `url_prefix=/model` (kept for frontend compatibility — the UI issues
hardcoded `/model/*` fetches).

## Endpoints

Lifetime simulation surface: `/ui`, `/run`, `/scenarios`, `/parameter-sets`,
`/runs`, `/runs/<id>`, `/runs/<id>/provenance`, `/runs/<id>/artifacts`,
`/artifacts/<id>`.

Catalogue, ontology, thresholds, and run-history surface (all `login_required`;
narrower roles noted):

- `GET  /catalogue`, `GET /catalogue/<slug>`, `GET /catalogue/<slug>/sbml`
- `GET  /results/<run_id>` — `admin`/`curator`/`accessor` only, ownership-checked
- `GET  /validation`, `GET /history`
- `GET  /api/models`, `GET /api/models/<slug>`, `GET /api/models/<slug>/ontology`
- `GET  /api/thresholds` (open) / `POST /api/thresholds` — `admin`/`curator` only
- `GET  /api/runs`, `POST /api/runs/compare`

Bundled-study surface (`study_routes.py`, mounted under
`/studies/<slug>/...`) is documented separately below.

## Ontology seeding

`ontology.seed_ontology_terms()` parses CV terms out of the four bundled SBML
files and resolves each unique IRI's label via a sequential EBI OLS4 HTTP
call. This is deliberately **not** run from the request path (it used to be,
via `catalogue.ensure_seeded()`, which made the first cold-start
`/model/catalogue` load take minutes and stall hard when OLS4 was
unreachable). Run it once, out of band, from `backend/`:

```
python -m plugins.pbpk.scripts.seed_ontology
```

Safe to re-run — CV-term inserts are `ON CONFLICT DO NOTHING`, already-seeded
studies are skipped, and any IRI left with `label IS NULL` from a prior OLS4
outage is retried (`ontology.retry_unresolved_labels`).

## Dependencies

- `PBKFAIRModel` — the simulation engine, a package at the repository root.
  `helpers.py` adds the repo root to `sys.path` if it is not already
  importable.
- `requests` — used by `ontology.py` for OLS4 label lookups. Declared in both
  `plugin.py`'s `required_packages` and `requirements.txt`; it happens to also
  be a core dependency of `backend/requirements.txt`, but plugin-owned imports
  must be declared here regardless so the loader can verify the install and
  skip-mount cleanly if it's ever missing.

## Environment variables

None.

## RBAC

- `admin` — all runs/artifacts.
- `curator` — creates and owns parameter sets, runs, artifacts.
- `accessor` — reads own runs/artifacts only (no cross-user grants in the PoC).
- `visualizer` — reaches only the open routes (`/ui`, `/run`, `/scenarios`,
  parameter-set catalog); never row-level run/artifact data.

Row-level ownership is enforced by `assert_can_read_run` / `assert_can_modify_run`
in `helpers.py` (load-bearing on the Flask path — see the RLS note below).

## Schema & storage

- `sql/001_schema.sql` — tables + RLS policies, applied by the plugin loader at
  boot. Idempotent.
- `sql/002_catalogue.sql` — `_fd.pbpk_models` (catalogue), `_fd.pbpk_thresholds`
  (regulatory thresholds), and the `study_slug`/`compound`/`engine`/
  `content_hash` columns on `_fd.pbpk_simulation_runs`, including the EFSA
  2020 group-TWI seed values. Applied idempotently by the plugin loader.
- `sql/003_ontology.sql` — `_fd.pbpk_iri_labels` (OLS4 label cache) and
  `_fd.pbpk_cv_terms` (per-study SBML CV-term inventory). Populated by the
  out-of-band `scripts/seed_ontology.py` step, not at boot.
- `sql/pbpk_storage_policies.sql` — `storage.objects` RLS for the
  `pbpk-artifacts` bucket. **NOT** auto-applied; apply out of band via the
  Supabase dashboard / admin SQL. Until then only the service-role backend can
  read/write the bucket, which is fine since the backend mediates every request
  and issues the signed URLs.
- The `pbpk-artifacts` bucket itself is declared in `plugin.py` and created by
  the loader's `bootstrap_plugin_buckets`.

RLS in `001_schema.sql` is defense-in-depth: the Flask app connects as a
Postgres superuser and bypasses RLS, so the handler-level checks in `helpers.py`
are load-bearing on the web path.

## Dependencies

Plugin-specific Python deps live in `requirements.txt` next to this README
(`scipy`, `python-libsbml`). They are installed at image build time by the
project `Dockerfile`; for venv development run
`./scripts/install-plugin-deps.sh` from the repo root after the standard
`pip install -r backend/requirements.txt`. The shared core requirements file
is passed to pip as a `--constraint` so plugin installs cannot drift shared
versions (numpy, pandas, supabase, ...).

The manifest declares `required_packages=["scipy", "libsbml"]` (import names,
not pip names — `python-libsbml` imports as `libsbml`). The loader uses
`importlib.util.find_spec` at boot and skip-mounts the plugin with a warning
if any are missing, so the rest of the app still starts.

## Bundled FAIR study models (`studies/`)

In addition to the lifetime simulation surface above, the plugin ships four
canonical PBPK study models packaged as a read-only catalog under
`/model/studies/<slug>/`:

| Slug      | Source                              | Scenarios | Compounds |
|-----------|-------------------------------------|-----------|-----------|
| `ratier`  | Ratier 2024 (lifetime PFAS)         | yes       | no        |
| `rovira`  | Rovira 2019 (PFAS)                  | no        | yes       |
| `verner`  | Ouidir 2025 / Verner (PFAS)         | no        | yes       |
| `generic` | Generic PFAS PBPK                   | yes       | yes       |

Each study lives in `studies/<slug>/` as `runner.py` + its SBML XML +
`parameters.csv`. The registry in `studies/__init__.py` maps slug → module and
loads the runner **lazily** — `libsbml`/`scipy` are only imported the first
time a study endpoint is hit, so plugin discovery and the rest of pbpk keep
working without them.

Endpoints (mounted by `study_routes.register(routes)` in `routes.py`):

- `GET  /model/studies` — list available studies.
- `GET  /model/studies/<slug>/ui` — render the study's interactive page.
- `POST /model/studies/<slug>/run` — execute one scenario; returns timeseries
  + summary JSON. Missing optional deps → `503`.
- `GET  /model/studies/<slug>/scenarios` — scenario metadata (empty for
  compound-only studies).
- `GET  /model/studies/<slug>/compounds` — compound metadata (empty for
  scenario-only studies).

Templates live under `templates/pbpk/studies/<slug>.html` and extend
`dashboard/layout.html`. Every pbpk page (lifetime + each study) includes
`templates/pbpk/_studies_tabs.html` near the top — that partial is the
in-plugin tab strip the convention asks for (see `_template/README.md`). It
is driven by `plugin_studies` (injected via a blueprint-scoped
`context_processor` in `routes.py`) and `pbpk_active_tab` (set per-route).
Adding a new study = drop a subpackage in `studies/<new>/`, add a row to
`STUDIES`, add the template, and include the partial.

Sourced from PR #17 (the `PBKFAIR/` tree); the original src-blueprint layout
was refolded into this plugin contract.

## Tests

`tests/` — RBAC, parameter-set, run, artifact, and stress coverage. Picked up by
the project pytest (`testpaths = tests plugins`). `conftest.py` imports the
shared app/auth fixtures from the project `tests/conftest.py`.

## FAIR / GDPR notes

- Every resource table carries `id`, `owner_id`, `created_at`.
- `DELETE /model/artifacts/<id>` provides right-to-erasure (blob + catalog row).
- **Known gap vs guide §7:** mutations do not yet call `kernel.audit.record`.
  See the migration plan Phase 4 follow-up.
