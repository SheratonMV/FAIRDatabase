"""
Integration tests for dashboard helper functions.

Tests cover:
- Dynamic table creation with PostgreSQL
- Data insertion with chunking
- Column sanitization (SQL injection prevention)
- Patient ID hashing
- File operations
"""

import pytest
import pandas as pd
from hashlib import sha256
from src.dashboard.helpers import (
    pg_create_data_table,
    pg_insert_data_rows,
    pg_sanitize_column,
    file_chunk_columns,
    file_save_and_read,
    pg_ensure_schema_and_metadata,
    pg_insert_metadata,
)
from app import get_db


class TestPgSanitizeColumn:
    """Test column name sanitization for SQL injection prevention"""

    def test_sanitizes_basic_column_name(self):
        """Standard column name → unchanged"""
        assert pg_sanitize_column("patient_id") == "patient_id"
        assert pg_sanitize_column("age") == "age"
        assert pg_sanitize_column("measurement_value") == "measurement_value"

    def test_sanitizes_column_with_spaces(self):
        """Spaces → underscores"""
        assert pg_sanitize_column("patient id") == "patient_id"
        assert pg_sanitize_column("first name") == "first_name"

    def test_sanitizes_column_with_special_characters(self):
        """Special characters → underscores"""
        assert pg_sanitize_column("patient-id") == "patient_id"
        assert pg_sanitize_column("value@2024") == "value_2024"
        assert pg_sanitize_column("col#1") == "col_1"
        assert pg_sanitize_column("data%change") == "data_change"

    def test_sanitizes_sql_injection_attempts(self):
        """SQL injection patterns → sanitized"""
        # SQL keywords and dangerous patterns
        assert pg_sanitize_column("DROP TABLE users") == "drop_table_users"
        assert pg_sanitize_column("'; DROP TABLE--") == "___drop_table__"
        assert pg_sanitize_column("SELECT * FROM") == "select___from"

    def test_sanitizes_unicode_characters(self):
        """Unicode characters → underscores or removed"""
        result = pg_sanitize_column("patientå_id")
        # Should handle unicode gracefully (exact behavior depends on implementation)
        assert "_id" in result or "id" in result

    def test_sanitizes_column_starting_with_number(self):
        """Column starting with number → prefixed or sanitized"""
        result = pg_sanitize_column("123_column")
        # PostgreSQL identifiers can't start with numbers
        assert not result[0].isdigit() or result.startswith("col_")

    def test_sanitizes_very_long_column_name(self):
        """Very long name → truncated to PostgreSQL limit (63 chars)"""
        long_name = "a" * 100
        result = pg_sanitize_column(long_name)
        # PostgreSQL identifier limit is 63 characters
        assert len(result) <= 63

    def test_sanitizes_empty_column_name(self):
        """Empty string → default column name or error handled"""
        result = pg_sanitize_column("")
        # Should produce a valid column name or be handled
        assert len(result) > 0


class TestFileChunkColumns:
    """Test column chunking for wide datasets"""

    def test_chunks_columns_below_threshold(self):
        """Less than 1200 columns → single chunk"""
        columns = [f"col{i}" for i in range(100)]
        chunks = file_chunk_columns(columns, chunk_size=1200)
        assert len(chunks) == 1
        assert chunks[0] == columns

    def test_chunks_columns_at_exact_threshold(self):
        """Exactly 1200 columns → single chunk"""
        columns = [f"col{i}" for i in range(1200)]
        chunks = file_chunk_columns(columns, chunk_size=1200)
        assert len(chunks) == 1
        assert len(chunks[0]) == 1200

    def test_chunks_columns_just_above_threshold(self):
        """1201 columns → two chunks"""
        columns = [f"col{i}" for i in range(1201)]
        chunks = file_chunk_columns(columns, chunk_size=1200)
        assert len(chunks) == 2
        assert len(chunks[0]) == 1200
        assert len(chunks[1]) == 1

    def test_chunks_columns_exactly_double_threshold(self):
        """Exactly 2400 columns → two chunks"""
        columns = [f"col{i}" for i in range(2400)]
        chunks = file_chunk_columns(columns, chunk_size=1200)
        assert len(chunks) == 2
        assert len(chunks[0]) == 1200
        assert len(chunks[1]) == 1200

    def test_chunks_columns_with_custom_chunk_size(self):
        """Custom chunk size → respects parameter"""
        columns = [f"col{i}" for i in range(250)]
        chunks = file_chunk_columns(columns, chunk_size=100)
        assert len(chunks) == 3
        assert len(chunks[0]) == 100
        assert len(chunks[1]) == 100
        assert len(chunks[2]) == 50

    def test_chunks_empty_column_list(self):
        """Empty list → empty result"""
        chunks = file_chunk_columns([], chunk_size=1200)
        assert len(chunks) == 0


