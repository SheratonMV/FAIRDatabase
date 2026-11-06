-- Read-only role for query.py: SELECT on the imagehub tables, nothing else.
-- No password here. `flask imagehub setup-query-role` enables login.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'imagehub_ro') THEN
        CREATE ROLE imagehub_ro NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
    END IF;
END $$;

ALTER ROLE imagehub_ro SET default_transaction_read_only = on;
ALTER ROLE imagehub_ro SET statement_timeout = '60s';

GRANT USAGE ON SCHEMA _fd TO imagehub_ro;

-- fd_lockdown.sql switches row rules on for every _fd table at each boot, so
-- this role sees no rows without its own policy.
DO $$
DECLARE t text;
BEGIN
    FOREACH t IN ARRAY ARRAY['wells', 'images', 'annotations', 'legends', 'exports'] LOOP
        EXECUTE format('GRANT SELECT ON _fd.imagehub_%s TO imagehub_ro', t);
        EXECUTE format('DROP POLICY IF EXISTS imagehub_%s_ro ON _fd.imagehub_%s', t, t);
        EXECUTE format(
            'CREATE POLICY imagehub_%s_ro ON _fd.imagehub_%s FOR SELECT TO imagehub_ro USING (true)',
            t, t
        );
    END LOOP;
END $$;
