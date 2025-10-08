import os
import time
from functools import lru_cache
from pathlib import Path
from typing import Any, TypeVar
from urllib.parse import urlparse

from dotenv import load_dotenv

# Load .env from backend directory (works regardless of CWD)
backend_dir = Path(__file__).parent
dotenv_path = backend_dir / ".env"
load_dotenv(dotenv_path, override=True)

from flask import current_app, g
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from httpx import ConnectError, RequestError, TimeoutException
from psycopg2 import OperationalError
from psycopg2.pool import ThreadedConnectionPool
from supabase import AsyncClient, Client, ClientOptions, acreate_client, create_client
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

# Type variable for generic RPC return types
T = TypeVar("T")


class Config:
    """Application configuration settings.
    ---
    tags:
      - configuration
    definitions:
      Config:
        type: object
        properties:
          SECRET_KEY:
            type: string
            description: Secret key used for securing the Flask application.
            example: "supersecret"
          ALLOWED_EXTENSIONS:
            type: array
            items:
              type: string
            description: Allowed file types for uploads.
            example: ["csv"]
          MAX_CONTENT_LENGTH:
            type: integer
            description: Maximum file upload size in bytes.
            example: 160000000
          SUPABASE_URL:
            type: string
            description: Supabase project URL.
            example: "https://xyzcompany.supabase.co"
          SUPABASE_KEY:
            type: string
            description: Supabase API key.
            example: "your-public-api-key"
          POSTGRES_NAME:
            type: string
            description: PostgreSQL database name.
          POSTGRES_USER:
            type: string
            description: PostgreSQL username.
          POSTGRES_PASSWORD:
            type: string
            description: PostgreSQL user password.
    """

    ENV = os.getenv("ENV")
    SECRET_KEY = os.getenv("SECRET_KEY", "supersecret")
    ALLOWED_EXTENSIONS = {"csv"}
    MAX_CONTENT_LENGTH = 16 * 1000 * 10000
    SUPABASE_URL = os.getenv("SUPABASE_URL")
    SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")
    SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

    # PostgreSQL Configuration
    # Supports both POSTGRES_URL (for pooled connections) and individual variables
    _postgres_url = os.getenv("POSTGRES_URL")
    _pooler_mode = None  # Track detected pooler mode

    if _postgres_url:
        # Parse connection URL (e.g., postgresql://user:pass@host:port/dbname?pgbouncer=true)
        _parsed = urlparse(_postgres_url)
        POSTGRES_HOST = _parsed.hostname
        POSTGRES_PORT = str(_parsed.port) if _parsed.port else "5432"
        POSTGRES_USER = _parsed.username
        POSTGRES_SECRET = _parsed.password
        POSTGRES_DB_NAME = _parsed.path.lstrip("/")

        # Validate pooler mode from connection string
        if _parsed.port == 6543 or ":6543" in _postgres_url:
            _pooler_mode = "transaction"
            print("[WARNING] Transaction mode pooler detected (port 6543)")
            print("[WARNING] Transaction mode is not recommended for Flask applications")
            print("[WARNING] Consider using Session mode (port 5432) for better compatibility")
        elif _parsed.port == 5432 or ":5432" in _postgres_url:
            if "pooler.supabase.com" in _postgres_url:
                _pooler_mode = "session"
                print("[INFO] Session mode pooler detected (port 5432) - optimal for Flask")
            else:
                _pooler_mode = "direct"
                print("[INFO] Direct connection detected (port 5432)")
        else:
            print(f"[WARNING] Unusual port detected: {_parsed.port}")
    else:
        # Fall back to individual environment variables
        POSTGRES_HOST = os.getenv("POSTGRES_HOST")
        POSTGRES_PORT = os.getenv("POSTGRES_PORT")
        POSTGRES_USER = os.getenv("POSTGRES_USER")
        POSTGRES_SECRET = os.getenv("POSTGRES_SECRET")
        POSTGRES_DB_NAME = os.getenv("POSTGRES_DB_NAME")

        # Check port from individual config
        if POSTGRES_PORT:
            if POSTGRES_PORT == "6543":
                _pooler_mode = "transaction"
                print("[WARNING] Transaction mode pooler detected (port 6543)")
                print("[WARNING] Not recommended for Flask - use port 5432 for Session mode")
            elif POSTGRES_PORT == "5432":
                _pooler_mode = "direct"
                print("[INFO] Standard PostgreSQL port detected (5432)")

    POOLER_MODE = _pooler_mode


