"""Utilities for saving, chunking, and importing CSV data into PostgreSQL."""

import csv
import os
import time
from hashlib import sha256

from flask import current_app
from werkzeug.utils import secure_filename


def pg_ensure_schema_and_metadata(cur, schema):
    """
    Ensure PostgreSQL schema and metadata table exist.

    NOTE: Schema and metadata table creation is now handled by Supabase migrations:
    - supabase/migrations/20250106000000_create_realtime_schema.sql
    - supabase/migrations/20250106000001_create_metadata_tables.sql

    This function is kept for backward compatibility but no longer creates schema/tables.
    The schema and metadata_tables are automatically created when migrations are applied.

    ---
    tags:
      - database
    summary: Verify _realtime schema and metadata table exist (now handled by migrations).
    parameters:
      - name: cur
        in: code
        type: psycopg2.extensions.cursor
        required: true
        description: PostgreSQL cursor for executing commands.
    """
    # Schema and table creation now handled by Supabase migrations
    # This function remains for backward compatibility but is now a no-op
    pass


def pg_create_data_table(cur, schema, table_name, columns, patient_col):
    """
    Create chunked PostgreSQL data table for a CSV column set.

    NOTE: This function continues to use psycopg2 for DDL operations.
    Dynamic table creation via Supabase REST API has schema cache refresh issues.
    For CRUD operations, we use Supabase client (see pg_insert_data_rows).

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
      - name: schema
        in: code
        type: string
        required: true
        description: Schema name (e.g., 'realtime').
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
    clean_cols = [pg_sanitize_column(c) for c in columns]
    cols_def = ", ".join(f"{col} TEXT" for col in clean_cols)

    cur.execute(
        f"""
        CREATE TABLE IF NOT EXISTS _{schema}.{table_name} (
            rowid SERIAL PRIMARY KEY,
            {patient_col} TEXT NOT NULL,
            {cols_def}
        );
    """
    )

    # Grant permissions for Supabase to access the table
    cur.execute(
        f"""
        GRANT ALL ON TABLE _{schema}.{table_name} TO anon, authenticated, service_role;
        GRANT USAGE, SELECT ON SEQUENCE _{schema}.{table_name}_rowid_seq TO anon, authenticated, service_role;
        """
    )

    # Notify PostgREST to reload schema cache
    cur.execute("NOTIFY pgrst, 'reload schema'")


def pg_insert_metadata(cur, schema, table_name, main_table, description, origin):
    """
    Insert a record into _realtime.metadata_tables for tracking.

    NOTE: Migrated to use Supabase client instead of psycopg2.
    The 'cur' parameter is kept for backward compatibility but is no longer used.

    ---
    tags:
      - database
    summary: Store metadata for uploaded file chunk.
    parameters:
      - name: cur
        in: code
        type: psycopg2.extensions.cursor
        required: true
        description: PostgreSQL cursor object (deprecated, kept for compatibility).
      - name: schema
        in: code
        type: string
        required: true
        description: Schema name (e.g., 'realtime').
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
    """
    from config import supabase_extension

    schema = pg_sanitize_column(schema).strip('"')  # Remove quotes added by sanitize

    # Note: Always use .execute() for table operations
    response = (
        supabase_extension.client.schema(f"_{schema}")
        .table("metadata_tables")
        .insert(
            {
                "table_name": table_name,
                "main_table": main_table,
                "description": description,
                "origin": origin,
            }
        )
        .execute()
    )

    return response.data[0] if response.data else None


def pg_insert_data_rows(cur, schema, table_name, patient_col, rows, columns, chunk_index):
    """
    Insert chunked rows into the corresponding PostgreSQL data table.

    NOTE: Continues to use psycopg2 for dynamic table inserts due to PostgREST
    schema cache limitations. The Supabase REST API can't immediately see
    dynamically created tables.

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
      - name: schema
        in: code
        type: string
        required: true
        description: Schema name (e.g., 'realtime').
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
    clean_cols = [pg_sanitize_column(c) for c in columns]
    col_names = ", ".join(clean_cols)
    placeholders = ", ".join(["%s"] * len(clean_cols))

    for row in rows:
        if len(row) < 2:
            continue
        patient_hash = sha256(row[0].encode()).hexdigest()
        values = row[1:][col_start:col_end]
        if len(values) != len(clean_cols):
            continue
        cur.execute(
            f"""
            INSERT INTO _{schema}.{table_name} ({patient_col}, {col_names})
            VALUES (%s, {placeholders});
        """,
            [patient_hash] + values,
        )


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
    clean = "".join(c for c in col if c.isalnum() or c == "_")
    return f'"{clean}"' if "-" in clean else clean


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
    timestamped = f"{filename.rsplit('.', 1)[0]}_{int(time.time())}.{extension}"
    path = os.path.join(current_app.config["UPLOAD_FOLDER"], timestamped)
    file.save(path)

    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        lines = [row for row in reader if row]

    if not lines:
        raise ValueError("Uploaded file is empty or malformed.")

    return lines, timestamped
