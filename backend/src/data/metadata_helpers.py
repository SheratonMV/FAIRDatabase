"""This is a script that will help with uploading metadata for samples"""

import pandas as pd


def validate_metadata_csv(csv_file, parent_table, conn):
    """check if metadata is correct"""
    errors = []

    try:
        df = pd.read_csv(csv_file)

        if 'sample_id' not in df.columns:
            errors.append("CSV must have 'sample_id' column")
            return False, errors, None

        # get samples from parent table
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

        valid_samples = set(otu_columns[1:])

        # Check all sample_ids exist in OTU table
        missing = set(df['sample_id']) - valid_samples
        if missing:
            errors.append(f"Samples not in OTU table: {', '.join(list(missing)[:5])}")

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