class Supabase:
    """Supabase integration class.
    ---
    tags:
      - supabase_client
    definitions:
      Supabase:
        type: object
        properties:
          client:
            type: object
            description: Lazy-loaded Supabase client instance.
          client_options:
            type: object
            description: Custom client configuration options for Supabase.
    methods:
      - name: init_app
        description: Initialize Supabase configuration with a Flask app.
        parameters:
          - name: app
            in: body
            required: true
            type: object
            description: Flask app instance.
      - name: teardown
        description: Clean up the Supabase client from Flask app context.
        parameters:
          - name: exception
            in: body
            required: false
            type: string
            description: Any exception thrown during request processing.
      - name: get_user
        description: Get the currently authenticated Supabase user.
        responses:
          200:
            description: Successfully retrieved user.
          500:
            description: Failed to retrieve user from Supabase.
    """

    def __init__(self, app=None, client_options: dict | None = None):
        """
        Initialize the SupabaseClient instance.
        """
        self.client_options = client_options
        self._client = None
        self._service_role_client = None
        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        """
        Initializes the Flask app with necessary configurations and creates application-level client singletons.

        This creates clients once during app initialization rather than per-request,
        improving performance by reusing the same client instances across all requests.
        """
        app.config.setdefault("SUPABASE_URL", Config.SUPABASE_URL)
        app.config.setdefault("SUPABASE_ANON_KEY", Config.SUPABASE_ANON_KEY)
        app.config.setdefault("SUPABASE_SERVICE_ROLE_KEY", Config.SUPABASE_SERVICE_ROLE_KEY)

        # Create application-level client singletons
        url = app.config["SUPABASE_URL"]
        anon_key = app.config.get("SUPABASE_ANON_KEY")
        service_key = app.config.get("SUPABASE_SERVICE_ROLE_KEY")

        if url and anon_key:
            options = self.client_options
            if options and not isinstance(options, ClientOptions):
                options = ClientOptions(**options)

            try:
                self._client = create_client(url, anon_key, options=options)
                app.logger.info("Supabase anon client initialized (app-level singleton)")
            except Exception as e:
                app.logger.error(f"Failed to initialize Supabase anon client: {e}")
                raise

        if url and service_key:
            service_role_options = {
                "postgrest_client_timeout": 180,
                "storage_client_timeout": 180,
                "auto_refresh_token": False,
                "persist_session": False,
            }
            options = ClientOptions(**service_role_options)

            try:
                self._service_role_client = create_client(url, service_key, options=options)
                app.logger.info("Supabase service role client initialized (app-level singleton)")
            except Exception as e:
                app.logger.error(f"Failed to initialize Supabase service role client: {e}")
                raise

        app.teardown_appcontext(self.teardown)

    def teardown(self, exception):
        """
        Clean up async clients after each request.

        Note: Sync clients are now app-level singletons and don't need per-request cleanup.
        Only async clients stored in g need cleanup.
        """
        g.pop("supabase_async_client", None)
        g.pop("supabase_async_service_role_client", None)

    @property
    def client(self) -> Client:
        """
        Return the application-level Supabase client singleton with anon key.

        This client uses the anon key and respects Row Level Security (RLS) policies.
        Use this for most operations including auth, RPC calls, and data access.

        The client is created once during app initialization and reused across all requests,
        providing better performance than per-request client creation.

        For admin operations that need to bypass RLS, use service_role_client instead.
        """
        if self._client is None:
            raise RuntimeError("Supabase client not initialized. Call init_app() first.")
        return self._client

    @property
    def service_role_client(self) -> Client:
        """
        Return the application-level Supabase client singleton with service role key.

        WARNING: This client bypasses Row Level Security (RLS) and has full admin privileges.
        Only use this for specific admin operations that require elevated permissions.

        The client is created once during app initialization and reused across all requests.

        For regular operations, use the standard client property instead.
        """
        if self._service_role_client is None:
            raise RuntimeError(
                "Supabase service role client not initialized. Call init_app() first."
            )
        return self._service_role_client

    @property
    async def async_client(self) -> AsyncClient:
        """
        Lazily initialize the async Supabase client with anon key and return it.

        This async client uses the anon key and respects Row Level Security (RLS) policies.
        Use this for async operations including auth, RPC calls, and data access.

        For admin operations that need to bypass RLS, use async_service_role_client instead.

        Example:
            from flask import Flask
            from config import supabase_extension

            app = Flask(__name__)
            supabase_extension.init_app(app)

            @app.route('/async-example')
            async def async_example():
                client = await supabase_extension.async_client
                response = await client.rpc('function_name', {}).execute()
                return response.data
        """
        if "supabase_async_client" not in g:
            url = current_app.config["SUPABASE_URL"]
            key = current_app.config.get("SUPABASE_ANON_KEY")

            if not url or not key:
                raise RuntimeError("Supabase URL or ANON_KEY not configured properly.")

            options = self.client_options
            if options and not isinstance(options, ClientOptions):
                options = ClientOptions(**options)

            try:
                g.supabase_async_client = await acreate_client(url, key, options=options)
            except Exception as e:
                current_app.logger.error(f"Supabase async client init error: {e}")
                raise

        return g.supabase_async_client

    @property
    async def async_service_role_client(self) -> AsyncClient:
        """
        Lazily initialize the async Supabase client with service role key and return it.

        WARNING: This client bypasses Row Level Security (RLS) and has full admin privileges.
        Only use this for specific admin operations that require elevated permissions.

        For regular operations, use the async_client property instead.

        Example:
            from flask import Flask
            from config import supabase_extension

            app = Flask(__name__)
            supabase_extension.init_app(app)

            @app.route('/admin-async-example')
            async def admin_async_example():
                client = await supabase_extension.async_service_role_client
                response = await client.rpc('admin_function', {}).execute()
                return response.data
        """
        if "supabase_async_service_role_client" not in g:
            url = current_app.config["SUPABASE_URL"]
            key = current_app.config.get("SUPABASE_SERVICE_ROLE_KEY")

            if not url or not key:
                raise RuntimeError("Supabase URL or SERVICE_ROLE_KEY not configured properly.")

            # Service role client should not auto-refresh tokens or persist sessions
            service_role_options = {
                "postgrest_client_timeout": 180,
                "storage_client_timeout": 180,
                "auto_refresh_token": False,  # No token refresh for service role
                "persist_session": False,  # No session persistence for service role
            }

            options = ClientOptions(**service_role_options)

            try:
                g.supabase_async_service_role_client = await acreate_client(
                    url, key, options=options
                )
            except Exception as e:
                current_app.logger.error(f"Supabase async service role client init error: {e}")
                raise

        return g.supabase_async_service_role_client

    def get_user(self):
        """
        Retrieve the currently authenticated user from Supabase.
        """
        try:
            return self.client.auth.get_user()
        except Exception as e:
            current_app.logger.error(f"Error getting user: {e}")
            return None

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((ConnectError, TimeoutException, RequestError)),
        reraise=True,
    )
    def safe_rpc_call(
        self, function_name: str, params: dict | None = None
    ) -> list[Any] | bool | Any:
        """
        Execute Supabase RPC with consistent error handling and automatic retry for transient failures.

        This method automatically handles .execute() chaining and provides
        centralized exception handling for all RPC calls. Prefer this over
        direct client.rpc() calls for consistency.

        Retry Logic:
        - Retries up to 3 times for transient network failures (connection errors, timeouts, request errors)
        - Uses exponential backoff (2s, 4s, 8s) between retries
        - Does NOT retry permanent errors (API errors, HTTP status errors, etc.)

        For better type safety, use type hints at the call site:
            data: list[TableNameResult] = supabase_extension.safe_rpc_call('get_all_tables')

        See src/types.py for available TypedDict definitions.
        ---
        tags:
          - supabase_rpc
        parameters:
          - name: function_name
            type: string
            required: true
            description: Name of the RPC function to call.
          - name: params
            type: object
            required: false
            description: Dictionary of parameters to pass to the RPC function.
        returns:
          type: list | bool | any
          description: response.data if successful (typically list, but may be bool for functions like table_exists)
        raises:
          GenericExceptionHandler: with appropriate status code and error message

        Example:
            data: list[TableNameResult] = supabase_extension.safe_rpc_call('get_all_tables')
            exists: bool = supabase_extension.safe_rpc_call('table_exists', {'p_table_name': 'my_table'})
        """
        from httpx import HTTPStatusError
        from postgrest.exceptions import APIError

        from src.exceptions import GenericExceptionHandler

        try:
            response = self.client.rpc(function_name, params or {}).execute()
            return response.data
        except APIError as e:
            # PostgREST API errors with detailed context
            current_app.logger.error(
                f"RPC {function_name} API error - Code: {e.code}, Message: {e.message}, "
                f"Hint: {e.hint}, Details: {e.details}"
            )

            # Handle specific PostgreSQL error codes
            if e.code == "42883":  # undefined_function
                raise GenericExceptionHandler(
                    f"Function '{function_name}' not found in database", status_code=404
                ) from e
            elif e.code == "PGRST204":  # No rows returned
                return []
            elif e.code == "42P01":  # undefined_table
                raise GenericExceptionHandler(
                    f"Table not found for function '{function_name}'", status_code=404
                ) from e
            elif e.code in ("42501", "42502"):  # insufficient_privilege
                raise GenericExceptionHandler(
                    f"Permission denied for function '{function_name}'", status_code=403
                ) from e
            elif e.code == "23505":  # unique_violation
                raise GenericExceptionHandler(
                    f"Duplicate entry: {e.message or 'Record already exists'}", status_code=409
                ) from e
            elif e.code == "23503":  # foreign_key_violation
                raise GenericExceptionHandler(
                    f"Foreign key constraint violation: {e.message}", status_code=409
                ) from e
            else:
                # Generic database error with preserved context
                error_msg = f"Database error in '{function_name}': {e.message or str(e)}"
                if e.hint:
                    error_msg += f" (Hint: {e.hint})"
                raise GenericExceptionHandler(error_msg, status_code=500) from e
        except TimeoutException as e:
            current_app.logger.error(f"RPC {function_name} timeout: {e}")
            raise GenericExceptionHandler(
                f"Request timeout for function '{function_name}'. Operation took too long.",
                status_code=504,
            ) from e
        except ConnectError as e:
            current_app.logger.error(f"RPC {function_name} connection error: {e}")
            raise GenericExceptionHandler(
                f"Cannot connect to database for function '{function_name}'. Service may be unavailable.",
                status_code=503,
            ) from e
        except HTTPStatusError as e:
            current_app.logger.error(f"RPC {function_name} HTTP error: {e.response.status_code}")
            raise GenericExceptionHandler(
                f"HTTP error {e.response.status_code} for function '{function_name}'",
                status_code=e.response.status_code,
            ) from e
        except RequestError as e:
            current_app.logger.error(f"RPC {function_name} request error: {e}")
            raise GenericExceptionHandler(
                f"Network error for function '{function_name}': {str(e)}", status_code=503
            ) from e
        except Exception as e:
            # Catch-all for unexpected errors
            current_app.logger.error(
                f"RPC {function_name} unexpected error: {type(e).__name__}: {e}"
            )
            raise GenericExceptionHandler(
                f"Unexpected error in '{function_name}': {str(e)}", status_code=500
            ) from e

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((ConnectError, TimeoutException, RequestError)),
        reraise=True,
    )
    async def async_safe_rpc_call(
        self, function_name: str, params: dict | None = None
    ) -> list[Any] | bool | Any:
        """
        Execute Supabase RPC asynchronously with consistent error handling and automatic retry for transient failures.

        This method automatically handles .execute() chaining and provides
        centralized exception handling for all async RPC calls. Use this for
        I/O-bound operations that can benefit from async execution.

        Retry Logic:
        - Retries up to 3 times for transient network failures (connection errors, timeouts, request errors)
        - Uses exponential backoff (2s, 4s, 8s) between retries
        - Does NOT retry permanent errors (API errors, HTTP status errors, etc.)

        For better type safety, use type hints at the call site:
            data: list[TableNameResult] = await supabase_extension.async_safe_rpc_call('get_all_tables')

        See src/types.py for available TypedDict definitions.
        ---
        tags:
          - supabase_rpc
          - async
        parameters:
          - name: function_name
            type: string
            required: true
            description: Name of the RPC function to call.
          - name: params
            type: object
            required: false
            description: Dictionary of parameters to pass to the RPC function.
        returns:
          type: list | bool | any
          description: response.data if successful (typically list, but may be bool for functions like table_exists)
        raises:
          GenericExceptionHandler: with appropriate status code and error message

        Example:
            # Flask 3.1+ supports async routes
            @app.route('/async-data')
            async def async_data():
                data: list[TableNameResult] = await supabase_extension.async_safe_rpc_call('get_all_tables')
                return jsonify(data)
        """
        from httpx import HTTPStatusError
        from postgrest.exceptions import APIError

        from src.exceptions import GenericExceptionHandler

        try:
            client = await self.async_client
            response = await client.rpc(function_name, params or {}).execute()
            return response.data
        except APIError as e:
            # PostgREST API errors with detailed context
            current_app.logger.error(
                f"Async RPC {function_name} API error - Code: {e.code}, Message: {e.message}, "
                f"Hint: {e.hint}, Details: {e.details}"
            )

            # Handle specific PostgreSQL error codes
            if e.code == "42883":  # undefined_function
                raise GenericExceptionHandler(
                    f"Function '{function_name}' not found in database", status_code=404
                ) from e
            elif e.code == "PGRST204":  # No rows returned
                return []
            elif e.code == "42P01":  # undefined_table
                raise GenericExceptionHandler(
                    f"Table not found for function '{function_name}'", status_code=404
                ) from e
            elif e.code in ("42501", "42502"):  # insufficient_privilege
                raise GenericExceptionHandler(
                    f"Permission denied for function '{function_name}'", status_code=403
                ) from e
            elif e.code == "23505":  # unique_violation
                raise GenericExceptionHandler(
                    f"Duplicate entry: {e.message or 'Record already exists'}", status_code=409
                ) from e
            elif e.code == "23503":  # foreign_key_violation
                raise GenericExceptionHandler(
                    f"Foreign key constraint violation: {e.message}", status_code=409
                ) from e
            else:
                # Generic database error with preserved context
                error_msg = f"Database error in '{function_name}': {e.message or str(e)}"
                if e.hint:
                    error_msg += f" (Hint: {e.hint})"
                raise GenericExceptionHandler(error_msg, status_code=500) from e
        except TimeoutException as e:
            current_app.logger.error(f"Async RPC {function_name} timeout: {e}")
            raise GenericExceptionHandler(
                f"Request timeout for function '{function_name}'. Operation took too long.",
                status_code=504,
            ) from e
        except ConnectError as e:
            current_app.logger.error(f"Async RPC {function_name} connection error: {e}")
            raise GenericExceptionHandler(
                f"Cannot connect to database for function '{function_name}'. Service may be unavailable.",
                status_code=503,
            ) from e
        except HTTPStatusError as e:
            current_app.logger.error(
                f"Async RPC {function_name} HTTP error: {e.response.status_code}"
            )
            raise GenericExceptionHandler(
                f"HTTP error {e.response.status_code} for function '{function_name}'",
                status_code=e.response.status_code,
            ) from e
        except RequestError as e:
            current_app.logger.error(f"Async RPC {function_name} request error: {e}")
            raise GenericExceptionHandler(
                f"Network error for function '{function_name}': {str(e)}", status_code=503
            ) from e
        except Exception as e:
            # Catch-all for unexpected errors
            current_app.logger.error(
                f"Async RPC {function_name} unexpected error: {type(e).__name__}: {e}"
            )
            raise GenericExceptionHandler(
                f"Unexpected error in '{function_name}': {str(e)}", status_code=500
            ) from e


