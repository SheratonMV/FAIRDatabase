"""Utilities for saving, chunking, and importing CSV data into PostgreSQL."""

from hashlib import sha256
from werkzeug.utils import secure_filename
from flask import current_app

import time
import os
import csv


def pg_ensure_schema_and_metadata(cur, schema):
    """
    Ensure PostgreSQL schema and metadata table exist.
    ---
    tags:
      - database
    summary: Create _realtime schema and metadata table if missing.
    parameters:
      - name: cur
        in: code
        type: psycopg2.extensions.cursor
        required: true
        description: PostgreSQL cursor for executing commands.
    """
    schema = pg_sanitize_column(schema)
    cur.execute(f"CREATE SCHEMA IF NOT EXISTS _{schema};")
    cur.execute(
        f"""
        CREATE TABLE IF NOT EXISTS _{schema}.metadata_tables (
            id SERIAL PRIMARY KEY,
            table_name TEXT NOT NULL,
            main_table TEXT NOT NULL,
            description TEXT,
            origin TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """
    )

    # Create sample metadata table
    cur.execute(
        f"""
        CREATE TABLE IF NOT EXISTS _{schema}.sample_metadata (
            id SERIAL PRIMARY KEY,
            parent_table TEXT NOT NULL,
            sample_id TEXT NOT NULL,
            metadata_field TEXT NOT NULL,
            metadata_value TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(parent_table, sample_id, metadata_field)
        );
        CREATE INDEX IF NOT EXISTS idx_sample_metadata_parent
            ON _{schema}.sample_metadata(parent_table);
        CREATE INDEX IF NOT EXISTS idx_sample_metadata_sample
            ON _{schema}.sample_metadata(sample_id);
    """
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


def pg_insert_metadata(cur, schema, table_name, main_table, description, origin):
    """
    Insert a record into _realtime.metadata_tables for tracking.
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
    """
    schema = pg_sanitize_column(schema)
    cur.execute(
        f"""
        INSERT INTO _{schema}.metadata_tables (table_name, main_table, \
          description, origin)
        VALUES (%s, %s, %s, %s);
    """,
        (table_name, main_table, description, origin),
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
