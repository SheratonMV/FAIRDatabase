"""Pytest fixtures for the vertical FL plugin test suite.

The plugin tests live outside the project ``tests/`` tree, so that conftest
is not a parent and its shared app/client/auth fixtures must be imported
explicitly (see plugins/pbpk/tests/conftest.py for the same pattern).
"""
import pytest

from tests.conftest import *  # noqa: F401,F403 — shared app/client/auth fixtures


@pytest.fixture(scope="module")
def curator_user(app):
    """Registers, logs in, and assigns the curator role — once per test module.

    VFL mutation routes (create_task, register_party, submit_psi,
    submit_embeddings, run_simulation) require admin or curator — the
    default role (visualizer) fails RBAC, so tests exercising POST routes
    need this instead of logged_in_user.

    Module-scoped: /auth/login is rate-limited to 5/minute, and one login
    per class would exceed that across this file's test classes.
    """
    from app import get_db
    from config import supabase_extension

    client = app.test_client()
    TEST_EMAIL = "vfl_test_user@test.com"
    TEST_PASSWORD = "aBJ3%!fj0_f42h2pvw3"

    client.post("/auth/register", data={"email": TEST_EMAIL, "password": TEST_PASSWORD},
                follow_redirects=True)
    client.post("/auth/login", data={"email": TEST_EMAIL, "password": TEST_PASSWORD},
                follow_redirects=True)

    with app.app_context():
        users = supabase_extension.client.auth.admin.list_users()
        user = next((u for u in users if u.email == TEST_EMAIL), None)
        if not user:
            pytest.fail("VFL curator test user not found in Supabase.")

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


@pytest.fixture
def vfl_task_cleanup(app):
    """Collects task IDs created during a test and deletes them on teardown.
    Deleting the task row cascades to parties/psi/rounds (see sql/001_schema.sql)."""
    task_ids: list[str] = []

    yield task_ids

    with app.app_context():
        from app import get_db
        db = get_db()
        cur = db.cursor()
        if task_ids:
            cur.execute("DELETE FROM _fd.vfl_tasks WHERE id = ANY(%s::uuid[])", (task_ids,))
        db.commit()
        cur.close()