# ============================================================================
# Metadata Query Caching
# ============================================================================
# Implements time-based in-memory caching for frequently called metadata RPC
# functions to reduce unnecessary database load.

# Cache TTL in seconds (default: 60 seconds / 1 minute)
METADATA_CACHE_TTL = 60


def _get_cache_key() -> int:
    """
    Generate a cache key based on current time rounded to cache TTL.

    This ensures cache entries are automatically invalidated after TTL expires
    by creating a new cache key for each time window.

    Returns:
        int: Cache key representing current time window
    """
    return int(time.time() // METADATA_CACHE_TTL)


@lru_cache(maxsize=128)
def _cached_get_all_tables(cache_key: int, schema_name: str = "_realtime") -> list[Any]:
    """
    Internal cached wrapper for get_all_tables RPC call.

    This function should not be called directly. Use get_cached_tables() instead.

    Args:
        cache_key: Time-based cache key for automatic TTL
        schema_name: Database schema name (default: '_realtime')

    Returns:
        list[TableNameResult]: List of table names in the schema
    """
    # Note: supabase_extension will be available at runtime
    # This is called after module initialization
    return supabase_extension.safe_rpc_call("get_all_tables", {"schema_name": schema_name})


@lru_cache(maxsize=256)
def _cached_get_table_columns(
    cache_key: int, table_name: str, schema_name: str = "_realtime"
) -> list[Any]:
    """
    Internal cached wrapper for get_table_columns RPC call.

    This function should not be called directly. Use get_cached_table_columns() instead.

    Args:
        cache_key: Time-based cache key for automatic TTL
        table_name: Name of the table to get columns for
        schema_name: Database schema name (default: '_realtime')

    Returns:
        list[ColumnInfoResult]: List of column information for the table
    """
    return supabase_extension.safe_rpc_call(
        "get_table_columns", {"p_table_name": table_name, "schema_name": schema_name}
    )


def get_cached_tables(schema_name: str = "_realtime") -> list[Any]:
    """
    Get all tables in schema with automatic time-based caching.

    This function caches results for METADATA_CACHE_TTL seconds to reduce
    database load from repeated calls. Use this instead of direct RPC calls
    to safe_rpc_call('get_all_tables') in read-heavy routes.

    Args:
        schema_name: Database schema name (default: '_realtime')

    Returns:
        list[TableNameResult]: List of table names in the schema

    Example:
        from config import get_cached_tables

        # Returns cached result if available within TTL window
        tables = get_cached_tables()
    """
    cache_key = _get_cache_key()
    return _cached_get_all_tables(cache_key, schema_name)


def get_cached_table_columns(table_name: str, schema_name: str = "_realtime") -> list[Any]:
    """
    Get table column information with automatic time-based caching.

    This function caches results for METADATA_CACHE_TTL seconds to reduce
    database load from repeated calls. Use this instead of direct RPC calls
    to safe_rpc_call('get_table_columns') in read-heavy routes.

    Args:
        table_name: Name of the table to get columns for
        schema_name: Database schema name (default: '_realtime')

    Returns:
        list[ColumnInfoResult]: List of column information for the table

    Example:
        from config import get_cached_table_columns

        # Returns cached result if available within TTL window
        columns = get_cached_table_columns('my_table_p1')
    """
    cache_key = _get_cache_key()
    return _cached_get_table_columns(cache_key, table_name, schema_name)


def invalidate_metadata_cache():
    """
    Manually clear all metadata caches.

    Call this function after operations that modify database schema or table structure:
    - After CSV file uploads (new tables created)
    - After table deletions
    - After schema migrations

    This ensures subsequent queries return fresh data instead of stale cache.

    Example:
        from config import invalidate_metadata_cache

        # After uploading new data
        upload_csv_file(file)
        invalidate_metadata_cache()  # Clear cache so new tables appear immediately
    """
    _cached_get_all_tables.cache_clear()
    _cached_get_table_columns.cache_clear()


# Global connection pool
connection_pool = None


def init_db_pool(minconn=1, maxconn=10):
    """Initialize the PostgreSQL connection pool.
    ---
    tags:
      - database_connection
    parameters:
      - name: minconn
        in: query
        type: integer
        description: Minimum number of connections in the pool
        default: 1
      - name: maxconn
        in: query
        type: integer
        description: Maximum number of connections in the pool
        default: 10
    responses:
      200:
        description: Connection pool initialized successfully
        schema:
          type: object
          example: {"status": "Pool initialized"}
      500:
        description: Failed to initialize connection pool
        schema:
          type: string
          example: "Connection pool initialization failed."
    """
    global connection_pool

    if connection_pool is None:
        try:
            config = current_app.config
            print(
                f"Initializing connection pool for DB on {config['POSTGRES_HOST']}:{config['POSTGRES_PORT']}"
            )
            connection_pool = ThreadedConnectionPool(
                minconn,
                maxconn,
                host=config["POSTGRES_HOST"],
                port=config["POSTGRES_PORT"],
                user=config["POSTGRES_USER"],
                password=config["POSTGRES_SECRET"],
                database=config["POSTGRES_DB_NAME"],
                connect_timeout=10,  # 10 second connection timeout
                options="-c statement_timeout=60000",  # 60 second query timeout
            )
            print(f"[INFO] Connection pool initialized with {minconn}-{maxconn} connections")
        except OperationalError as e:
            print(f"[ERROR] Failed to initialize connection pool: {e}")
            connection_pool = None

    return connection_pool


def get_db():
    """Get a database connection from the pool for the current request."""
    if "db" not in g:
        pool = init_db_pool()
        if pool is not None:
            try:
                g.db = pool.getconn()
            except Exception as e:
                print(f"[ERROR] Failed to get connection from pool: {e}")
                g.db = None
        else:
            g.db = None
    return g.db


def teardown_db(exception):
    """Return the database connection to the pool after the request is finished."""
    db = g.pop("db", None)

    if db is not None and connection_pool is not None:
        try:
            connection_pool.putconn(db)
        except Exception as e:
            print(f"[ERROR] Failed to return connection to pool: {e}")
            # If putconn fails, close the connection manually
            try:
                db.close()
            except:
                pass


def close_db_pool():
    """Close all connections in the pool and reset the pool.

    This is useful for testing when database configuration changes,
    or during application shutdown.
    """
    global connection_pool

    if connection_pool is not None:
        try:
            connection_pool.closeall()
            print("[INFO] Connection pool closed successfully")
        except Exception as e:
            print(f"[ERROR] Failed to close connection pool: {e}")
        finally:
            connection_pool = None


# Configure Supabase client with timeouts
# Using 180s timeout for test suite compatibility
#
# Token Management in Flask Backend:
# - auto_refresh_token=False: Token refresh is handled manually in @login_required decorator
#   (both proactive refresh before expiry and reactive refresh on validation failure)
# - persist_session=False: Session persistence is managed by Flask's session system,
#   not by Supabase client (no browser localStorage/sessionStorage in backend context)
#
# These settings match the service role client configuration and are appropriate for
# server-side usage where each request is isolated and sessions don't persist across
# HTTP requests within the Supabase client itself.
supabase_client_options = {
    "postgrest_client_timeout": 180,  # 180 second timeout for PostgREST requests
    "storage_client_timeout": 180,  # 180 second timeout for Storage requests
    "auto_refresh_token": False,  # Manual refresh handled by @login_required decorator
    "persist_session": False,  # Flask sessions handle persistence, not client
}

supabase_extension = Supabase(client_options=supabase_client_options)
limiter = Limiter(get_remote_address, default_limits=["100 per minute", "50 per second"])


def validate_config():
    """
    Validate that all required configuration variables are set.

    Raises:
        ValueError: If any required configuration variables are missing or empty.
    """
    required = {
        "SUPABASE_URL": Config.SUPABASE_URL,
        "SUPABASE_ANON_KEY": Config.SUPABASE_ANON_KEY,
        "POSTGRES_HOST": Config.POSTGRES_HOST,
        "POSTGRES_DB_NAME": Config.POSTGRES_DB_NAME,
    }

    missing = [k for k, v in required.items() if not v or not v.strip()]

    if missing:
        raise ValueError(f"Missing required configuration: {', '.join(missing)}")
