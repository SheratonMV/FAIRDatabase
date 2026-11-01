from functools import wraps
from flask import g, session, redirect, url_for, abort

from config import get_db


DEFAULT_ROLE = "visualizer"


def _load_role(user_id: str) -> str:
    """Look up the caller's role from _fd.user_roles.

    A missing row means the auth.users trigger has not run yet, so the user
    gets the least-privileged default role. A failed lookup (no connection,
    missing table, query error) is different: we do not know who the caller
    is, so we refuse the request (503) instead of guessing a role.
    """
    db = get_db()
    if db is None:
        abort(503, description="Role lookup unavailable.")
    try:
        with db.cursor() as cur:
            cur.execute(
                "SELECT role::text FROM _fd.user_roles WHERE user_id = %s",
                (user_id,),
            )
            row = cur.fetchone()
    except Exception:
        db.rollback()
        abort(503, description="Role lookup unavailable.")
    return row[0] if row else DEFAULT_ROLE


def login_required(*allowed_roles):
    """Protect a route by checking for a logged-in user (and optional role).

    Usage:
        @login_required()                      -> any authenticated user
        @login_required("admin", "curator")    -> only listed roles; otherwise 403

    Unauthenticated callers are redirected to the landing page. Sets
    ``g.user`` (uuid) and ``g.role`` (str) for the duration of the request.
    """

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not session.get("user"):
                return redirect(url_for("main_routes.index"))
            g.user = session["user"]
            if "role" not in g:
                g.role = _load_role(g.user)
            if allowed_roles and g.role not in allowed_roles:
                abort(403)
            return f(*args, **kwargs)

        return decorated_function

    return decorator
