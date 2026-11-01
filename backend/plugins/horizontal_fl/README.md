# Horizontal FL plugin

Differentially-private horizontal federated learning (DP-FedProx / FedAvg).
Migrated from `src/federated/` in Phase 5 of the plugin migration (see
`docs/PLUGIN_MIGRATION_PLAN.md`).

## What it does

- **Tasks** (`_fd.fl_tasks`) — a federated training job: algorithm, round
  count, DP parameters, model architecture.
- **Rounds** (`_fd.fl_rounds`, `_fd.fl_round_submissions`) — per-round client
  submissions, aggregated weights, ε spent.
- **Gradient submission** — clients POST AES-256-GCM-encrypted weight updates;
  the server decrypts in memory, clips to L2 norm, adds Gaussian DP noise, and
  aggregates. Raw gradients never touch disk.
- **Simulation** — runs all FL rounds in-process against a synthetic
  Dirichlet-partitioned dataset.
- **Export** — task config / round log as JSON or CSV; final weights can be
  exported into a PBPK parameter set.

Mounted at `url_prefix=/fl`. The dashboard UI is at `/fl/ui` (was
`/federated/ui` before the migration; core keeps a legacy redirect).

## Dependencies

- **torch** — OPTIONAL. Only `POST /fl/tasks/<id>/simulate` needs it; the
  import is lazy (`engine.py` is imported inside that handler). Task CRUD,
  gradient submission, and the UI all work without torch installed.

## Kernel surface used

- `kernel.crypto` — `decrypt_weights` (AES-256-GCM; resolves the app
  `SECRET_KEY` internally, so the plugin never handles the core secret).
- `kernel.privacy` — `compute_noise_multiplier`, `compute_epsilon_spent`,
  `clip_gradients`, `add_gaussian_noise_dp`.
- `kernel.dp_budget` — per-dataset DP epsilon-budget ledger. This is kernel,
  not plugin-owned: core routes also consume it and it writes a core table.

## Cross-plugin hand-off

`POST /fl/tasks/<id>/export-params` writes a PBPK parameter set by calling the
PBPK plugin's HTTP API (`POST /model/parameter-sets`), forwarding the caller's
session cookie — never by importing PBPK code (guide §3). The target is
`FAIRDB_INTERNAL_URL` (default `http://127.0.0.1:5000`), not the request's
`Host` header, so a client cannot redirect the forwarded cookies elsewhere.

## Schema

- `sql/001_schema.sql` — `_fd.fl_tasks`, `fl_rounds`, `fl_clients`,
  `fl_round_submissions`. Applied by the plugin loader. Idempotent.
- The DP budget table (`_fd.fl_epsilon_budget`) and `metadata_tables.fl_eligible`
  are kernel-owned (`kernel/sql/002_dp_budget.sql`), not here.

## RBAC

Per-task ownership: admins see/act on any task; everyone else only on tasks
they created (no cross-user grant table for FL). Task mutations require
`admin`/`curator`; reads and the UI are open to any authenticated user.

## Tests

`tests/` — crypto, engine, RDP accountant, route, and integration coverage.
Picked up by the project pytest. `conftest.py` imports the shared app/auth
fixtures from the project `tests/conftest.py`.

## FAIR / GDPR notes

- Raw gradients are decrypted in memory only, never persisted.
- `purge_round_weights` clears aggregated weights after export.
- DP epsilon budget is enforced per dataset via `kernel.dp_budget`.
- **Known gap vs guide §7:** mutations do not yet call `kernel.audit.record`.
