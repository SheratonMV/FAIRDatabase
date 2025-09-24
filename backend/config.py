from dotenv import load_dotenv

load_dotenv()
import os

import psycopg2

from flask import current_app, g
from flask_limiter import Limiter
from psycopg2 import OperationalError, Error
from flask_limiter.util import get_remote_address
from supabase import Client, ClientOptions, create_client


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
        app.config.setdefault(
            "SUPABASE_SERVICE_ROLE_KEY", Config.SUPABASE_SERVICE_ROLE_KEY
        )
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


def init_db():
    """Establish a connection to the PostgreSQL database.
    ---
    tags:
      - database_connection
    responses:
      200:
        description: Database connection established successfully
        schema:
          type: string
          example: "Connection to PostgreSQL established."
      500:
        description: Failed to connect to the database
        schema:
          type: string
          example: "Database connection failed."
    """
    try:
        config = current_app.config
        print(
            f"Connecting to DB on {config['POSTGRES_HOST']}:{config['POSTGRES_PORT']}"
        )
        conn = psycopg2.connect(
            host=config["POSTGRES_HOST"],
            port=config["POSTGRES_PORT"],
            user=config["POSTGRES_USER"],
            password=config["POSTGRES_SECRET"],
            database=config["POSTGRES_DB_NAME"],
        )
        return conn
    except OperationalError as e:
        print(f"[ERROR] Failed to connect to DB: {e}")
        return None


def get_db():
    """Get the database connection for the current request."""
    if "db" not in g:
        g.db = init_db()
    return g.db


def teardown_db(exception):
    """Close the database connection after the request is finished."""
    db = g.pop("db", None)

    if db is not None:
        db.close()


supabase_extension = Supabase()
limiter = Limiter(get_remote_address, default_limits=["100 per minute", "50 per second"])
