-- RBAC schema for FAIRDatabase.
-- Idempotent: safe to re-run on every boot. Applied after migrate_schema.sql
-- (which creates the _fd schema) and BEFORE the plugin loader runs at Flask
-- boot, because plugin-owned RLS policies (e.g. plugins/pbpk/sql/001_schema.sql)
-- call _fd.current_role() defined here.
--
-- Roles model: one role per user, drawn from {admin, curator, accessor, visualizer}.
--   - admin     : full access; manages users and grants
--   - curator   : uploads + modifies datasets they own
--   - accessor  : reads datasets explicitly granted to them
--   - visualizer: catalog + aggregate visualizations only
--
-- We deliberately do NOT add foreign keys to auth.users(id). This file is
-- applied in two contexts: (a) Postgres initdb mounts (where the auth schema
-- has not yet been provisioned by Supabase) and (b) every Flask boot via the
-- entrypoint. Omitting the FK keeps the file idempotent across both passes;
-- the auth.users trigger below is guarded by an existence check so it only
-- attaches once the auth schema is present. RLS still uses auth.uid() at
-- request time, which does not require a FK.

CREATE SCHEMA IF NOT EXISTS _fd;

-- ---------------------------------------------------------------------------
-- Role enum
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type t
                   JOIN pg_namespace n ON n.oid = t.typnamespace
                   WHERE n.nspname = '_fd' AND t.typname = 'user_role') THEN
        CREATE TYPE _fd.user_role AS ENUM
            ('admin', 'curator', 'accessor', 'visualizer');
    END IF;
END $$;

