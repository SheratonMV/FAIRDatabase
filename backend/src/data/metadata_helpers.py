"""Helper functions for sample metadata management."""

import pandas as pd
import re
from flask import current_app

# Whitelist of allowed metadata fields
ALLOWED_FIELDS = [
    'treatment', 'timepoint', 'condition', 'sample_type',
    'age_group', 'sex', 'cohort', 'group'
]

# Patterns to detect PII
FORBIDDEN_PATTERNS = [
    r'email', r'@', r'phone', r'address', r'ssn',
    r'\b\d{3}-\d{2}-\d{4}\b',  # SSN
    r'\b\d{2}/\d{2}/\d{4}\b',  # Date
]


def validate_metadata_csv(csv_file, parent_table, conn):
    """Validate metadata CSV. Returns (valid, errors, df)."""
    errors = []

    try:
        # Read CSV
        df = pd.read_csv(csv_file)

        # Check sample_id column
        if 'sample_id' not in df.columns:
            errors.append("CSV must have 'sample_id' column")
            return False, errors, None

        # Get OTU table columns
        cur = conn.cursor()
        cur.execute(f"""
            SELECT column_name FROM information_schema.columns
            WHERE table_schema = '_fd' AND table_name = %s
            AND column_name != 'rowid'
            ORDER BY ordinal_position
        """, (parent_table,))

        otu_columns = [row[0] for row in cur.fetchall()]
        if not otu_columns:
            errors.append(f"Parent table {parent_table} not found")
            return False, errors, None

        # First column is patient ID, rest are samples
        valid_samples = set(otu_columns[1:])

        # Check all sample_ids exist in OTU table
        missing = set(df['sample_id']) - valid_samples
        if missing:
            errors.append(f"Samples not in OTU table: {', '.join(list(missing)[:5])}")

        # Check metadata fields
        metadata_fields = [col for col in df.columns if col != 'sample_id']
        invalid_fields = [f for f in metadata_fields if f not in ALLOWED_FIELDS]
        if invalid_fields:
            errors.append(f"Invalid fields (use {', '.join(ALLOWED_FIELDS)}): {', '.join(invalid_fields)}")

        # Check for forbidden patterns in values
        for col in metadata_fields:
            for val in df[col].astype(str):
                for pattern in FORBIDDEN_PATTERNS:
                    if re.search(pattern, val, re.IGNORECASE):
                        errors.append(f"Forbidden pattern detected in {col}: {val[:20]}")
                        break

        if errors:
            return False, errors, df

        return True, [], df

    except Exception as e:
        return False, [f"Error reading CSV: {str(e)}"], None


def store_metadata(df, parent_table, conn):
    """Store metadata in database."""
    cur = conn.cursor()

    # Delete existing metadata for this table
    cur.execute("DELETE FROM _fd.sample_metadata WHERE parent_table = %s", (parent_table,))

    # Insert new metadata
    for _, row in df.iterrows():
        sample_id = row['sample_id']
        for field in df.columns:
            if field != 'sample_id':
                value = str(row[field])
                cur.execute("""
                    INSERT INTO _fd.sample_metadata
                    (parent_table, sample_id, metadata_field, metadata_value)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (parent_table, sample_id, metadata_field)
                    DO UPDATE SET metadata_value = EXCLUDED.metadata_value
                """, (parent_table, sample_id, field, value))

    conn.commit()


def get_metadata(parent_table, conn):
    """Get metadata for a table. Returns dict of {sample_id: {field: value}}."""
    cur = conn.cursor()
    cur.execute("""
        SELECT sample_id, metadata_field, metadata_value
        FROM _fd.sample_metadata
        WHERE parent_table = %s
    """, (parent_table,))

    metadata = {}
    for sample_id, field, value in cur.fetchall():
        if sample_id not in metadata:
            metadata[sample_id] = {}
        metadata[sample_id][field] = value

    return metadata


def get_metadata_fields(parent_table, conn):
    """Get list of available metadata fields for a table."""
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT metadata_field
        FROM _fd.sample_metadata
        WHERE parent_table = %s
    """, (parent_table,))

    return [row[0] for row in cur.fetchall()]


def has_metadata(parent_table, conn):
    """Check if table has metadata."""
    cur = conn.cursor()
    cur.execute("""
        SELECT COUNT(*) FROM _fd.sample_metadata
        WHERE parent_table = %s
    """, (parent_table,))

    count = cur.fetchone()[0]
    return count > 0
