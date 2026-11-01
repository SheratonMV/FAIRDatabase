-- Applied by app._apply_schema after kernel + plugin SQL (see create_app).

-- ---------------------------------------------------------------------------
-- What a non-superuser database caller may touch in _fd (deny by default).
--
-- Flask and the edge functions connect as roles that skip row rules
-- (superuser or BYPASSRLS), so none of this limits them. It limits everyone else: chiefly a logged-in user talking to the
-- database directly through the Supabase REST gateway with their own token.
-- An earlier version granted the 'authenticated' role read/write on EVERY
-- _fd table, including tables with no row rules (sample metadata, FL weights
-- and privacy budget, audit logs), so any signed-up user could read and
-- rewrite them. Now:
--   1. take back every grant 'anon' and 'authenticated' hold in _fd, and stop
--      new tables inheriting grants automatically;
--   2. grant back only the tables whose row rules are in rbac_schema.sql
--      (per-dataset tables get theirs when they are created, see
--      src/dashboard/helpers.py);
--   3. switch row rules on for every _fd table, so a table with no rules
--      shows no rows to a non-superuser even if someone grants it later by
--      mistake. Tables created while the app runs (uploads, generalisation
--      output) get no grants (step 1), so they are closed until the next
--      boot switches their rules on too.
-- The app's 'postgres' role has BYPASSRLS, so Flask is unaffected. Supabase
-- Realtime keeps its bookkeeping tables in _fd but connects as
-- supabase_admin (superuser), so it is unaffected as well.
-- The role checks make this a no-op on plain Postgres (no Supabase roles).
-- ---------------------------------------------------------------------------
DO $$
DECLARE r text;
BEGIN
    FOREACH r IN ARRAY ARRAY['anon', 'authenticated'] LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
            EXECUTE format('REVOKE ALL ON ALL TABLES IN SCHEMA _fd FROM %I', r);
            EXECUTE format('REVOKE ALL ON ALL SEQUENCES IN SCHEMA _fd FROM %I', r);
            EXECUTE format('ALTER DEFAULT PRIVILEGES IN SCHEMA _fd REVOKE ALL ON TABLES FROM %I', r);
            EXECUTE format('ALTER DEFAULT PRIVILEGES IN SCHEMA _fd REVOKE ALL ON SEQUENCES FROM %I', r);
        END IF;
    END LOOP;

    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
        GRANT USAGE ON SCHEMA _fd TO authenticated;
        GRANT SELECT, INSERT, UPDATE, DELETE ON _fd.metadata_tables TO authenticated;
        GRANT SELECT, INSERT, UPDATE, DELETE ON _fd.dataset_grants  TO authenticated;
        GRANT SELECT ON _fd.user_roles TO authenticated;
        -- Per-dataset tables carry their own row rules (see helpers.py).
        FOR r IN
            SELECT m.table_name FROM _fd.metadata_tables m
              JOIN pg_class c ON c.relname = m.table_name
              JOIN pg_namespace n ON n.oid = c.relnamespace AND n.nspname = '_fd'
        LOOP
            EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON _fd.%I TO authenticated', r);
        END LOOP;
    END IF;
END $$;

DO $$
DECLARE t record;
BEGIN
    FOR t IN
        SELECT c.relname
          FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
         WHERE n.nspname = '_fd' AND c.relkind IN ('r', 'p')
           AND NOT c.relrowsecurity
    LOOP
        -- Only the table owner may do this; skip (with a notice) rather than
        -- roll back the whole file if some table belongs to another role.
        BEGIN
            EXECUTE format('ALTER TABLE _fd.%I ENABLE ROW LEVEL SECURITY', t.relname);
        EXCEPTION WHEN insufficient_privilege THEN
            RAISE NOTICE 'RLS not enabled on _fd.%: not owner', t.relname;
        END;
    END LOOP;
END $$;
