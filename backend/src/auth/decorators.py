from functools import wraps
from flask import g, session, redirect, url_for, request, jsonify


def login_required():
    """
    Protects a route by checking for a logged-in user.
    If `api=True`, returns a JSON 401 error instead of redirect.
    """

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not session.get("user"):
                return redirect(url_for("main_routes.index"))
            g.user = session["user"]
            return f(*args, **kwargs)

        return decorated_function

    return decorator