-- ---------------------------------------------------------------------------
-- user_roles : single row per user, default 'visualizer'
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS _fd.user_roles (
    user_id     uuid PRIMARY KEY,
    role        _fd.user_role NOT NULL DEFAULT 'visualizer',
    assigned_by uuid,
    assigned_at timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- role_audit : append-only history of role changes
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS _fd.role_audit (
    id         bigserial PRIMARY KEY,
    user_id    uuid NOT NULL,
    old_role   _fd.user_role,
    new_role   _fd.user_role NOT NULL,
    changed_by uuid NOT NULL,
    changed_at timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- owner_id on metadata_tables (curator who uploaded the dataset)
-- ---------------------------------------------------------------------------
ALTER TABLE _fd.metadata_tables
    ADD COLUMN IF NOT EXISTS owner_id uuid;

CREATE INDEX IF NOT EXISTS metadata_tables_owner_idx
    ON _fd.metadata_tables(owner_id);

-- ---------------------------------------------------------------------------
-- dataset_grants : explicit per-dataset read access for accessors
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS _fd.dataset_grants (
    dataset_id bigint NOT NULL
                       REFERENCES _fd.metadata_tables(id) ON DELETE CASCADE,
    user_id    uuid   NOT NULL,
    granted_by uuid   NOT NULL,
    granted_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (dataset_id, user_id)
);

CREATE TABLE IF NOT EXISTS _fd.grant_audit (
    id         bigserial PRIMARY KEY,
    dataset_id bigint NOT NULL,
    user_id    uuid   NOT NULL,
    action     text   NOT NULL CHECK (action IN ('granted', 'revoked')),
    changed_by uuid   NOT NULL,
    changed_at timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- Helper functions used by RLS policies. SECURITY DEFINER so they can read
-- _fd.user_roles even when the calling role lacks SELECT on the table.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION _fd.current_role()
RETURNS _fd.user_role
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = _fd, pg_temp
AS $$
    SELECT role FROM _fd.user_roles WHERE user_id = auth.uid();
$$;

CREATE OR REPLACE FUNCTION _fd.can_read_dataset(ds_id bigint)
RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = _fd, pg_temp
AS $$
    SELECT
        _fd.current_role() = 'admin'
        OR EXISTS (SELECT 1 FROM _fd.metadata_tables
                    WHERE id = ds_id AND owner_id = auth.uid())
        OR EXISTS (SELECT 1 FROM _fd.dataset_grants
                    WHERE dataset_id = ds_id AND user_id = auth.uid());
$$;

-- ---------------------------------------------------------------------------
-- RLS on metadata_tables
-- A direct database caller sees only catalog rows for datasets it may read
-- (admin, owner, or grantee). The full catalog for visualizers is served by
-- Flask, which connects as a superuser and is not limited by these rules.
-- Showing every row here would hand out each dataset's owner_id, which is
-- the user id needed to forge a session for that owner.
-- ---------------------------------------------------------------------------
ALTER TABLE _fd.metadata_tables ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS metadata_select ON _fd.metadata_tables;
CREATE POLICY metadata_select ON _fd.metadata_tables FOR SELECT
    USING (_fd.can_read_dataset(id));

DROP POLICY IF EXISTS metadata_insert ON _fd.metadata_tables;
CREATE POLICY metadata_insert ON _fd.metadata_tables FOR INSERT
    WITH CHECK (
        _fd.current_role() IN ('admin', 'curator')
        AND owner_id = auth.uid()
    );

DROP POLICY IF EXISTS metadata_update ON _fd.metadata_tables;
CREATE POLICY metadata_update ON _fd.metadata_tables FOR UPDATE
    USING (
        _fd.current_role() = 'admin'
        OR (_fd.current_role() = 'curator' AND owner_id = auth.uid())
    );

DROP POLICY IF EXISTS metadata_delete ON _fd.metadata_tables;
CREATE POLICY metadata_delete ON _fd.metadata_tables FOR DELETE
    USING (
        _fd.current_role() = 'admin'
        OR (_fd.current_role() = 'curator' AND owner_id = auth.uid())
    );

-- ---------------------------------------------------------------------------
-- RLS on dataset_grants
-- Admin or owning curator can manage; users can see their own grants.
-- ---------------------------------------------------------------------------
ALTER TABLE _fd.dataset_grants ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS grants_select ON _fd.dataset_grants;
CREATE POLICY grants_select ON _fd.dataset_grants FOR SELECT
    USING (
        _fd.current_role() = 'admin'
        OR user_id = auth.uid()
        OR EXISTS (SELECT 1 FROM _fd.metadata_tables m
                   WHERE m.id = dataset_id AND m.owner_id = auth.uid())
    );

DROP POLICY IF EXISTS grants_write ON _fd.dataset_grants;
CREATE POLICY grants_write ON _fd.dataset_grants FOR ALL
    USING (
        _fd.current_role() = 'admin'
        OR EXISTS (SELECT 1 FROM _fd.metadata_tables m
                   WHERE m.id = dataset_id AND m.owner_id = auth.uid())
    )
    WITH CHECK (
        _fd.current_role() = 'admin'
        OR EXISTS (SELECT 1 FROM _fd.metadata_tables m
                   WHERE m.id = dataset_id AND m.owner_id = auth.uid())
    );

-- ---------------------------------------------------------------------------
-- user_roles : the row owner can read their own role; admin reads all.
-- Writes are gated to admin only (the app uses service_role for the trigger
-- path and admin console, so this policy is the user-path safety net).
-- ---------------------------------------------------------------------------
ALTER TABLE _fd.user_roles ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS user_roles_select ON _fd.user_roles;
CREATE POLICY user_roles_select ON _fd.user_roles FOR SELECT
    USING (user_id = auth.uid() OR _fd.current_role() = 'admin');

DROP POLICY IF EXISTS user_roles_write ON _fd.user_roles;
CREATE POLICY user_roles_write ON _fd.user_roles FOR ALL
    USING (_fd.current_role() = 'admin')
    WITH CHECK (_fd.current_role() = 'admin');

-- ---------------------------------------------------------------------------
-- Grants for 'anon' / 'authenticated' on _fd live in fd_lockdown.sql, which
-- runs after the kernel and plugin SQL so it covers their tables too.
-- ---------------------------------------------------------------------------

-- ---------------------------------------------------------------------------
-- Auto-assign 'visualizer' role on new auth.users insertion.
-- Only created if the auth schema is present (i.e. running on a Supabase DB).
-- On the initdb pass auth.users may not exist yet; the entrypoint re-run at
-- Flask boot will install the trigger once Supabase has finished setup.
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'auth' AND table_name = 'users') THEN

        CREATE OR REPLACE FUNCTION _fd.handle_new_auth_user()
        RETURNS trigger
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = _fd, pg_temp
        AS $fn$
        BEGIN
            INSERT INTO _fd.user_roles (user_id, role)
            VALUES (NEW.id, 'visualizer')
            ON CONFLICT (user_id) DO NOTHING;
            RETURN NEW;
        END;
        $fn$;

        DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
        CREATE TRIGGER on_auth_user_created
            AFTER INSERT ON auth.users
            FOR EACH ROW EXECUTE FUNCTION _fd.handle_new_auth_user();
    END IF;
END $$;
