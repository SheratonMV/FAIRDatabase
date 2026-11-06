"""query.py: the SQL check, and what the role can and cannot reach."""
import os

import psycopg2
import pytest

from plugins.imagehub.query import connect, run_query, validate_sql

needs_role = pytest.mark.skipif(
    not os.getenv("IMAGEHUB_RO_PASSWORD"), reason="IMAGEHUB_RO_PASSWORD is not set",
)


@pytest.mark.parametrize("sql", [
    "SELECT 1",
    "select 1;",
    "  WITH a AS (SELECT 1) SELECT * FROM a",
    "SELECT 'DROP TABLE x; DELETE' AS text",
    "SELECT props ->> 'Viability (%)' FROM _fd.imagehub_wells -- DELETE;\n",
    'SELECT "update" FROM t',
])
def test_validate_accepts(sql):
    assert validate_sql(sql)


@pytest.mark.parametrize("sql", [
    "",
    "-- only a comment",
    "DROP TABLE _fd.imagehub_wells",
    "DELETE FROM _fd.imagehub_wells",
    "SELECT 1; DROP TABLE _fd.imagehub_wells",
    "WITH d AS (DELETE FROM t RETURNING *) SELECT * FROM d",
    "SELECT * INTO x FROM t",
    "SET ROLE postgres",
    "EXPLAIN SELECT 1",
    "SELECT 1 /* a */; /* b */ SELECT 2",
])
def test_validate_rejects(sql):
    with pytest.raises(ValueError):
        validate_sql(sql)


@pytest.fixture
def conn():
    connection = connect()
    yield connection
    connection.close()


@needs_role
def test_role_reads_imagehub_tables(conn):
    for table in ("wells", "images", "annotations", "legends", "exports"):
        columns, rows, _ = run_query(conn, f"SELECT count(*) AS n FROM _fd.imagehub_{table}")
        assert columns == ["n"] and rows[0][0] >= 0
        conn.rollback()


@needs_role
def test_limit_cuts_off_and_reports_it(conn):
    _, rows, truncated = run_query(conn, "SELECT generate_series(1, 10)", limit=3)
    assert len(rows) == 3 and truncated is True
    conn.rollback()
    _, rows, truncated = run_query(conn, "SELECT generate_series(1, 3)", limit=3)
    assert len(rows) == 3 and truncated is False


@needs_role
@pytest.mark.parametrize("table", [
    "auth.users",
    "_fd.user_roles",
    "_fd.plugin_audit",
    "_fd.metadata_tables",
    "_fd.pbpk_simulation_runs",
    "storage.objects",
])
def test_role_cannot_read_other_tables(conn, table):
    with pytest.raises(psycopg2.errors.InsufficientPrivilege):
        run_query(conn, f"SELECT * FROM {table} LIMIT 1")


@needs_role
@pytest.mark.parametrize("statement", [
    "DELETE FROM _fd.imagehub_wells",
    "SET ROLE postgres",
    "CREATE TABLE _fd.imagehub_x (a int)",
])
def test_role_cannot_write_when_the_check_is_bypassed(conn, statement):
    with conn.cursor() as cur, pytest.raises(psycopg2.Error):
        cur.execute(statement)
        conn.commit()
        if statement.startswith("SET"):
            cur.execute("DELETE FROM _fd.imagehub_wells")


@needs_role
def test_timeout_stops_a_long_query():
    connection = connect(timeout=0.2)
    try:
        with pytest.raises(psycopg2.errors.QueryCanceled):
            run_query(connection, "SELECT pg_sleep(5)")
    finally:
        connection.close()
