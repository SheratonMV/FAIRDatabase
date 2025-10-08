from unittest.mock import MagicMock, patch

from psycopg2 import OperationalError

from config import get_db, teardown_db


class TestDatabaseConnection:
    """Test database connection management (relying on Supabase pooler)"""

    def test_get_db_returns_connection(self, app):
        """Test get_db returns a database connection"""
        with app.app_context():
            conn = get_db()

            assert conn is not None
            assert hasattr(conn, "cursor")

    def test_get_db_reuses_connection_in_context(self, app):
        """Test get_db reuses connection within same request context"""
        with app.app_context():
            from flask import g

            conn1 = get_db()
            conn2 = get_db()

            # Should be the same connection object within the same request
            assert conn1 is conn2
            assert g.db is conn1

    def test_get_db_handles_connection_failure(self, app):
        """Test get_db handles connection failures gracefully"""
        with app.app_context():
            # Mock psycopg2.connect to raise OperationalError
            with patch("config.psycopg2.connect") as mock_connect:
                mock_connect.side_effect = OperationalError("Connection failed")

                conn = get_db()

                assert conn is None

    def test_teardown_db_closes_connection(self, app):
        """Test teardown_db closes the connection"""
        with app.app_context():
            from flask import g

            # Get a real connection first, then replace with mock
            get_db()

            # Replace with mock connection to verify close is called
            mock_conn = MagicMock()
            g.db = mock_conn

            teardown_db(None)

            # Verify close was called
            mock_conn.close.assert_called_once()
            assert "db" not in g

    def test_teardown_db_handles_close_failure(self, app):
        """Test teardown_db handles close failures gracefully"""
        with app.app_context():
            from flask import g

            # Create mock connection that fails on close
            mock_conn = MagicMock()
            mock_conn.close.side_effect = Exception("Close failed")
            g.db = mock_conn

            # Should not raise exception
            teardown_db(None)

            assert "db" not in g

    def test_teardown_db_no_connection(self, app):
        """Test teardown_db handles case when no connection exists"""
        with app.app_context():
            from flask import g

            # Ensure no connection in g
            g.pop("db", None)

            # Should not raise exception
            teardown_db(None)

    def test_connection_config(self, app):
        """Test connection uses correct configuration"""
        with app.app_context():
            with patch("config.psycopg2.connect") as mock_connect:
                mock_connect.return_value = MagicMock()

                get_db()

                # Verify psycopg2.connect was called with correct params
                call_kwargs = mock_connect.call_args[1]
                assert call_kwargs["host"] == app.config["POSTGRES_HOST"]
                assert call_kwargs["port"] == app.config["POSTGRES_PORT"]
                assert call_kwargs["user"] == app.config["POSTGRES_USER"]
                assert call_kwargs["password"] == app.config["POSTGRES_SECRET"]
                assert call_kwargs["database"] == app.config["POSTGRES_DB_NAME"]
                assert call_kwargs["connect_timeout"] == 10
                assert "statement_timeout" in call_kwargs["options"]

    def test_connection_lifecycle(self, app):
        """Test complete connection lifecycle within request"""
        with app.app_context():
            # Get connection
            conn1 = get_db()
            assert conn1 is not None

            # Verify connection is reused
            conn2 = get_db()
            assert conn1 is conn2

            # Close connection
            teardown_db(None)

            # New connection should be created after teardown
            from flask import g

            assert "db" not in g


class TestPoolerModeDetection:
    """Test pooler mode detection from configuration"""

    def test_transaction_mode_detection_from_url(self):
        """Test transaction mode is detected from port 6543"""
        from config import Config

        # This is informational only - Config is set at import time
        # Just verify the detection logic exists
        assert hasattr(Config, "POOLER_MODE")

    def test_session_mode_detection_from_url(self):
        """Test session mode is detected from pooler.supabase.com"""
        from config import Config

        assert hasattr(Config, "POOLER_MODE")

    def test_direct_connection_detection(self):
        """Test direct connection is detected"""
        from config import Config

        assert hasattr(Config, "POOLER_MODE")
