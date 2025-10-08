"""Tests for metadata query caching functionality."""

import time
from unittest.mock import patch

from config import (
    METADATA_CACHE_TTL,
    _get_cache_key,
    get_cached_table_columns,
    get_cached_tables,
    invalidate_metadata_cache,
    supabase_extension,
)


class TestMetadataCaching:
    """Test metadata caching functionality."""

    def test_cache_key_generation(self):
        """Test that cache keys are generated based on time windows."""
        # Cache keys should be the same within the same TTL window
        key1 = _get_cache_key()
        time.sleep(0.1)  # Small delay within same window
        key2 = _get_cache_key()
        assert key1 == key2, "Cache keys should be identical within same TTL window"

    def test_cache_key_changes_after_ttl(self):
        """Test that cache keys change after TTL expires (simulation)."""
        # Simulate time passing by manually calculating different time windows
        current_time = int(time.time())
        key1 = current_time // METADATA_CACHE_TTL
        future_time = current_time + METADATA_CACHE_TTL + 1
        key2 = future_time // METADATA_CACHE_TTL
        assert key1 != key2, "Cache keys should differ across TTL windows"

    def test_get_cached_tables_uses_cache(self):
        """Test that get_cached_tables properly caches results."""
        # Clear cache before test
        invalidate_metadata_cache()

        # Setup mock return value
        mock_data = [{"table_name": "test_p1"}, {"table_name": "test_p2"}]

        with patch.object(supabase_extension, "safe_rpc_call", return_value=mock_data) as mock_rpc:
            # First call should hit database
            result1 = get_cached_tables()
            assert result1 == mock_data
            assert mock_rpc.call_count == 1

            # Second call within same time window should use cache
            result2 = get_cached_tables()
            assert result2 == mock_data
            assert mock_rpc.call_count == 1  # Still 1, cache was used

            # Verify both results are identical
            assert result1 == result2

    def test_get_cached_table_columns_uses_cache(self):
        """Test that get_cached_table_columns properly caches results."""
        # Clear cache before test
        invalidate_metadata_cache()

        # Setup mock return value
        mock_data = [
            {"column_name": "rowid", "data_type": "integer"},
            {"column_name": "patient_id", "data_type": "text"},
        ]

        with patch.object(supabase_extension, "safe_rpc_call", return_value=mock_data) as mock_rpc:
            # First call should hit database
            result1 = get_cached_table_columns("test_p1")
            assert result1 == mock_data
            assert mock_rpc.call_count == 1

            # Second call with same table name should use cache
            result2 = get_cached_table_columns("test_p1")
            assert result2 == mock_data
            assert mock_rpc.call_count == 1  # Still 1, cache was used

            # Call with different table name should hit database
            result3 = get_cached_table_columns("test_p2")
            assert result3 == mock_data
            assert mock_rpc.call_count == 2  # New call for different table

    def test_invalidate_metadata_cache_clears_all_caches(self):
        """Test that invalidate_metadata_cache clears all cached data."""
        # Clear cache before test
        invalidate_metadata_cache()

        # Setup mock data with function to return appropriate data
        def mock_rpc_call(func_name, params):
            if func_name == "get_all_tables":
                return [{"table_name": "test_p1"}]
            elif func_name == "get_table_columns":
                return [{"column_name": "rowid"}]
            return []

        with patch.object(
            supabase_extension, "safe_rpc_call", side_effect=mock_rpc_call
        ) as mock_rpc:
            # Populate caches
            get_cached_tables()
            get_cached_table_columns("test_p1")
            assert mock_rpc.call_count == 2

            # Clear caches
            invalidate_metadata_cache()

            # Reset mock to track new calls
            mock_rpc.reset_mock()

            # These should now hit the database again
            get_cached_tables()
            get_cached_table_columns("test_p1")
            assert mock_rpc.call_count == 2

    def test_cached_functions_with_custom_schema(self):
        """Test that caching works with custom schema names."""
        invalidate_metadata_cache()

        mock_data = [{"table_name": "public_table"}]

        with patch.object(supabase_extension, "safe_rpc_call", return_value=mock_data) as mock_rpc:
            # Call with custom schema
            result = get_cached_tables(schema_name="public")
            assert result == mock_data
            mock_rpc.assert_called_once_with("get_all_tables", {"schema_name": "public"})

    def test_cached_tables_different_schemas_separate_cache(self):
        """Test that different schemas maintain separate cache entries."""
        invalidate_metadata_cache()

        realtime_data = [{"table_name": "realtime_table"}]
        public_data = [{"table_name": "public_table"}]

        def mock_rpc_call(func_name, params):
            if params.get("schema_name") == "public":
                return public_data
            return realtime_data

        with patch.object(
            supabase_extension, "safe_rpc_call", side_effect=mock_rpc_call
        ) as mock_rpc:
            # Call with different schemas
            result1 = get_cached_tables(schema_name="_realtime")
            result2 = get_cached_tables(schema_name="public")

            assert result1 == realtime_data
            assert result2 == public_data
            assert mock_rpc.call_count == 2
