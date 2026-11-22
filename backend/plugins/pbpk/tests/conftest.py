"""Pytest fixtures for the PBPK plugin test suite.

Inherits the shared app/client/auth fixtures from the project-level
``tests/conftest.py`` (the plugin tests live outside the ``tests/`` tree, so
that conftest is not a parent and must be imported explicitly), then adds the
PBPK-specific role/cleanup fixtures.
"""
import pytest

from app import get_db
from tests.conftest import *  # noqa: F401,F403 — shared app/client/auth fixtures


@pytest.fixture(scope="module")
def pbpk_client(app):
    """Test client with session seeded as a curator user for stress tests.

    POST /model/parameter-sets and POST /model/runs require admin or curator
    role. This fixture registers, logs in, and assigns the curator role so
    that RBAC gates pass during the stress test suite.
    """
    from config import supabase_extension

    TEST_EMAIL = "pbpk_stress@test.com"
    TEST_PASSWORD = "aBJ3%!fj0_f42h2pvw3"

    client = app.test_client()
    client.post(
        "/auth/register",
        data={"email": TEST_EMAIL, "password": TEST_PASSWORD},
        follow_redirects=True,
    )
    client.post(
        "/auth/login",
        data={"email": TEST_EMAIL, "password": TEST_PASSWORD},
        follow_redirects=True,
    )

    with app.app_context():
        users = supabase_extension.client.auth.admin.list_users()
        user = next((u for u in users if u.email == TEST_EMAIL), None)

        if user:
            db = get_db()
            cur = db.cursor()
            cur.execute(
                "INSERT INTO _fd.user_roles (user_id, role) VALUES (%s, 'curator') "
                "ON CONFLICT (user_id) DO UPDATE SET role = 'curator'",
                (str(user.id),),
            )
            db.commit()
            cur.close()

    yield client, TEST_EMAIL

    with app.app_context():
        if user:
            supabase_extension.client.auth.admin.delete_user(user.id)


@pytest.fixture(scope="class")
def curator_user(app, client):
    """Registers, logs in, and assigns the curator role to the test user.

    POST /model/parameter-sets and POST /model/runs require admin or curator
    role. Use this fixture instead of logged_in_user for tests that call
    those write endpoints.
    """
    from config import supabase_extension

    TEST_EMAIL = "test_user_1@test.com"
    TEST_PASSWORD = "aBJ3%!fj0_f42h2pvw3"

    client.post(
        "/auth/register",
        data={"email": TEST_EMAIL, "password": TEST_PASSWORD},
        follow_redirects=True,
    )
    client.post(
        "/auth/login",
        data={"email": TEST_EMAIL, "password": TEST_PASSWORD},
        follow_redirects=True,
    )

    with app.app_context():
        users = supabase_extension.client.auth.admin.list_users()
        user = next((u for u in users if u.email == TEST_EMAIL), None)
        if not user:
            pytest.fail("Curator test user not found in Supabase.")

        db = get_db()
        cur = db.cursor()
        cur.execute(
            "INSERT INTO _fd.user_roles (user_id, role) VALUES (%s, 'curator') "
            "ON CONFLICT (user_id) DO UPDATE SET role = 'curator'",
            (str(user.id),),
        )
        db.commit()
        cur.close()

        yield client, user

        supabase_extension.client.auth.admin.delete_user(user.id)


@pytest.fixture(scope="module")
def pbpk_cleanup(app):
    """Collects IDs created during stress tests and deletes them on teardown."""
    ps_ids: list[int] = []
    run_ids: list[int] = []

    yield ps_ids, run_ids

    with app.app_context():
        db = get_db()
        cur = db.cursor()
        if run_ids:
            cur.execute(
                "DELETE FROM _fd.pbpk_simulation_runs WHERE id = ANY(%s)", (run_ids,)
            )
        if ps_ids:
            # Also remove runs the test did not get to record (it failed
            # before appending them, or they were warm-up runs); otherwise
            # they block the parameter-set delete below.
            cur.execute(
                "DELETE FROM _fd.pbpk_simulation_runs WHERE param_set_id = ANY(%s)",
                (ps_ids,),
            )
            cur.execute(
                "DELETE FROM _fd.pbpk_parameter_sets WHERE id = ANY(%s)", (ps_ids,)
            )
        db.commit()
        cur.close()
