"""Utilities for saving, chunking, and importing CSV data into PostgreSQL.

KERNEL CONTRACT: ``filter_owned_tables``, ``filter_readable_tables``,
``assert_can_read_table`` and ``assert_can_modify_table`` are re-exported by
``kernel.rbac`` and consumed by plugins. Their signatures and semantics are a
public contract — do not rename, reorder arguments, or change their raised
exception types without bumping the kernel surface and migrating callers under
``backend/plugins/``.
"""

from hashlib import sha256
from werkzeug.utils import secure_filename
from flask import current_app
from psycopg2 import sql

import secrets
import time
import os
import csv


def _clean_identifier(name):
    """Strip everything except alphanumerics and underscores."""
    return "".join(c for c in name if c.isalnum() or c == "_")


def filter_owned_tables(cur, tables, user_id, role):
    """Restrict ``tables`` to those owned by ``user_id`` for non-admin callers.

    ``tables`` is an iterable of physical table names in the ``_fd`` schema.
    Admins keep the full list. Curators get only tables whose
    ``metadata_tables.owner_id`` matches their uuid. Other roles get nothing.
    """
    if role == "admin":
        return list(tables)
    if role != "curator" or not user_id:
        return []
    tables = list(tables)
    if not tables:
        return []
    cur.execute(
        "SELECT table_name FROM _fd.metadata_tables "
        "WHERE owner_id = %s AND table_name = ANY(%s)",
        (user_id, tables),
    )
    return [row[0] for row in cur.fetchall()]


def assert_can_modify_table(cur, table_name, user_id, role):
    """Raise PermissionError unless the caller may mutate ``table_name``.

    Admins always pass. Curators pass only when they own the dataset.
    """
    if role == "admin":
        return
    if role != "curator" or not user_id:
        raise PermissionError("forbidden")
    cur.execute(
        "SELECT 1 FROM _fd.metadata_tables "
        "WHERE table_name = %s AND owner_id = %s LIMIT 1",
        (table_name, user_id),
    )
    if cur.fetchone() is None:
        raise PermissionError("forbidden")


def assert_can_modify_dataset(cur, dataset_id, user_id, role):
    """Same rule as ``assert_can_modify_table`` but keyed by
    ``metadata_tables.id``, which is what the FL routes receive.

    Raises ``ValueError`` for an id that is not an integer and
    ``PermissionError`` when the dataset is missing or not the caller's, so
    a refused id and an unknown id look the same to the caller.
    """
    try:
        ds_id = int(dataset_id)
    except (TypeError, ValueError):
        raise ValueError("dataset_id must be an integer")
    if role not in ("admin", "curator") or not user_id:
        raise PermissionError("forbidden")
    cur.execute("SELECT owner_id FROM _fd.metadata_tables WHERE id = %s", (ds_id,))
    row = cur.fetchone()
    if row is None:
        raise PermissionError("forbidden")
    if role != "admin" and str(row[0]) != str(user_id):
        raise PermissionError("forbidden")


def filter_readable_tables(cur, tables, user_id, role):
    """Restrict ``tables`` to those the caller is allowed to read row-level.

    - admin           : everything in the input list
    - curator         : tables they own
    - accessor        : tables they own OR have an explicit dataset_grants row for
    - visualizer/none : nothing (visualizers go through aggregate viz endpoints)
    """
    if role == "admin":
        return list(tables)
    if not user_id:
        return []
    tables = list(tables)
    if not tables:
        return []
    if role == "curator":
        cur.execute(
            "SELECT table_name FROM _fd.metadata_tables "
            "WHERE owner_id = %s AND table_name = ANY(%s)",
            (user_id, tables),
        )
        return [row[0] for row in cur.fetchall()]
    if role == "accessor":
        cur.execute(
            "SELECT m.table_name FROM _fd.metadata_tables m "
            "WHERE m.table_name = ANY(%s) AND ("
            "   m.owner_id = %s "
            "   OR EXISTS (SELECT 1 FROM _fd.dataset_grants g "
            "              WHERE g.dataset_id = m.id AND g.user_id = %s))",
            (tables, user_id, user_id),
        )
        return [row[0] for row in cur.fetchall()]
    return []


