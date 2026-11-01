"""Protection against forged cross-site requests (CSRF).

The browser sends our session cookie with every request to this host, even
when the request was started by another website (a hidden form that posts to
/admin/users/<id>/role, say). So a state-changing request must also prove it
came from one of our own pages. Our pages carry a random per-session token;
a foreign page cannot read it.

What is checked, on POST / PUT / PATCH / DELETE:
- a ``csrf_token`` form field or an ``X-CSRFToken`` header must match the
  token stored in the session (constant-time compare);
- except for ``application/json`` bodies. A browser will not send JSON to
  another origin without that origin's permission first (CORS preflight), and
  this app grants none to foreign origins, so JSON requests cannot be forged
  from another site. This keeps scripted API clients (FL sites, the
  plugin-to-plugin export call) working without a token.

Templates get ``csrf_token()`` and ``csrf_input()``; the two base layouts add
the token to every same-origin ``fetch``/XHR request automatically.

Switched off when ``TESTING`` is set unless ``CSRF_ENABLED`` is set
explicitly, so the existing test-suite form posts keep working.
"""

import hmac
import secrets

from flask import abort, current_app, request, session
from markupsafe import Markup, escape

_SESSION_KEY = "_csrf_token"
_UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def csrf_token():
    """Return this session's token, creating it on first use."""
    token = session.get(_SESSION_KEY)
    if not token:
        token = secrets.token_urlsafe(32)
        session[_SESSION_KEY] = token
    return token


def csrf_input():
    """Hidden form field carrying the token, for ``<form method="post">``."""
    return Markup(
        f'<input type="hidden" name="csrf_token" value="{escape(csrf_token())}">'
    )


def _enabled():
    cfg = current_app.config
    return cfg.get("CSRF_ENABLED", not cfg.get("TESTING", False))


def _check():
    if request.method not in _UNSAFE_METHODS or not _enabled():
        return
    if request.mimetype == "application/json":
        return
    expected = session.get(_SESSION_KEY)
    sent = request.headers.get("X-CSRFToken") or request.form.get("csrf_token")
    if not expected or not sent or not hmac.compare_digest(expected, sent):
        abort(400, description="Missing or invalid CSRF token. Reload the page and try again.")


def init_csrf(app):
    app.before_request(_check)
    app.jinja_env.globals["csrf_token"] = csrf_token
    app.jinja_env.globals["csrf_input"] = csrf_input
