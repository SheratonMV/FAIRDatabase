-- Vertical FL plugin schema. Idempotent — re-running this file must be a no-op.
-- Only ever touch tables prefixed with your plugin name: `_fd.vfl_*`.

CREATE TABLE IF NOT EXISTS _fd.vfl_tasks (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    status          TEXT NOT NULL DEFAULT 'pending',
    psi_status      TEXT NOT NULL DEFAULT 'pending',
    psi_cohort_size INT,
    n_parties       INT NOT NULL DEFAULT 3,
    n_tasks         INT NOT NULL DEFAULT 1,
    task_types      JSONB NOT NULL DEFAULT '["binary"]'::jsonb,
    task_sigma      JSONB NOT NULL DEFAULT '{}'::jsonb,
    dp_epsilon      FLOAT NOT NULL,
    dp_delta        FLOAT NOT NULL DEFAULT 1e-5,
    dp_clip_norm    FLOAT NOT NULL DEFAULT 1.0,
    rounds_total    INT NOT NULL DEFAULT 10,
    rounds_done     INT NOT NULL DEFAULT 0,
    simulation      BOOLEAN NOT NULL DEFAULT FALSE,
    sim_n_clients   INT NOT NULL DEFAULT 3,
    sim_alpha       FLOAT NOT NULL DEFAULT 0.5,
    model_arch      JSONB NOT NULL DEFAULT '{}'::jsonb,
    dataset_id      UUID,
    created_by      UUID,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS _fd.vfl_parties (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id         UUID NOT NULL REFERENCES _fd.vfl_tasks(id) ON DELETE CASCADE,
    site_id         TEXT NOT NULL,
    feature_dim     INT NOT NULL,
    feature_names   JSONB NOT NULL DEFAULT '[]'::jsonb,
    registered_at   TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (task_id, site_id)
);

-- Each party submits SHA-256-hashed patient IDs. The server computes the
-- intersection once all n_parties have submitted and stores cohort_size on
-- vfl_tasks. Honest-but-curious threat model; see README.md.
CREATE TABLE IF NOT EXISTS _fd.vfl_psi (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id         UUID NOT NULL REFERENCES _fd.vfl_tasks(id) ON DELETE CASCADE,
    site_id         TEXT NOT NULL,
    hashed_ids      JSONB NOT NULL DEFAULT '[]'::jsonb,
    submitted_at    TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (task_id, site_id)
);

-- Aggregation triggers when embeddings_received == n_parties (synchronous).
-- Raw embeddings are purged after gradient dispatch (privacy hygiene).
CREATE TABLE IF NOT EXISTS _fd.vfl_rounds (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id             UUID NOT NULL REFERENCES _fd.vfl_tasks(id) ON DELETE CASCADE,
    round_n             INT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'open',
    embeddings_received INT NOT NULL DEFAULT 0,
    embeddings          JSONB,
    top_model_weights   JSONB,
    loss_per_task       JSONB,
    epsilon_per_task    JSONB,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (task_id, round_n)
);

-- Per-party gradient slices for a round, keyed by site_id. Consumed on first
-- GET (see db.consume_gradient).
ALTER TABLE _fd.vfl_rounds ADD COLUMN IF NOT EXISTS gradients JSONB;

CREATE INDEX IF NOT EXISTS vfl_parties_task_idx ON _fd.vfl_parties (task_id);
CREATE INDEX IF NOT EXISTS vfl_psi_task_idx     ON _fd.vfl_psi     (task_id);
CREATE INDEX IF NOT EXISTS vfl_rounds_task_idx  ON _fd.vfl_rounds  (task_id);
