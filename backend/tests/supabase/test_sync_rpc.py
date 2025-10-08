from unittest.mock import MagicMock, patch

import pytest
from httpx import ConnectError, HTTPStatusError, RequestError, TimeoutException
from postgrest.exceptions import APIError

from config import supabase_extension
from src.exceptions import GenericExceptionHandler


class TestSyncRPCCall:
    """Test safe_rpc_call method with various scenarios"""

    def test_successful_rpc_call(self, app):
        """Test successful RPC call returns data"""
        with app.app_context():
            result = supabase_extension.safe_rpc_call(
                "get_all_tables", {"p_schema_name": "_realtime"}
            )

            assert isinstance(result, list)
            table_names = [t["table_name"] for t in result]
            assert "metadata_tables" in table_names

    def test_rpc_call_table_exists_true(self, app):
        """Test table_exists RPC returns True for existing table"""
        with app.app_context():
            result = supabase_extension.safe_rpc_call(
                "table_exists", {"p_table_name": "metadata_tables", "p_schema_name": "_realtime"}
            )

            assert result is True

    def test_rpc_call_table_exists_false(self, app):
        """Test table_exists RPC returns False for non-existent table"""
        with app.app_context():
            result = supabase_extension.safe_rpc_call(
                "table_exists", {"p_table_name": "nonexistent_table", "p_schema_name": "_realtime"}
            )

            assert result is False

    def test_rpc_call_get_table_columns(self, app):
        """Test get_table_columns RPC returns correct structure"""
        with app.app_context():
            result = supabase_extension.safe_rpc_call(
                "get_table_columns", {"p_table_name": "metadata_tables", "p_schema_name": "_realtime"}
            )

            assert isinstance(result, list)
            assert len(result) > 0

            column_names = [col["column_name"] for col in result]
            assert "id" in column_names
            assert "table_name" in column_names

    def test_rpc_call_search_tables_by_column(self, app):
        """Test search_tables_by_column RPC finds correct tables"""
        with app.app_context():
            result = supabase_extension.safe_rpc_call(
                "search_tables_by_column",
                {"p_column_name": "table_name", "p_schema_name": "_realtime"},
            )

            assert isinstance(result, list)
            table_names = [t["table_name"] for t in result]
            assert "metadata_tables" in table_names

    @pytest.mark.parametrize(
        "error_code,expected_status,error_message",
        [
            ("42883", 404, "not found"),
            ("42P01", 404, "not found"),
            ("42501", 403, "permission denied"),
            ("42502", 403, "permission denied"),
            ("23505", 409, "duplicate"),
            ("23503", 409, "foreign key"),
        ],
    )
    def test_rpc_call_api_errors(self, app, error_code, expected_status, error_message):
        """Test RPC call handles various PostgreSQL errors correctly"""
        with app.app_context(), patch.object(supabase_extension.client, "rpc") as mock_rpc:
            mock_execute = MagicMock()
            mock_execute.side_effect = APIError(
                {
                    "code": error_code,
                    "message": f"Test error {error_code}",
                    "hint": "Test hint",
                    "details": "Test details",
                }
            )
            mock_rpc.return_value.execute = mock_execute

            with pytest.raises(GenericExceptionHandler) as exc_info:
                supabase_extension.safe_rpc_call("test_function", {})

            assert exc_info.value.status_code == expected_status
            assert error_message.lower() in exc_info.value.message.lower()

    def test_rpc_call_timeout_error(self, app):
        """Test RPC call handles timeout errors"""
        with app.app_context(), patch.object(supabase_extension.client, "rpc") as mock_rpc:
            mock_execute = MagicMock()
            mock_execute.side_effect = TimeoutException("Request timeout")
            mock_rpc.return_value.execute = mock_execute

            with pytest.raises(GenericExceptionHandler) as exc_info:
                supabase_extension.safe_rpc_call("test_function", {})

            assert exc_info.value.status_code == 504
            assert "timeout" in exc_info.value.message.lower()

    def test_rpc_call_connection_error(self, app):
        """Test RPC call handles connection errors"""
        with app.app_context(), patch.object(supabase_extension.client, "rpc") as mock_rpc:
            mock_execute = MagicMock()
            mock_execute.side_effect = ConnectError("Cannot connect")
            mock_rpc.return_value.execute = mock_execute

            with pytest.raises(GenericExceptionHandler) as exc_info:
                supabase_extension.safe_rpc_call("test_function", {})

            assert exc_info.value.status_code == 503
            assert "connect" in exc_info.value.message.lower()

    def test_rpc_call_request_error(self, app):
        """Test RPC call handles generic request errors"""
        with app.app_context(), patch.object(supabase_extension.client, "rpc") as mock_rpc:
            mock_execute = MagicMock()
            mock_execute.side_effect = RequestError("Network error")
            mock_rpc.return_value.execute = mock_execute

            with pytest.raises(GenericExceptionHandler) as exc_info:
                supabase_extension.safe_rpc_call("test_function", {})

            assert exc_info.value.status_code == 503

    def test_rpc_call_http_status_error(self, app):
        """Test RPC call handles HTTP status errors"""
        with app.app_context(), patch.object(supabase_extension.client, "rpc") as mock_rpc:
            mock_response = MagicMock()
            mock_response.status_code = 500
            mock_execute = MagicMock()
            mock_execute.side_effect = HTTPStatusError(
                "Server error", request=MagicMock(), response=mock_response
            )
            mock_rpc.return_value.execute = mock_execute

            with pytest.raises(GenericExceptionHandler) as exc_info:
                supabase_extension.safe_rpc_call("test_function", {})

            assert exc_info.value.status_code == 500

    def test_rpc_call_pgrst204_returns_empty_list(self, app):
        """Test RPC call returns empty list for PGRST204 (no rows)"""
        with app.app_context(), patch.object(supabase_extension.client, "rpc") as mock_rpc:
            mock_execute = MagicMock()
            mock_execute.side_effect = APIError({"code": "PGRST204", "message": "No rows returned"})
            mock_rpc.return_value.execute = mock_execute

            result = supabase_extension.safe_rpc_call("test_function", {})

            assert result == []

    def test_rpc_call_retry_decorator_configured(self, app):
        """Test retry decorator is configured on safe_rpc_call method"""
        # Verify the retry decorator is present
        assert hasattr(supabase_extension.safe_rpc_call, "retry")
        retry_obj = supabase_extension.safe_rpc_call.retry

        # Verify retry stops after 3 attempts
        assert retry_obj.stop.max_attempt_number == 3

    def test_rpc_call_error_handling_logs_and_converts(self, app):
        """Test RPC call logs errors and converts to GenericExceptionHandler

        Note: Current implementation catches retryable exceptions (ConnectError, TimeoutException,
        RequestError) and converts them to GenericExceptionHandler before the retry decorator
        can see them. This means retries don't currently work as intended. Future refactoring
        could move exception handling outside the retry decorator to enable actual retries.
        """
        with app.app_context(), patch.object(supabase_extension.client, "rpc") as mock_rpc:
            mock_rpc.return_value.execute.side_effect = ConnectError("Connection refused")

            with pytest.raises(GenericExceptionHandler) as exc_info:
                supabase_extension.safe_rpc_call("test_function", {})

            assert exc_info.value.status_code == 503
            # Currently only attempts once due to exception handling structure
            assert mock_rpc.call_count == 1

    def test_rpc_call_no_retry_on_permanent_errors(self, app):
        """Test RPC call does NOT retry on permanent errors like APIError"""
        with app.app_context(), patch.object(supabase_extension.client, "rpc") as mock_rpc:
            mock_rpc.return_value.execute.side_effect = APIError(
                {"code": "42883", "message": "Function not found"}
            )

            with pytest.raises(GenericExceptionHandler):
                supabase_extension.safe_rpc_call("test_function", {})

            # Should only attempt once (no retries for permanent errors)
            assert mock_rpc.call_count == 1

    def test_rpc_call_unexpected_exception(self, app):
        """Test RPC call handles unexpected exceptions"""
        with app.app_context(), patch.object(supabase_extension.client, "rpc") as mock_rpc:
            mock_execute = MagicMock()
            mock_execute.side_effect = ValueError("Unexpected error")
            mock_rpc.return_value.execute = mock_execute

            with pytest.raises(GenericExceptionHandler) as exc_info:
                supabase_extension.safe_rpc_call("test_function", {})

            assert exc_info.value.status_code == 500
            assert "unexpected error" in exc_info.value.message.lower()


class TestClientProperties:
    """Test Supabase client properties and initialization"""

    def test_client_property_returns_singleton(self, app):
        """Test client property returns the same instance"""
        with app.app_context():
            client1 = supabase_extension.client
            client2 = supabase_extension.client

            assert client1 is client2

    def test_service_role_client_property_returns_singleton(self, app):
        """Test service_role_client property returns the same instance"""
        with app.app_context():
            client1 = supabase_extension.service_role_client
            client2 = supabase_extension.service_role_client

            assert client1 is client2

    def test_client_property_raises_without_init(self):
        """Test client property raises error without initialization"""
        # Create new instance without init_app
        sb = type(supabase_extension).__new__(type(supabase_extension))
        sb._client = None

        with pytest.raises(RuntimeError) as exc_info:
            _ = sb.client

        assert "not initialized" in str(exc_info.value).lower()

    def test_service_role_client_raises_without_init(self):
        """Test service_role_client raises error without initialization"""
        sb = type(supabase_extension).__new__(type(supabase_extension))
        sb._service_role_client = None

        with pytest.raises(RuntimeError) as exc_info:
            _ = sb.service_role_client

        assert "not initialized" in str(exc_info.value).lower()