def assert_can_read_table(cur, table_name, user_id, role):
    """Raise PermissionError unless the caller may read ``table_name``.

    Mirrors ``filter_readable_tables`` for single-table entry points.
    """
    if role == "admin":
        return
    if not user_id or role not in ("curator", "accessor"):
        raise PermissionError("forbidden")
    if role == "curator":
        cur.execute(
            "SELECT 1 FROM _fd.metadata_tables "
            "WHERE table_name = %s AND owner_id = %s LIMIT 1",
            (table_name, user_id),
        )
    else:  # accessor
        cur.execute(
            "SELECT 1 FROM _fd.metadata_tables m "
            "WHERE m.table_name = %s AND ("
            "  m.owner_id = %s "
            "  OR EXISTS (SELECT 1 FROM _fd.dataset_grants g "
            "             WHERE g.dataset_id = m.id AND g.user_id = %s)) "
            "LIMIT 1",
            (table_name, user_id, user_id),
        )
    if cur.fetchone() is None:
        raise PermissionError("forbidden")


def pg_ensure_schema_and_metadata(cur, schema):
    """
    Ensure PostgreSQL schema and metadata table exist.
    ---
    tags:
      - database
    summary: Create _fd schema and metadata table if missing.
    parameters:
      - name: cur
        in: code
        type: psycopg2.extensions.cursor
        required: true
        description: PostgreSQL cursor for executing commands.
    """
    clean_schema = f"_{_clean_identifier(schema)}"
    schema_id = sql.Identifier(clean_schema)
    cur.execute(
        sql.SQL("CREATE SCHEMA IF NOT EXISTS {};").format(schema_id)
    )

    # Check existence before CREATE to avoid permission errors on tables
    # owned by the migration user (e.g. supabase_admin) when the app
    # connects as a non-owner role that has CREATE on the schema but not
    # ownership of existing tables.
    cur.execute(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_schema = %s AND table_name = 'metadata_tables'",
        (clean_schema,),
    )
    if cur.fetchone() is None:
        cur.execute(
            sql.SQL("""
            CREATE TABLE {schema}.metadata_tables (
                id SERIAL PRIMARY KEY,
                table_name TEXT NOT NULL,
                main_table TEXT NOT NULL,
                description TEXT,
                origin TEXT,
                owner_id uuid,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """).format(schema=schema_id)
        )

    cur.execute(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_schema = %s AND table_name = 'sample_metadata'",
        (clean_schema,),
    )
    if cur.fetchone() is None:
        cur.execute(
            sql.SQL("""
            CREATE TABLE {schema}.sample_metadata (
                id SERIAL PRIMARY KEY,
                parent_table TEXT NOT NULL,
                sample_id TEXT NOT NULL,
                metadata_field TEXT NOT NULL,
                metadata_value TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(parent_table, sample_id, metadata_field)
            );
            """).format(schema=schema_id)
        )
        cur.execute(
            sql.SQL(
                "CREATE INDEX idx_sample_metadata_parent"
                " ON {schema}.sample_metadata(parent_table);"
            ).format(schema=schema_id)
        )
        cur.execute(
            sql.SQL(
                "CREATE INDEX idx_sample_metadata_sample"
                " ON {schema}.sample_metadata(sample_id);"
            ).format(schema=schema_id)
        )


