from datetime import UTC
from functools import wraps

from flask import g, redirect, session, url_for


def login_required():
    """
    Protects a route by validating the user's JWT token with Supabase.
    Automatically refreshes expired tokens using the refresh token.
    Redirects to login page if validation fails.
    """

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            access_token = session.get("access_token")
            refresh_token = session.get("refresh_token")

            # No tokens in session, redirect to login
            if not access_token:
                session.clear()
                return redirect(url_for("main_routes.index"))

            from config import supabase_extension

            try:
                # Validate JWT token with Supabase
                user_response = supabase_extension.client.auth.get_user(jwt=access_token)
                g.user = user_response.user.id
                return f(*args, **kwargs)
            except Exception:
                # Token validation failed, try to refresh
                if refresh_token:
                    try:
                        refresh_resp = supabase_extension.client.auth.refresh_session(refresh_token)

                        # Update session with new tokens
                        session["access_token"] = refresh_resp.session.access_token
                        session["refresh_token"] = refresh_resp.session.refresh_token
                        session["expires_at"] = refresh_resp.session.expires_at
                        session["user"] = refresh_resp.user.id

                        # Set user for this request
                        g.user = refresh_resp.user.id
                        return f(*args, **kwargs)
                    except Exception:
                        # Refresh failed, clear session and redirect
                        session.clear()
                        return redirect(url_for("main_routes.index"))
                else:
                    # No refresh token, clear session and redirect
                    session.clear()
                    return redirect(url_for("main_routes.index"))

        return decorated_function

    return decorator


def refresh_session_if_needed():
    """
    Check if the current session's access token is expired or about to expire,
    and refresh it using the refresh token if necessary.

    This should be called in before_request or in the login_required decorator
    to ensure users maintain valid sessions.
    """

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not session.get("user"):
                # No user logged in, skip refresh
                return f(*args, **kwargs)

            access_token = session.get("access_token")
            refresh_token = session.get("refresh_token")
            expires_at = session.get("expires_at")

            if not all([access_token, refresh_token, expires_at]):
                # Missing token data, user needs to re-login
                session.clear()
                return redirect(url_for("main_routes.index"))

            # Check if token is expired or will expire soon (within 5 minutes)
            from datetime import datetime

            try:
                expires_datetime = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
                now = datetime.now(UTC)
                time_until_expiry = (expires_datetime - now).total_seconds()

                # Refresh if token expires in less than 5 minutes (300 seconds)
                if time_until_expiry < 300:
                    from config import supabase_extension

                    try:
                        # Refresh the session
                        refresh_resp = supabase_extension.client.auth.refresh_session(refresh_token)

                        # Update session with new tokens
                        session["access_token"] = refresh_resp.session.access_token
                        session["refresh_token"] = refresh_resp.session.refresh_token
                        session["expires_at"] = refresh_resp.session.expires_at
                    except Exception:
                        # Refresh failed, clear session and redirect to login
                        session.clear()
                        return redirect(url_for("main_routes.index"))
            except (ValueError, AttributeError):
                # Invalid expires_at format, clear session
                session.clear()
                return redirect(url_for("main_routes.index"))

            return f(*args, **kwargs)

        return decorated_function

    return decorator