class TestPgCreateDataTable:
    """Test dynamic PostgreSQL table creation"""

    def test_creates_table_with_valid_columns(self, app):
        """Standard columns → table created successfully"""
        with app.app_context():
            conn = get_db()
            cur = conn.cursor()

            try:
                # Clean up any existing test table
                cur.execute("DROP TABLE IF EXISTS _realtime.test_table_create CASCADE")
                conn.commit()

                columns = ["age", "gender", "diagnosis"]
                pg_create_data_table(cur, "realtime", "test_table_create", columns, "patient_id")
                conn.commit()

                # Verify table exists
                cur.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables
                        WHERE table_schema = '_realtime'
                        AND table_name = 'test_table_create'
                    )
                """)
                assert cur.fetchone()[0] is True

                # Verify columns exist
                cur.execute("""
                    SELECT column_name FROM information_schema.columns
                    WHERE table_schema = '_realtime'
                    AND table_name = 'test_table_create'
                    ORDER BY ordinal_position
                """)
                column_names = [row[0] for row in cur.fetchall()]
                assert "rowid" in column_names
                assert "patient_id" in column_names
                assert "age" in column_names
                assert "gender" in column_names
                assert "diagnosis" in column_names

            finally:
                cur.execute("DROP TABLE IF EXISTS _realtime.test_table_create CASCADE")
                conn.commit()
                cur.close()

    def test_creates_index_on_patient_column(self, app):
        """Table creation → index on patient_id created"""
        with app.app_context():
            conn = get_db()
            cur = conn.cursor()

            try:
                cur.execute("DROP TABLE IF EXISTS _realtime.test_table_index CASCADE")
                conn.commit()

                columns = ["col1"]
                pg_create_data_table(cur, "realtime", "test_table_index", columns, "patient_id")
                conn.commit()

                # Verify index exists
                cur.execute("""
                    SELECT EXISTS (
                        SELECT FROM pg_indexes
                        WHERE schemaname = '_realtime'
                        AND tablename = 'test_table_index'
                        AND indexname = 'idx_test_table_index_patient_id'
                    )
                """)
                assert cur.fetchone()[0] is True

            finally:
                cur.execute("DROP TABLE IF EXISTS _realtime.test_table_index CASCADE")
                conn.commit()
                cur.close()

    def test_grants_permissions_to_supabase_roles(self, app):
        """Table creation → permissions granted to anon, authenticated, service_role"""
        with app.app_context():
            conn = get_db()
            cur = conn.cursor()

            try:
                cur.execute("DROP TABLE IF EXISTS _realtime.test_table_perms CASCADE")
                conn.commit()

                columns = ["col1"]
                pg_create_data_table(cur, "realtime", "test_table_perms", columns, "patient_id")
                conn.commit()

                # Verify permissions (check if anon role can access)
                cur.execute("""
                    SELECT has_table_privilege('anon', '_realtime.test_table_perms', 'SELECT')
                """)
                assert cur.fetchone()[0] is True

                cur.execute("""
                    SELECT has_table_privilege('authenticated', '_realtime.test_table_perms', 'SELECT')
                """)
                assert cur.fetchone()[0] is True

            finally:
                cur.execute("DROP TABLE IF EXISTS _realtime.test_table_perms CASCADE")
                conn.commit()
                cur.close()

    def test_handles_special_characters_in_column_names(self, app):
        """Column names with special chars → sanitized and table created"""
        with app.app_context():
            conn = get_db()
            cur = conn.cursor()

            try:
                cur.execute("DROP TABLE IF EXISTS _realtime.test_table_special CASCADE")
                conn.commit()

                # Columns with special characters (will be sanitized)
                columns = ["patient-name", "test@date", "value#1"]
                pg_create_data_table(cur, "realtime", "test_table_special", columns, "patient_id")
                conn.commit()

                # Verify table exists
                cur.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables
                        WHERE table_schema = '_realtime'
                        AND table_name = 'test_table_special'
                    )
                """)
                assert cur.fetchone()[0] is True

            finally:
                cur.execute("DROP TABLE IF EXISTS _realtime.test_table_special CASCADE")
                conn.commit()
                cur.close()

    def test_creates_table_with_many_columns(self, app):
        """Large column set (near 1200 limit) → table created"""
        with app.app_context():
            conn = get_db()
            cur = conn.cursor()

            try:
                cur.execute("DROP TABLE IF EXISTS _realtime.test_table_wide CASCADE")
                conn.commit()

                # Create 100 columns (reasonable test size)
                columns = [f"col{i}" for i in range(100)]
                pg_create_data_table(cur, "realtime", "test_table_wide", columns, "patient_id")
                conn.commit()

                # Verify table exists and has correct column count
                cur.execute("""
                    SELECT COUNT(*) FROM information_schema.columns
                    WHERE table_schema = '_realtime'
                    AND table_name = 'test_table_wide'
                """)
                # Should have 100 + rowid + patient_id = 102 columns
                column_count = cur.fetchone()[0]
                assert column_count == 102

            finally:
                cur.execute("DROP TABLE IF EXISTS _realtime.test_table_wide CASCADE")
                conn.commit()
                cur.close()


