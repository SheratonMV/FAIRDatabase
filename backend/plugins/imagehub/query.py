"""Run one read-only SQL query as the role ``imagehub_ro``.

    python -m plugins.imagehub.query "SELECT count(*) FROM _fd.imagehub_wells"
    python -m plugins.imagehub.query --format csv --limit 1000 "<SQL>"

The database role is the real guard: it has SELECT on the imagehub tables only,
and every transaction is read-only. ``validate_sql`` adds clear errors on top.
"""
import argparse
import csv
import json
import re
import sys

import psycopg2

from kernel.env import get as env_get

DEFAULT_LIMIT = 200
MAX_LIMIT = 10000
DEFAULT_TIMEOUT = 30  # seconds

_COMMENTS_AND_STRINGS_RE = re.compile(
    r"--[^\n]*|/\*.*?\*/|'(?:[^']|'')*'|\"(?:[^\"]|\"\")*\"|\$\$.*?\$\$", re.DOTALL,
)
_FORBIDDEN_RE = re.compile(
    r"\b(INSERT|UPDATE|DELETE|MERGE|DROP|ALTER|CREATE|TRUNCATE|GRANT|REVOKE|COPY|"
    r"INTO|SET|RESET|DO|CALL|VACUUM|LOCK)\b",
    re.IGNORECASE,
)


def validate_sql(sql):
    """Return the statement without a trailing ``;``, or raise ValueError."""
    # Text in strings, comments and quoted names does not count as SQL keywords.
    bare = _COMMENTS_AND_STRINGS_RE.sub(" ", sql).strip()
    if bare.endswith(";"):
        bare = bare[:-1].rstrip()
    if not bare:
        raise ValueError("empty query")
    if ";" in bare:
        raise ValueError("only one statement is allowed")
    if not re.match(r"(SELECT|WITH)\b", bare, re.IGNORECASE):
        raise ValueError("only SELECT is allowed")
    forbidden = _FORBIDDEN_RE.search(bare)
    if forbidden:
        raise ValueError(f"{forbidden.group(1).upper()} is not allowed")
    return sql.strip().rstrip(";").rstrip()


def connect(timeout=DEFAULT_TIMEOUT):
    password = env_get("IMAGEHUB_RO_PASSWORD")
    if not password:
        raise RuntimeError(
            "IMAGEHUB_RO_PASSWORD is not set (bootstrap.sh rewrites backend/.env and "
            "drops it). See the plugin README."
        )
    conn = psycopg2.connect(
        host=env_get("POSTGRES_HOST"),
        port=env_get("POSTGRES_PORT"),
        dbname=env_get("POSTGRES_DB_NAME"),
        user="imagehub_ro",
        password=password,
        options=f"-c statement_timeout={int(timeout * 1000)} "
                "-c default_transaction_read_only=on",
    )
    conn.set_session(readonly=True)
    return conn


def run_query(conn, sql, limit=DEFAULT_LIMIT):
    """Return ``(columns, rows, truncated)``. Fetches at most ``limit`` + 1 rows."""
    statement = validate_sql(sql)
    with conn.cursor("imagehub_query") as cur:
        cur.execute(statement)
        rows = cur.fetchmany(limit + 1)
        columns = [d[0] for d in cur.description]
    return columns, rows[:limit], len(rows) > limit


def _cell(value):
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def print_table(columns, rows):
    cells = [[_cell(v).replace("\n", " ") for v in row] for row in rows]
    widths = [
        min(60, max([len(c)] + [len(r[i]) for r in cells]))
        for i, c in enumerate(columns)
    ]
    line = lambda values: " | ".join(
        v[:w].ljust(w) for v, w in zip(values, widths)
    ).rstrip()
    print(line(columns))
    print("-+-".join("-" * w for w in widths))
    for row in cells:
        print(line(row))


def main(argv=None):
    parser = argparse.ArgumentParser(description="Read-only query on the imagehub tables.")
    parser.add_argument("sql")
    parser.add_argument("--format", choices=("table", "csv"), default="table")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT,
                        help=f"maximum rows, up to {MAX_LIMIT}")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help="seconds")
    args = parser.parse_args(argv)
    limit = max(1, min(args.limit, MAX_LIMIT))
    try:
        validate_sql(args.sql)
        conn = connect(args.timeout)
        try:
            columns, rows, truncated = run_query(conn, args.sql, limit)
        finally:
            conn.close()
    except (ValueError, RuntimeError, psycopg2.Error) as exc:
        print(f"error: {str(exc).strip()}", file=sys.stderr)
        return 1
    if args.format == "csv":
        writer = csv.writer(sys.stdout)
        writer.writerow(columns)
        writer.writerows([_cell(v) for v in row] for row in rows)
    else:
        print_table(columns, rows)
    print(f"({len(rows)} rows{', cut off at the limit' if truncated else ''})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
