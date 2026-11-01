-- Kernel-owned DP epsilon-budget ledger. Idempotent; applied by the plugin
-- loader at boot. Relocated from fl_schema.sql in migration plan Phase 5 —
-- the budget is consumed by core routes and by FL plugins, and the
-- metadata_tables flag below is a core column, so this is kernel, not plugin.
--
-- DEPENDENCY: the ALTER on _fd.metadata_tables near the bottom of this file
-- requires that table to exist. Core's _apply_schema (migrate_schema.sql)
-- runs BEFORE the plugin loader calls apply_plugin_schema, so the ordering
-- is correct today. If you ever reorder app.create_app(), keep core SQL
-- ahead of kernel SQL or this file will fail with "relation does not exist".

-- Per-dataset DP epsilon budget.
CREATE TABLE IF NOT EXISTS _fd.fl_epsilon_budget (
    dataset_id      INTEGER PRIMARY KEY,  -- _fd.metadata_tables.id
    total_budget    FLOAT NOT NULL DEFAULT 10.0,
    spent           FLOAT NOT NULL DEFAULT 0.0,
    last_updated    TIMESTAMPTZ DEFAULT NOW()
);

-- FL-eligible flag on the core dataset catalog.
ALTER TABLE _fd.metadata_tables
    ADD COLUMN IF NOT EXISTS fl_eligible BOOLEAN NOT NULL DEFAULT FALSE;

-- dataset_id points at _fd.metadata_tables.id, which is an integer. It used
-- to be declared UUID, so no real dataset could ever be enrolled or bound,
-- and nothing tied a budget/task to a dataset its caller owns. Convert in
-- place when the column holds no dataset ids yet; otherwise leave it and
-- say so, because converting would throw those ids away.
DO $$
BEGIN
    IF (SELECT data_type FROM information_schema.columns
         WHERE table_schema = '_fd' AND table_name = 'fl_epsilon_budget'
           AND column_name = 'dataset_id') = 'uuid' THEN
        IF EXISTS (SELECT 1 FROM _fd.fl_epsilon_budget WHERE dataset_id IS NOT NULL) THEN
            RAISE NOTICE '_fd.fl_epsilon_budget.dataset_id is UUID and holds rows; not converted';
        ELSE
            ALTER TABLE _fd.fl_epsilon_budget ALTER COLUMN dataset_id TYPE INTEGER USING NULL;
        END IF;
    END IF;
END $$;