class TestPgInsertDataRows:
    """Test data insertion with patient ID hashing"""

    def test_inserts_single_row(self, app):
        """Single row → inserted with hashed patient ID"""
        with app.app_context():
            conn = get_db()
            cur = conn.cursor()

            try:
                # Create table
                cur.execute("DROP TABLE IF EXISTS _realtime.test_insert_single CASCADE")
                conn.commit()
                columns = ["age", "gender"]
                pg_create_data_table(cur, "realtime", "test_insert_single", columns, "patient_id")
                conn.commit()

                # Insert data
                rows = [["P123", "45", "M"]]
                pg_insert_data_rows(cur, "realtime", "test_insert_single", "patient_id", rows, columns, 0)
                conn.commit()

                # Verify insertion
                cur.execute("SELECT COUNT(*) FROM _realtime.test_insert_single")
                assert cur.fetchone()[0] == 1

                # Verify patient ID is hashed
                expected_hash = sha256("P123".encode()).hexdigest()
                cur.execute("SELECT patient_id FROM _realtime.test_insert_single")
                assert cur.fetchone()[0] == expected_hash

            finally:
                cur.execute("DROP TABLE IF EXISTS _realtime.test_insert_single CASCADE")
                conn.commit()
                cur.close()

    def test_inserts_multiple_rows(self, app):
        """Multiple rows → all inserted correctly"""
        with app.app_context():
            conn = get_db()
            cur = conn.cursor()

            try:
                cur.execute("DROP TABLE IF EXISTS _realtime.test_insert_multi CASCADE")
                conn.commit()
                columns = ["value"]
                pg_create_data_table(cur, "realtime", "test_insert_multi", columns, "patient_id")
                conn.commit()

                # Insert multiple rows
                rows = [
                    ["P1", "100"],
                    ["P2", "200"],
                    ["P3", "300"],
                ]
                pg_insert_data_rows(cur, "realtime", "test_insert_multi", "patient_id", rows, columns, 0)
                conn.commit()

                # Verify all inserted
                cur.execute("SELECT COUNT(*) FROM _realtime.test_insert_multi")
                assert cur.fetchone()[0] == 3

            finally:
                cur.execute("DROP TABLE IF EXISTS _realtime.test_insert_multi CASCADE")
                conn.commit()
                cur.close()

    def test_hashes_different_patient_ids_uniquely(self, app):
        """Different patient IDs → different hashes"""
        with app.app_context():
            conn = get_db()
            cur = conn.cursor()

            try:
                cur.execute("DROP TABLE IF EXISTS _realtime.test_hash_unique CASCADE")
                conn.commit()
                columns = ["value"]
                pg_create_data_table(cur, "realtime", "test_hash_unique", columns, "patient_id")
                conn.commit()

                rows = [
                    ["P1", "100"],
                    ["P2", "200"],
                ]
                pg_insert_data_rows(cur, "realtime", "test_hash_unique", "patient_id", rows, columns, 0)
                conn.commit()

                # Verify different hashes
                cur.execute("SELECT DISTINCT patient_id FROM _realtime.test_hash_unique")
                hashes = [row[0] for row in cur.fetchall()]
                assert len(hashes) == 2
                assert hashes[0] != hashes[1]

            finally:
                cur.execute("DROP TABLE IF EXISTS _realtime.test_hash_unique CASCADE")
                conn.commit()
                cur.close()

    def test_skips_malformed_rows_with_too_few_columns(self, app):
        """Rows with < 2 values → skipped"""
        with app.app_context():
            conn = get_db()
            cur = conn.cursor()

            try:
                cur.execute("DROP TABLE IF EXISTS _realtime.test_skip_malformed CASCADE")
                conn.commit()
                columns = ["col1"]
                pg_create_data_table(cur, "realtime", "test_skip_malformed", columns, "patient_id")
                conn.commit()

                # Mix of valid and invalid rows
                rows = [
                    ["P1", "value1"],  # Valid
                    ["P2"],            # Invalid - too few columns
                    ["P3", "value3"],  # Valid
                ]
                pg_insert_data_rows(cur, "realtime", "test_skip_malformed", "patient_id", rows, columns, 0)
                conn.commit()

                # Only valid rows should be inserted
                cur.execute("SELECT COUNT(*) FROM _realtime.test_skip_malformed")
                assert cur.fetchone()[0] == 2

            finally:
                cur.execute("DROP TABLE IF EXISTS _realtime.test_skip_malformed CASCADE")
                conn.commit()
                cur.close()

    def test_handles_chunked_insert_first_chunk(self, app):
        """Chunk index 0 → inserts first 1200 columns"""
        with app.app_context():
            conn = get_db()
            cur = conn.cursor()

            try:
                cur.execute("DROP TABLE IF EXISTS _realtime.test_chunk_0 CASCADE")
                conn.commit()
                # Simulate first chunk (columns 0-4 for testing)
                columns = ["col0", "col1", "col2", "col3", "col4"]
                pg_create_data_table(cur, "realtime", "test_chunk_0", columns, "patient_id")
                conn.commit()

                # Data row with patient ID + 5 column values
                rows = [["P1", "v0", "v1", "v2", "v3", "v4"]]
                pg_insert_data_rows(cur, "realtime", "test_chunk_0", "patient_id", rows, columns, 0)
                conn.commit()

                # Verify insertion
                cur.execute("SELECT COUNT(*) FROM _realtime.test_chunk_0")
                assert cur.fetchone()[0] == 1

            finally:
                cur.execute("DROP TABLE IF EXISTS _realtime.test_chunk_0 CASCADE")
                conn.commit()
                cur.close()

    def test_handles_empty_row_list(self, app):
        """Empty rows list → no error, no inserts"""
        with app.app_context():
            conn = get_db()
            cur = conn.cursor()

            try:
                cur.execute("DROP TABLE IF EXISTS _realtime.test_empty_rows CASCADE")
                conn.commit()
                columns = ["col1"]
                pg_create_data_table(cur, "realtime", "test_empty_rows", columns, "patient_id")
                conn.commit()

                # Empty rows
                pg_insert_data_rows(cur, "realtime", "test_empty_rows", "patient_id", [], columns, 0)
                conn.commit()

                # Verify no rows inserted
                cur.execute("SELECT COUNT(*) FROM _realtime.test_empty_rows")
                assert cur.fetchone()[0] == 0

            finally:
                cur.execute("DROP TABLE IF EXISTS _realtime.test_empty_rows CASCADE")
                conn.commit()
                cur.close()


