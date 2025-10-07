import os
from pathlib import Path
from typing import Any, TypeVar

from dotenv import load_dotenv

# Load .env from backend directory (works regardless of CWD)
backend_dir = Path(__file__).parent
dotenv_path = backend_dir / ".env"
load_dotenv(dotenv_path, override=True)

from flask import current_app, g
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from psycopg2 import OperationalError
from psycopg2.pool import ThreadedConnectionPool
from supabase import Client, ClientOptions, create_client

# Type variable for generic RPC return types
T = TypeVar('T')


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
          UPLOAD_FOLDER:
            type: string
            description: Local path where uploaded files will be stored.
            example: "./uploads"
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
    UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", "./uploads")
    ALLOWED_EXTENSIONS = {"csv"}
    MAX_CONTENT_LENGTH = 16 * 1000 * 10000
    SUPABASE_URL = os.getenv("SUPABASE_URL")
    SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    POSTGRES_HOST = os.getenv("POSTGRES_HOST")
    POSTGRES_PORT = os.getenv("POSTGRES_PORT")
    POSTGRES_USER = os.getenv("POSTGRES_USER")
    POSTGRES_SECRET = os.getenv("POSTGRES_SECRET")
    POSTGRES_DB_NAME = os.getenv("POSTGRES_DB_NAME")


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
        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        """
        Initializes the Flask app with necessary configurations and registers the teardown method.
        """
        app.config.setdefault("SUPABASE_URL", Config.SUPABASE_URL)
        app.config.setdefault("SUPABASE_SERVICE_ROLE_KEY", Config.SUPABASE_SERVICE_ROLE_KEY)
        app.teardown_appcontext(self.teardown)

    def teardown(self, exception):
        """
        Clean up the Supabase client after each request by popping it from Flask's `g` object.
        """
        g.pop("supabase_client", None)

    @property
    def client(self) -> Client:
        """
        Lazily initialize the Supabase client and return it. This client is used for interacting with Supabase's
        REST API and Auth services.
        """
        if "supabase_client" not in g:
            url = current_app.config["SUPABASE_URL"]
            key = current_app.config.get("SUPABASE_SERVICE_ROLE_KEY")

            if not url or not key:
                raise RuntimeError("Supabase URL or KEY not configured properly.")

            options = self.client_options
            if options and not isinstance(options, ClientOptions):
                options = ClientOptions(**options)

            try:
                g.supabase_client = create_client(url, key, options=options)
            except Exception as e:
                current_app.logger.error(f"Supabase client init error: {e}")
                raise

        return g.supabase_client

    def get_user(self):
        """
        Retrieve the currently authenticated user from Supabase.
        """
        try:
            return self.client.auth.get_user()
        except Exception as e:
            current_app.logger.error(f"Error getting user: {e}")
            return None

    def safe_rpc_call(self, function_name: str, params: dict | None = None) -> list[Any] | bool | Any:
        """
        Execute Supabase RPC with consistent error handling.

        This method automatically handles .execute() chaining and provides
        centralized exception handling for all RPC calls. Prefer this over
        direct client.rpc() calls for consistency.

        See DATABASE.md "Query Execution Convention" for more details.

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
        from src.exceptions import GenericExceptionHandler

        try:
            response = self.client.rpc(function_name, params or {}).execute()
            return response.data
        except Exception as e:
            current_app.logger.error(f"RPC {function_name} failed: {e}")
            raise GenericExceptionHandler(
                f"Database operation failed: {str(e)}", status_code=500
            ) from e


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


supabase_extension = Supabase()
limiter = Limiter(get_remote_address, default_limits=["100 per minute", "50 per second"])
