from datetime import UTC
from functools import wraps

from flask import g, redirect, session, url_for


def login_required():
    """
    Protects a route by validating the user's JWT token with Supabase.
    Proactively refreshes tokens before expiration (within 5 minutes).
    Redirects to login page if validation fails.
    """

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            access_token = session.get("access_token")
            refresh_token = session.get("refresh_token")
            expires_at = session.get("expires_at")

            # No tokens in session, redirect to login
            if not access_token:
                session.clear()
                return redirect(url_for("main_routes.index"))

            from config import supabase_extension

            # Proactive token refresh: check if token expires soon (within 5 minutes)
            if expires_at and refresh_token:
                try:
                    from datetime import datetime

                    expires_datetime = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
                    now = datetime.now(UTC)
                    time_until_expiry = (expires_datetime - now).total_seconds()

                    # Refresh proactively if token expires in less than 5 minutes (300 seconds)
                    if time_until_expiry < 300:
                        try:
                            refresh_resp = supabase_extension.client.auth.refresh_session(
                                refresh_token
                            )

                            # Update session with new tokens
                            session["access_token"] = refresh_resp.session.access_token
                            session["refresh_token"] = refresh_resp.session.refresh_token
                            session["expires_at"] = refresh_resp.session.expires_at
                            session["user"] = refresh_resp.user.id

                            # Update access_token for validation below
                            access_token = refresh_resp.session.access_token
                            g.user = refresh_resp.user.id
                        except Exception:
                            # Proactive refresh failed, will try reactive refresh on validation failure
                            pass
                except (ValueError, AttributeError):
                    # Invalid expires_at format, continue with validation
                    pass

            # Validate JWT token with Supabase
            try:
                user_response = supabase_extension.client.auth.get_user(jwt=access_token)
                g.user = user_response.user.id
                return f(*args, **kwargs)
            except Exception:
                # Token validation failed, try reactive refresh as fallback
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