def pg_create_data_table(cur, schema, table_name, columns, patient_col):
    """
    Create chunked PostgreSQL data table for a CSV column set.
    ---
    tags:
      - database
    summary: Create a single chunked data table for incoming CSV data.
    parameters:
      - name: cur
        in: code
        type: psycopg2.extensions.cursor
        required: true
        description: PostgreSQL cursor object.
      - name: table_name
        in: code
        type: string
        required: true
        description: Target table name.
      - name: columns
        in: code
        type: list
        required: true
        description: List of column names for the chunk.
      - name: patient_col
        in: code
        type: string
        required: true
        description: Name of the patient ID column.
    """
    schema_id = sql.Identifier(f"_{_clean_identifier(schema)}")
    table_id = sql.Identifier(_clean_identifier(table_name))
    patient_id = sql.Identifier(_clean_identifier(patient_col))
    col_defs = sql.SQL(", ").join(
        sql.SQL("{} TEXT").format(sql.Identifier(_clean_identifier(c)))
        for c in columns
    )

    cur.execute(
        sql.SQL("""
        CREATE TABLE IF NOT EXISTS {schema}.{table} (
            rowid SERIAL PRIMARY KEY,
            {patient} TEXT NOT NULL,
            {cols}
        );
        """).format(
            schema=schema_id,
            table=table_id,
            patient=patient_id,
            cols=col_defs,
        )
    )

    # Defense-in-depth: enable RLS on the per-dataset data table so any
    # non-superuser caller (Supabase edge functions, direct psql, future
    # API gateways) is gated by the curator/grant logic in
    # _fd.can_read_dataset(). The Flask path is enforced at the decorator
    # + handler layer (see filter_readable_tables / assert_can_read_table)
    # because the deployment's Postgres user is a superuser/BYPASSRLS role
    # that does not engage these policies; if you tighten POSTGRES_USER to
    # 'authenticated' you must also wire request.jwt.claims into the
    # connection so auth.uid() resolves -- the policies below assume that.
    select_policy = sql.Identifier(f"{_clean_identifier(table_name)}_select")
    write_policy = sql.Identifier(f"{_clean_identifier(table_name)}_write")
    cur.execute(
        sql.SQL("ALTER TABLE {schema}.{table} ENABLE ROW LEVEL SECURITY;")
        .format(schema=schema_id, table=table_id)
    )
    cur.execute(
        sql.SQL("DROP POLICY IF EXISTS {policy} ON {schema}.{table};")
        .format(policy=select_policy, schema=schema_id, table=table_id)
    )
    cur.execute(
        sql.SQL(
            "CREATE POLICY {policy} ON {schema}.{table} FOR SELECT "
            "USING (_fd.can_read_dataset((SELECT id FROM {schema}.metadata_tables "
            "WHERE table_name = %s LIMIT 1)));"
        ).format(policy=select_policy, schema=schema_id, table=table_id),
        (table_name,),
    )
    cur.execute(
        sql.SQL("DROP POLICY IF EXISTS {policy} ON {schema}.{table};")
        .format(policy=write_policy, schema=schema_id, table=table_id)
    )
    cur.execute(
        sql.SQL(
            "CREATE POLICY {policy} ON {schema}.{table} FOR ALL "
            "USING (_fd.current_role() = 'admin' "
            "  OR (_fd.current_role() = 'curator' AND EXISTS "
            "       (SELECT 1 FROM {schema}.metadata_tables m "
            "         WHERE m.table_name = %s AND m.owner_id = auth.uid())));"
        ).format(policy=write_policy, schema=schema_id, table=table_id),
        (table_name,),
    )
    # _fd no longer hands every new table to 'authenticated' automatically
    # (rbac_schema.sql); grant this one explicitly since its row rules above
    # decide who sees what. Skipped on plain Postgres without Supabase roles.
    cur.execute("SELECT 1 FROM pg_roles WHERE rolname = 'authenticated'")
    if cur.fetchone():
        cur.execute(
            sql.SQL(
                "GRANT SELECT, INSERT, UPDATE, DELETE ON {schema}.{table} "
                "TO authenticated;"
            ).format(schema=schema_id, table=table_id)
        )


def pg_insert_metadata(cur, schema, table_name, main_table, description, origin, owner_id=None):
    """
    Insert a record into _fd.metadata_tables for tracking.
    ---
    tags:
      - database
    summary: Store metadata for uploaded file chunk.
    parameters:
      - name: cur
        in: code
        type: psycopg2.extensions.cursor
        required: true
        description: PostgreSQL cursor object.
      - name: table_name
        in: code
        type: string
        required: true
        description: Name of the chunk table.
      - name: main_table
        in: code
        type: string
        required: true
        description: Original base table name.
      - name: description
        in: code
        type: string
        required: false
        description: Description of the uploaded file.
      - name: origin
        in: code
        type: string
        required: false
        description: Source or origin of the file.
      - name: owner_id
        in: code
        type: uuid
        required: false
        description: UUID of the user who owns this dataset (for RBAC grants).
    """
    schema_id = sql.Identifier(f"_{_clean_identifier(schema)}")
    cur.execute(
        sql.SQL("""
        INSERT INTO {schema}.metadata_tables (table_name, main_table,
          description, origin, owner_id)
        VALUES (%s, %s, %s, %s, %s);
        """).format(schema=schema_id),
        (table_name, main_table, description, origin, owner_id),
    )


