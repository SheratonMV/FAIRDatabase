import pytest
import os

from app import create_app, get_db
from config import supabase_extension
from dotenv import load_dotenv


TEST_EMAIL = "test_user_1@test.com"
TEST_PASSWORD = "aBJ3%!fj0_f42h2pvw3"
TEST_FAULTY_REPEAT = TEST_PASSWORD + " "


def pytest_configure():
    """
    Configure pytest with default test constants for email, username, and password.
    ---
    tags:
      - config
    parameters:
      - name: TEST_EMAIL
        in: config
        type: string
        required: true
        description: Default email used in the tests.
      - name: TEST_USERNAME
        in: config
        type: string
        required: true
        description: Default username used in the tests.
      - name: TEST_PASSWORD
        in: config
        type: string
        required: true
        description: Default password used in the tests.
    """
    pytest.TEST_EMAIL = TEST_EMAIL
    pytest.TEST_PASSWORD = TEST_PASSWORD
    pytest.TEST_FAULTY_REPEAT = TEST_FAULTY_REPEAT


@pytest.fixture(scope="module")
def app():
    """
    Create and configure a Flask app instance for testing.

    This fixture creates a new app configured for testing with a test
    database. It pushes an application context to enable use of Flask's
    `current_app` and `g`. The database connection is established before
    yielding the app, allowing tests to access the app and DB.

    """
    load_dotenv(os.path.join(os.path.dirname(__file__), ".env.test"))

    path = os.path.join(os.path.dirname(__file__), "uploads")
    app = create_app(os.getenv("POSTGRES_DB_NAME"))
    app.config.update(
        {
            "TESTING": True,
            "SERVER_NAME": "localhost",
            "UPLOAD_FOLDER": path,
            "SUPABASE_URL": os.getenv("SUPABASE_URL"),
            "SUPABASE_KEY": os.getenv("SUPABASE_KEY"),
            "SUPABASE_SERVICE_ROLE_KEY": os.getenv("SUPABASE_SERVICE_ROLE_KEY"),
            "POSTGRES_DB_NAME": os.getenv("POSTGRES_DB_NAME"),
            "POSTGRES_USER": os.getenv("POSTGRES_USER"),
            "POSTGRES_SECRET": os.getenv("POSTGRES_SECRET"),
            "POSTGRES_PORT": os.getenv("POSTGRES_PORT"),
            "POSTGRES_HOST": os.getenv("POSTGRES_HOST"),
        }
    )

    yield app


@pytest.fixture(scope="class")
def rollback(app):
    """
    Provide a callable to manually rollback DB changes during a test.
    """
    with app.app_context():
        conn = get_db()
        cursor = conn.cursor()

        def do_rollback():
            conn.rollback()

        yield do_rollback

        cursor.close()
        conn.close()


@pytest.fixture(scope="class")
def client(app):
    """
    Create a test client for the app.

    This fixture provides a test client that can be used to make HTTP
    requests to the app in tests.
    """
    return app.test_client()


@pytest.fixture()
def runner(app):
    """
    Create a CLI runner for the app.

    This fixture provides a test CLI runner that can be used to invoke
    command line interface (CLI) commands in tests.
    """
    return app.test_cli_runner()


@pytest.fixture
def load_test_file():
    """
    Load the contents of a test file from the data directory.

    This fixture enables loading files like `users.json`, `sample.csv`,
    etc., for use within your tests. It provides an easy way to read and
    retrieve the contents of files stored in the `tests/data/` directory.

    ---
    tags:
      - test_file_loader
    parameters:
      - name: filename
        in: query
        type: string
        required: true
        description: The name of the test file to load.
      - name: mode
        in: query
        type: string
        required: false
        description: The mode in which to open the file. Defaults to 'r'.
    returns:
      - type: string
        description: The contents of the test file as a string.
    """

    def _loader(filename="df.csv", mode="r"):
        file_path = os.path.join(os.path.dirname(__file__), filename)

        with open(file_path, "rb") as f:
            return f.read()

    return _loader


@pytest.fixture(scope="class")
def registered_user(app, client):
    """
    Registers a test user via the /auth/register route, simulates Supabase signup,
    and cleans up the user from Supabase after the test class.
    ---
    tags:
      - auth
    parameters:
      - name: email
        in: query
        type: string
        required: true
        description: Email address used to register the user.
      - name: username
        in: query
        type: string
        required: true
        description: Username used to register the user.
      - name: password
        in: query
        type: string
        required: true
        description: Password used to register the user.
    responses:
      200:
        description: Registration successful.
      400:
        description: Registration failed (e.g., duplicate email).
    """
    response = client.post(
        "/auth/register",
        data={"email": TEST_EMAIL, "password": TEST_PASSWORD},
        follow_redirects=True,
    )

    with app.app_context():
        user_list = supabase_extension.client.auth.admin.list_users()
        user = next((u for u in user_list if u.email == TEST_EMAIL), None)
        if user is None:
            pytest.fail("Test user was not created in Supabase")

        yield response, user

        supabase_extension.client.auth.admin.delete_user(user.id)


@pytest.fixture(scope="class")
def logged_in_user(app, client):
    """
    Logs in a test user via the /auth/login route and starts a session.

    This fixture ensures that a user is first registered, then successfully
    authenticated through the login route. It yields the test client and user object,
    and cleans up the user from Supabase after the test class.

    ---
    tags:
      - auth
    parameters:
      - name: email
        in: query
        type: string
        required: true
        description: Email address used to log in the user.
      - name: password
        in: query
        type: string
        required: true
        description: Password used to log in the user.
    responses:
      200:
        description: Login successful and session established.
      400:
        description: Login failed due to missing credentials.
      401:
        description: Login failed due to invalid credentials.
    """
    client.post(
        "/auth/register",
        data={"email": TEST_EMAIL, "password": TEST_PASSWORD},
        follow_redirects=True,
    )

    response = client.post(
        "/auth/login",
        data={"email": TEST_EMAIL, "password": TEST_PASSWORD},
        follow_redirects=True,
    )

    assert response.status_code == 200

    with app.app_context():
        users = supabase_extension.client.auth.admin.list_users()
        user = next((u for u in users if u.email == TEST_EMAIL), None)
        if not user:
            pytest.fail("Logged-in user not found in Supabase.")

        yield client, user

        supabase_extension.client.auth.admin.delete_user(user.id)


@pytest.fixture
def logout_user(client):
    """
    Logs out the user.
    ---
    tags:
      - auth
    responses:
      302:
        description: Logout successful (user redirected).
    """
    response = client.get("/auth/logout")

    assert response.status_code == 204
    yield response
