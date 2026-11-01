"""Role x route 403 matrix.

Drives every protected blueprint route with a synthetic session and a
monkeypatched role lookup. The goal is to verify the ``@login_required``
decorator gates each route by role, independent of database state and
Supabase availability.
"""

import uuid
import pytest
from flask import g

from src.auth import decorators


class _StubCursor:
    def execute(self, *a, **kw): pass
    def fetchall(self): return []
    def fetchone(self): return None
    def __enter__(self): return self
    def __exit__(self, *a): return False


class _StubDB:
    def cursor(self): return _StubCursor()
    def commit(self): pass
    def rollback(self): pass
    def close(self): pass


PROTECTED_ROUTES = [
    # path,                     method, allowed_roles
    ("/dashboard",              "GET",  None),  # any authenticated
    ("/dashboard/upload",       "GET",  ("admin", "curator")),
    ("/dashboard/update",       "GET",  ("admin", "curator")),
    ("/dashboard/search",       "GET",  ("admin", "curator", "accessor")),
    ("/data/data_generalization", "GET", ("admin", "curator")),
    ("/admin/users",            "GET",  ("admin",)),
    ("/visualization/dataset/some_table", "GET", ("admin", "curator", "accessor")),
]

ALL_ROLES = ("admin", "curator", "accessor", "visualizer")


@pytest.fixture(scope="module", autouse=True)
def _stub_g_db(app):
    """Inject a stub g.db so route handlers don't blow up on a None DB."""
    @app.before_request
    def _set_stub_db():
        g.db = _StubDB()
    yield


@pytest.fixture
def role_session(client, monkeypatch):
    """Return a helper that primes the session and the role lookup."""

    def _setup(role):
        monkeypatch.setattr(decorators, "_load_role", lambda _uid: role)
        with client.session_transaction() as s:
            s.clear()
            s["user"] = str(uuid.uuid4())
            s["email"] = f"{role}@test.com"

    return _setup


class TestRouteRoleMatrix:
    @pytest.mark.parametrize("path,method,allowed", PROTECTED_ROUTES)
    @pytest.mark.parametrize("role", ALL_ROLES)
    def test_role_route_matrix(self, client, role_session, path, method, allowed, role):
        role_session(role)
        resp = client.open(path, method=method)
        if allowed is None or role in allowed:
            assert resp.status_code != 403, (
                f"{role} unexpectedly forbidden from {method} {path}"
            )
        else:
            assert resp.status_code == 403, (
                f"{role} should be forbidden from {method} {path} "
                f"(got {resp.status_code})"
            )

    def test_unauthenticated_redirects(self, client):
        with client.session_transaction() as s:
            s.clear()
        resp = client.get("/admin/users", follow_redirects=False)
        assert resp.status_code in (301, 302)


class TestDatasetVisualizationAccess:
    """The per-dataset plot shows every sample of one dataset. A curator who
    does not own it (stub DB: no ownership row) must be turned away before
    the backend calls the edge function with the service key."""

    def test_unowned_dataset_never_reaches_edge_function(
        self, client, role_session, monkeypatch
    ):
        from src.visualization import routes as viz_routes

        calls = []
        monkeypatch.setattr(
            viz_routes, "call_visualization_edge_function",
            lambda *a, **kw: calls.append(a) or {"success": True},
        )
        monkeypatch.setattr(viz_routes, "validate_table_exists", lambda *a: True)
        role_session("curator")
        resp = client.get("/visualization/dataset/someone_elses_table")
        assert resp.status_code == 302
        assert calls == []