def pg_insert_data_rows(
    cur, schema, table_name, patient_col, rows, columns, chunk_index
):
    """
    Insert chunked rows into the corresponding PostgreSQL data table.
    ---
    tags:
      - database
    summary: Insert CSV row values into chunk table with hashed patient ID.
    parameters:
      - name: cur
        in: code
        type: psycopg2.extensions.cursor
        required: true
        description: PostgreSQL cursor object.
      - name: table_name
        in: code
        type: string
        required: true
        description: Target chunk table name.
      - name: patient_col
        in: code
        type: string
        required: true
        description: Name of the patient ID column.
      - name: rows
        in: code
        type: list
        required: true
        description: List of parsed CSV rows.
      - name: columns
        in: code
        type: list
        required: true
        description: Column names for this chunk.
      - name: chunk_index
        in: code
        type: integer
        required: true
        description: Current chunk index (zero-based).
    """
    col_start = chunk_index * 1200
    col_end = col_start + len(columns)
    clean_cols = [_clean_identifier(c) for c in columns]
    col_ids = sql.SQL(", ").join(sql.Identifier(c) for c in clean_cols)
    placeholders = sql.SQL(", ").join(sql.Placeholder() for _ in clean_cols)
    schema_id = sql.Identifier(f"_{_clean_identifier(schema)}")
    table_id = sql.Identifier(_clean_identifier(table_name))
    patient_id = sql.Identifier(_clean_identifier(patient_col))

    insert_query = sql.SQL("""
        INSERT INTO {schema}.{table} ({patient}, {cols})
        VALUES (%s, {placeholders});
    """).format(
        schema=schema_id,
        table=table_id,
        patient=patient_id,
        cols=col_ids,
        placeholders=placeholders,
    )

    for row in rows:
        if len(row) < 2:
            continue
        patient_hash = sha256(row[0].encode()).hexdigest()
        values = row[1:][col_start:col_end]
        if len(values) != len(clean_cols):
            continue
        cur.execute(insert_query, [patient_hash] + values)


def pg_sanitize_column(col):
    """
    Sanitize column name for use in PostgreSQL queries.
    ---
    tags:
      - utility
    summary: Remove unsafe characters and quote if necessary.
    parameters:
      - name: col
        in: code
        type: string
        required: true
        description: Column name from CSV header.
    """
    return "".join(c for c in col if c.isalnum() or c == "_")


def file_chunk_columns(columns, chunk_size=1200):
    """
    Split CSV column names into manageable chunks.
    ---
    tags:
      - file
    summary: Chunk column headers for table creation.
    parameters:
      - name: columns
        in: code
        type: list
        required: true
        description: List of CSV column headers (excluding patient ID).
      - name: chunk_size
        in: code
        type: integer
        required: false
        description: Max number of columns per chunk.
    """
    return [columns[i : i + chunk_size] for i in range(0, len(columns), chunk_size)]


def file_save_and_read(file):
    """
    Save uploaded file to disk and return filename and CSV content.
    ---
    tags:
      - file
    summary: Save and parse uploaded CSV file.
    parameters:
      - name: file
        in: formData
        type: file
        required: true
        description: File object from Flask `request.files`.
    """
    filename = secure_filename(file.filename)
    extension = filename.rsplit(".", 1)[-1].lower()
    # Timestamp plus a short random tag: the stem becomes the dataset's table
    # name, and two uploads of the same file in the same second must not land
    # in (and merge into) the same tables.
    timestamped = (
        f"{filename.rsplit('.', 1)[0]}_{int(time.time())}_{secrets.token_hex(3)}"
        f".{extension}"
    )
    path = os.path.join(current_app.config["UPLOAD_FOLDER"], timestamped)
    file.save(path)

    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        lines = [row for row in reader if row]

    if not lines:
        raise ValueError("Uploaded file is empty or malformed.")

    return lines, timestamped
