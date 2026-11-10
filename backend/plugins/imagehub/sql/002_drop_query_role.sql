-- Removes the read-only role imagehub_ro that earlier versions created here, with
-- its policies and grants. Idempotent; no table, column or row is touched.
DO $$
DECLARE t text;
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'imagehub_ro') THEN
        FOREACH t IN ARRAY ARRAY['wells', 'images', 'annotations', 'legends', 'exports'] LOOP
            EXECUTE format('DROP POLICY IF EXISTS imagehub_%s_ro ON _fd.imagehub_%s', t, t);
            EXECUTE format('REVOKE ALL ON _fd.imagehub_%s FROM imagehub_ro', t);
        END LOOP;
        REVOKE ALL ON SCHEMA _fd FROM imagehub_ro;
        DROP ROLE imagehub_ro;
    END IF;
END $$;
