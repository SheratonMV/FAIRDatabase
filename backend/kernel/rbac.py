"""Role / ownership checks for plugin routes. See ``docs/PLUGIN_GUIDE.md`` §2.

Re-exports the dataset-level guards from the core dashboard helpers and adds
``assert_owns`` for a plugin's own ``_fd.<plugin>_*`` rows.
"""
from flask import g
from psycopg2 import sql

from src.dashboard.helpers import (
    assert_can_modify_dataset,
    assert_can_modify_table,
    assert_can_read_table,
    filter_owned_tables,
    filter_readable_tables,
)

__all__ = [
    "assert_can_read_table",
    "assert_can_modify_table",
    "assert_can_modify_dataset",
    "filter_readable_tables",
    "filter_owned_tables",
    "assert_owns",
]


def assert_owns(cur, table, id_col, row_id):
    """Raise unless the current user owns row ``row_id`` of ``table``.

    ``table`` is a physical, optionally schema-qualified table name, e.g.
    ``"_fd.myplugin_runs"``; it must have an ``owner_id uuid`` column.
    ``cur`` is an open psycopg2 cursor.

    Admins bypass the ownership check. Raises ``FileNotFoundError`` if the row
    does not exist, ``PermissionError`` if it exists but belongs to another
    user. Reads ``g.user`` / ``g.role`` — call inside a request handler.
    """
    parts = [p for p in table.split(".") if p]
    table_ident = sql.SQL(".").join(sql.Identifier(p) for p in parts)
    query = sql.SQL("SELECT owner_id FROM {tbl} WHERE {col} = %s").format(
        tbl=table_ident,
        col=sql.Identifier(id_col),
    )
    cur.execute(query, (row_id,))
    row = cur.fetchone()
    if row is None:
        raise FileNotFoundError(f"{table} row {row_id} not found")
    if getattr(g, "role", None) == "admin":
        return
    if str(row[0]) != str(getattr(g, "user", None)):
        raise PermissionError("forbidden")