class TestFileSaveAndRead:
    """Test file operations for CSV data"""

    def test_saves_and_reads_csv_file(self, tmp_path):
        """Save CSV → read back returns same data"""
        file_path = tmp_path / "test_data.csv"

        # Create test data
        df = pd.DataFrame({
            'patient_id': ['P1', 'P2', 'P3'],
            'age': [25, 30, 35],
            'value': ['A', 'B', 'C']
        })

        # Save file
        content, rows = file_save_and_read(df, str(file_path))

        # Verify file exists
        assert file_path.exists()

        # Verify returned rows match DataFrame
        assert len(rows) == 3
        assert rows[0] == ['P1', '25', 'A']
        assert rows[1] == ['P2', '30', 'B']
        assert rows[2] == ['P3', '35', 'C']

        # Verify returned content (list of lists)
        assert len(content) == 4  # Header + 3 rows
        assert content[0] == ['patient_id', 'age', 'value']

    def test_handles_empty_dataframe(self, tmp_path):
        """Empty DataFrame → empty file created"""
        file_path = tmp_path / "empty.csv"

        df = pd.DataFrame()
        content, rows = file_save_and_read(df, str(file_path))

        assert file_path.exists()
        assert len(rows) == 0


class TestPgEnsureSchemaAndMetadata:
    """Test schema and metadata table setup"""

    def test_ensures_schema_exists(self, app):
        """Schema creation → _realtime schema exists"""
        with app.app_context():
            conn = get_db()
            cur = conn.cursor()

            try:
                pg_ensure_schema_and_metadata(cur, "realtime")
                conn.commit()

                # Verify schema exists
                cur.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.schemata
                        WHERE schema_name = '_realtime'
                    )
                """)
                assert cur.fetchone()[0] is True

            finally:
                cur.close()

    def test_ensures_metadata_table_exists(self, app):
        """Metadata table creation → metadata_tables exists"""
        with app.app_context():
            conn = get_db()
            cur = conn.cursor()

            try:
                pg_ensure_schema_and_metadata(cur, "realtime")
                conn.commit()

                # Verify metadata_tables exists
                cur.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables
                        WHERE table_schema = '_realtime'
                        AND table_name = 'metadata_tables'
                    )
                """)
                assert cur.fetchone()[0] is True

            finally:
                cur.close()


class TestPgInsertMetadata:
    """Test metadata insertion"""

    def test_inserts_metadata_record(self, app):
        """Metadata insertion → record created"""
        with app.app_context():
            conn = get_db()
            cur = conn.cursor()

            try:
                # Ensure schema exists
                pg_ensure_schema_and_metadata(cur, "realtime")
                conn.commit()

                # Clean up any existing test metadata
                cur.execute("""
                    DELETE FROM _realtime.metadata_tables
                    WHERE table_name LIKE 'test_meta_%'
                """)
                conn.commit()

                # Insert metadata
                table_name = "test_meta_table"
                pg_insert_metadata(
                    cur, "realtime", table_name, table_name,
                    "Test description", "Test origin"
                )
                conn.commit()

                # Verify insertion
                cur.execute("""
                    SELECT COUNT(*) FROM _realtime.metadata_tables
                    WHERE table_name = %s
                """, [table_name])
                assert cur.fetchone()[0] >= 1

            finally:
                # Clean up
                cur.execute("""
                    DELETE FROM _realtime.metadata_tables
                    WHERE table_name LIKE 'test_meta_%'
                """)
                conn.commit()
                cur.close()
