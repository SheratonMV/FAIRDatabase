"""Tests for the /fl blueprint — real engine, no upstream mocks."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import pytest
from unittest.mock import patch, MagicMock
import numpy as np
from kernel.crypto import encrypt_weights


SECRET = "test-secret"


class TestFLTaskCreation:
    def test_create_task_missing_fields_returns_400(self, client):
        resp = client.post("/fl/tasks", json={}, content_type="application/json")
        assert resp.status_code in (302, 400)  # 302 = not logged in redirect

    def test_ui_redirects_when_not_logged_in(self, client):
        resp = client.get("/fl/ui")
        assert resp.status_code == 302

    def test_get_nonexistent_task_returns_404(self, client):
        resp = client.get("/fl/tasks/00000000-0000-0000-0000-000000000000")
        # 302 if auth wall, 404 if authenticated
        assert resp.status_code in (302, 404)


class TestFLInputValidation:
    def test_gradients_endpoint_requires_encrypted_payload(self, client):
        resp = client.post(
            "/fl/tasks/fake-id/rounds/1/gradients",
            json={"weights": [1.0, 2.0]},
            content_type="application/json",
        )
        assert resp.status_code in (302, 400)

    def test_list_rounds_nonexistent_task(self, client):
        resp = client.get("/fl/tasks/00000000-0000-0000-0000-000000000000/rounds")
        assert resp.status_code in (302, 404)

    def test_get_model_nonexistent_task(self, client):
        resp = client.get("/fl/tasks/00000000-0000-0000-0000-000000000000/model")
        assert resp.status_code in (302, 404)


class TestLegacyRedirect:
    def test_legacy_url_redirects(self, client):
        resp = client.get("/federated/federated_learning/federated_learning")
        assert resp.status_code in (301, 302)


class TestVerticalFLAvailability:
    """Covers the guard that keeps this dashboard usable when vertical_fl is
    not mounted.

    Rendered through a bare Jinja environment rather than the shared ``app``
    fixture: that fixture skips whenever Supabase/Postgres are unreachable,
    which is every CI run, so these assertions would never execute there. The
    page only reads ``vfl_available``, so a stub base template is enough.
    """

    @staticmethod
    def _render(vfl_available):
        import jinja2

        templates = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates"
        )
        env = jinja2.Environment(
            loader=jinja2.ChoiceLoader([
                jinja2.FileSystemLoader(templates),
                jinja2.DictLoader(
                    {"dashboard/layout.html": "{% block content %}{% endblock %}"}
                ),
            ]),
            autoescape=True,
        )
        return env.get_template("horizontal_fl/federated_learning.html").render(
            tasks=[], user_email=None, current_path="/fl/ui",
            vfl_available=vfl_available,
        )

    def test_vertical_tab_hidden_when_plugin_absent(self):
        html = self._render(vfl_available=False)
        assert 'id="btn-vertical"' not in html
        assert 'id="panel-vertical"' not in html
        assert "const VFL_AVAILABLE = false" in html

    def test_vertical_tab_shown_when_plugin_present(self):
        html = self._render(vfl_available=True)
        assert 'id="btn-vertical"' in html
        assert 'id="panel-vertical"' in html
        assert "const VFL_AVAILABLE = true" in html

    def test_guard_key_matches_vertical_fl_blueprint_name(self):
        """federated_ui derives vfl_available from this blueprint name, so a
        rename in the sibling plugin would silently hide the tab."""
        plugin = pytest.importorskip("plugins.vertical_fl.plugin")
        assert plugin.PLUGIN.blueprint.name == "vertical_fl_routes"
