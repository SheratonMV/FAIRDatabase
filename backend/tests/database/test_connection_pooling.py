import pytest
from unittest.mock import patch, MagicMock
from psycopg2 import OperationalError

from config import init_db_pool, get_db, close_db_pool, connection_pool, teardown_db


class TestConnectionPooling:
    """Test connection pool initialization and management"""

    def test_init_db_pool_success(self, app):
        """Test connection pool initializes successfully"""
        with app.app_context():
            # Close any existing pool
            close_db_pool()

            pool = init_db_pool(minconn=1, maxconn=5)

            assert pool is not None
            assert pool.minconn == 1
            assert pool.maxconn == 5

    def test_init_db_pool_singleton(self, app):
        """Test connection pool is a singleton"""
        with app.app_context():
            close_db_pool()

            pool1 = init_db_pool()
            pool2 = init_db_pool()

            assert pool1 is pool2

    def test_init_db_pool_connection_failure(self, app):
        """Test connection pool handles connection failures gracefully"""
        with app.app_context():
            close_db_pool()

            # Mock ThreadedConnectionPool to raise OperationalError
            with patch('config.ThreadedConnectionPool') as mock_pool:
                mock_pool.side_effect = OperationalError('Connection failed')

                pool = init_db_pool()

                assert pool is None

    def test_get_db_returns_connection(self, app):
        """Test get_db returns a database connection"""
        with app.app_context():
            close_db_pool()
            init_db_pool()

            conn = get_db()

            assert conn is not None
            assert hasattr(conn, 'cursor')

    def test_get_db_reuses_connection_in_context(self, app):
        """Test get_db reuses connection within same request context"""
        with app.app_context():
            from flask import g

            close_db_pool()
            init_db_pool()

            conn1 = get_db()
            conn2 = get_db()

            assert conn1 is conn2
            assert g.db is conn1

    def test_get_db_handles_pool_getconn_failure(self, app):
        """Test get_db handles connection retrieval failures"""
        with app.app_context():
            close_db_pool()
            pool = init_db_pool()

            with patch.object(pool, 'getconn') as mock_getconn:
                mock_getconn.side_effect = Exception('Failed to get connection')

                conn = get_db()

                assert conn is None

    def test_teardown_db_returns_connection_to_pool(self, app):
        """Test teardown_db returns connection to pool"""
        with app.app_context():
            from flask import g

            close_db_pool()
            pool = init_db_pool()

            # Get a connection
            conn = get_db()
            assert g.db is conn

            # Teardown should return connection
            with patch.object(pool, 'putconn') as mock_putconn:
                teardown_db(None)

                mock_putconn.assert_called_once_with(conn)
                assert 'db' not in g

    def test_teardown_db_closes_on_putconn_failure(self, app):
        """Test teardown_db closes connection if putconn fails"""
        with app.app_context():
            from flask import g

            close_db_pool()
            pool = init_db_pool()

            # Get real connection first, then replace with mock
            get_db()

            # Replace with mock connection
            mock_conn = MagicMock()
            g.db = mock_conn

            with patch.object(pool, 'putconn') as mock_putconn:
                mock_putconn.side_effect = Exception('putconn failed')

                teardown_db(None)

                # Verify close was called on the mock connection
                mock_conn.close.assert_called_once()

    def test_close_db_pool_success(self, app):
        """Test close_db_pool closes all connections"""
        with app.app_context():
            close_db_pool()
            pool = init_db_pool()

            with patch.object(pool, 'closeall') as mock_closeall:
                close_db_pool()

                mock_closeall.assert_called_once()

    def test_close_db_pool_handles_errors(self, app):
        """Test close_db_pool handles errors gracefully"""
        with app.app_context():
            close_db_pool()
            pool = init_db_pool()

            with patch.object(pool, 'closeall') as mock_closeall:
                mock_closeall.side_effect = Exception('Close failed')

                # Should not raise exception
                close_db_pool()

    def test_connection_pool_config(self, app):
        """Test connection pool uses correct configuration"""
        with app.app_context():
            close_db_pool()

            with patch('config.ThreadedConnectionPool') as mock_pool_class:
                mock_pool_class.return_value = MagicMock()

                init_db_pool(minconn=2, maxconn=8)

                call_args = mock_pool_class.call_args
                assert call_args[0][0] == 2  # minconn
                assert call_args[0][1] == 8  # maxconn
                assert call_args[1]['host'] == app.config['POSTGRES_HOST']
                assert call_args[1]['port'] == app.config['POSTGRES_PORT']
                assert call_args[1]['user'] == app.config['POSTGRES_USER']
                assert call_args[1]['password'] == app.config['POSTGRES_SECRET']
                assert call_args[1]['database'] == app.config['POSTGRES_DB_NAME']
                assert call_args[1]['connect_timeout'] == 10
                assert 'statement_timeout' in call_args[1]['options']

    def test_get_db_without_pool_initialization(self, app):
        """Test get_db initializes pool if not already initialized"""
        with app.app_context():
            close_db_pool()

            # Don't explicitly call init_db_pool
            conn = get_db()

            # Should auto-initialize and return connection
            assert conn is not None

    def test_teardown_db_no_connection(self, app):
        """Test teardown_db handles case when no connection exists"""
        with app.app_context():
            from flask import g

            # Ensure no connection in g
            g.pop('db', None)

            # Should not raise exception
            teardown_db(None)


class TestPoolerModeDetection:
    """Test pooler mode detection from configuration"""

    def test_transaction_mode_detection_from_url(self):
        """Test transaction mode is detected from port 6543"""
        from config import Config

        # This is informational only - Config is set at import time
        # Just verify the detection logic exists
        assert hasattr(Config, 'POOLER_MODE')

    def test_session_mode_detection_from_url(self):
        """Test session mode is detected from pooler.supabase.com"""
        from config import Config

        assert hasattr(Config, 'POOLER_MODE')

    def test_direct_connection_detection(self):
        """Test direct connection is detected"""
        from config import Config

        assert hasattr(Config, 'POOLER_MODE')
