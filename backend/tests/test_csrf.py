"""Forged-request protection (src/csrf.py), on a bare Flask app so it runs
without Supabase/Postgres."""

import re

import pytest
from flask import Flask, render_template_string

from src.csrf import init_csrf


@pytest.fixture
def client():
    app = Flask(__name__)
    app.config.update(SECRET_KEY="k" * 40, CSRF_ENABLED=True)
    init_csrf(app)

    @app.route("/form")
    def form():
        return render_template_string(
            '<meta name="csrf-token" content="{{ csrf_token() }}">'
            '<form method="post">{{ csrf_input() }}</form>'
        )

    @app.route("/act", methods=["POST"])
    def act():
        return "done"

    return app.test_client()


def _token(client):
    html = client.get("/form").get_data(as_text=True)
    return re.search(r'content="([^"]+)"', html).group(1)


def test_form_post_without_token_refused(client):
    client.get("/form")
    assert client.post("/act", data={"x": "1"}).status_code == 400


def test_form_post_with_wrong_token_refused(client):
    _token(client)
    assert client.post("/act", data={"csrf_token": "forged"}).status_code == 400


def test_form_post_with_token_accepted(client):
    tok = _token(client)
    assert client.post("/act", data={"csrf_token": tok}).status_code == 200


def test_header_token_accepted(client):
    tok = _token(client)
    assert client.post("/act", headers={"X-CSRFToken": tok}).status_code == 200


def test_text_plain_body_needs_token(client):
    # A foreign page can send text/plain without a CORS preflight.
    client.get("/form")
    resp = client.post("/act", data="{}", content_type="text/plain")
    assert resp.status_code == 400


def test_json_body_passes_without_token(client):
    # Browsers preflight cross-origin JSON, so it cannot be forged; API
    # clients (FL sites, plugin-to-plugin export) rely on this.
    assert client.post("/act", json={}).status_code == 200


def test_token_from_other_session_refused(client):
    tok = _token(client)
    with client.session_transaction() as s:
        s.clear()
    client.get("/form")  # new session, new token
    assert client.post("/act", data={"csrf_token": tok}).status_code == 400
