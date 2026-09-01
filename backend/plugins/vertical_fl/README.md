# Vertical FL plugin

Differentially-private vertical federated learning with multi-heterogeneous-task support.
Implements split learning with LSTM bottom models (one per party), an MMoE top model,
task-stratified Gaussian DP on embedding gradients, and Rényi DP accounting per task.

## What it does

- **Tasks** (`_fd.vfl_tasks`) — a VFL training job: number of parties, task types,
  per-task DP noise multipliers, model architecture (stored as `model_arch` JSONB).
- **Party registration** (`_fd.vfl_parties`) — each data-holding site registers its
  `site_id`, `feature_dim`, and `feature_names`. All dataset-specific config lives
  here and in `model_arch`, never hardcoded in the engine.
- **PSI** (`_fd.vfl_psi`) — parties submit SHA-256-hashed patient IDs; the server
  computes the hash-set intersection once all parties have submitted and stores the
  aligned cohort size on `vfl_tasks`. Honest-but-curious threat model.
- **Embedding submission + aggregation** — each party POSTs its LSTM-encoded
  embedding slice for a round; when all `n_parties` have submitted, the server
  concatenates them, runs the top-model forward + backward pass, applies
  clip-and-Gaussian DP noise to the resulting gradient, and slices it back into
  per-party chunks. Raw embeddings are purged from the DB immediately after
  gradient dispatch.
- **Gradient retrieval** — parties GET their DP-noised gradient slice and update
  their local encoder. Gradients are not persisted; parties must fetch within the
  same round window.
- **Simulation** — runs all FL rounds in-process against a synthetic
  Dirichlet-partitioned dataset. Supports domain-aware feature partitioning
  via `feature_groups` in `model_arch`.
- **Export** — task config + per-round loss and ε-per-task log as JSON; raw
  embeddings are stripped before export.

Mounted at `url_prefix=/vfl`. The dashboard UI is at `/fl/ui` (Vertical FL tab
in the horizontal FL dashboard — no separate `/vfl/ui` route).

## Dependencies

- **torch** — OPTIONAL. Only `POST /vfl/tasks/<id>/simulate` and
  `POST /vfl/tasks/<id>/rounds/<n>/embeddings` need it; the import is lazy
  (`engine.py` is imported inside those handlers). Task CRUD, party registration,
  PSI, and the UI all work without torch installed.
- **numpy** — used in the embedding/gradient routes and simulation; available in
  the core `requirements.txt`.

## Kernel surface used

- `kernel.auth` — `@login_required(...)` on all routes; `g.user` and `g.role`
  for ownership checks and admin bypass.
- `kernel.rdp_accountant` — `compute_epsilon_spent` called by
  `engine.renyi_epsilon_per_task` to convert per-task noise multiplier + rounds
  into (ε, δ)-DP.
- `kernel.dp_budget` — `get_epsilon_budget` and `consume_epsilon_guarded` charge
  the shared per-dataset ε ledger on every round of `submit_embeddings` and
  `run_simulation`; `create_task` rejects a `dataset_id` with no budget row.

## Cross-plugin hand-off

None. VFL does not call other plugins' HTTP APIs. The UI is co-hosted in the
horizontal FL dashboard (`/fl/ui`) via a shared template.

## Schema

- `sql/001_schema.sql` — `_fd.vfl_tasks`, `_fd.vfl_parties`, `_fd.vfl_psi`,
  `_fd.vfl_rounds`. Applied by the plugin loader. Idempotent.
- `vfl_rounds.embeddings` (JSONB) holds intermediate embeddings per round; nulled
  by `purge_round_embeddings` after gradient dispatch.

## RBAC

Per-task ownership: admins see and act on any task; all other roles only see tasks
they created. Mutation routes (`POST`) require `admin` or `curator`. Read routes
and model/export endpoints are open to any authenticated user.

## Tests

`tests/` — engine unit tests (`test_engine.py`: `SiteEncoder` shape, MMoE forward,
`split_backward` gradient shapes, DP noise variance, `renyi_epsilon_per_task`
budget), integration tests (`test_vfl_integration.py`: 10-round simulation end-to-end),
and route tests (`test_routes.py`: DB-dependent tests marked `skip` until services
are up). Picked up by the project pytest. `conftest.py` imports shared app/auth
fixtures from the project `tests/conftest.py`.

## Threat model

Patient alignment uses SHA-256-hashed ID-set intersection, consistent with the
honest-but-curious threat model. The server sees only hashes, never raw IDs.
Production deployments across real institutions should replace this with a
circuit-based PSI protocol for cryptographic guarantees against a malicious
coordinator.

## FAIR / GDPR notes

- Raw embeddings are purged from `_fd.vfl_rounds.embeddings` after gradient dispatch;
  they never persist past a single round.
- Gradient slices are not stored; parties must retrieve them before the next round.
- PSI operates on SHA-256 hashes; the server never receives raw patient IDs.
- DP epsilon is tracked per task via `renyi_epsilon_per_task`; per-round ε is
  stored in `vfl_rounds.epsilon_per_task` for audit. The per-dataset total is
  charged to `kernel.dp_budget` each round.
- **Known gap:** mutations do not yet call `kernel.audit.record`.
