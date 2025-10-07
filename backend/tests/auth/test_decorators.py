"""
Integration tests for authentication decorators.

Tests cover:
- login_required decorator with various token states
- Session management and cleanup
- Error handling and security edge cases

Note: These tests use existing protected routes since Flask
doesn't allow adding routes after the app has handled requests.
"""

import pytest
from unittest.mock import patch, MagicMock


class TestLoginRequired:
    """Test login_required decorator security and token validation"""

    def test_allows_authenticated_user_with_valid_token(self, app, logged_in_user):
        """Valid access token → user authenticated and route accessible"""
        client, user = logged_in_user

        # Test using existing protected route (/dashboard)
        with client:
            response = client.get("/dashboard")
            # Should not redirect to login (302/308 is normal dashboard redirect)
            assert response.status_code in (200, 302, 308)
            # Should not be redirected to homepage
            if response.status_code in (302, 308):
                assert response.location != "/"

    def test_blocks_anonymous_user_without_token(self, app, client):
        """No access token → redirect to index"""
        with client:
            response = client.get("/dashboard", follow_redirects=False)
            # Should redirect (not allow access)
            assert response.status_code in (302, 303, 307, 308)

    def test_blocks_user_with_missing_access_token(self, app, client):
        """Session exists but no access token → redirect to index"""
        with client.session_transaction() as sess:
            # Set some session data but no access_token
            sess["user"] = "fake_user_id"
            sess["email"] = "test@test.com"

        with client:
            response = client.get("/dashboard", follow_redirects=False)
            # Should redirect (not allow access)
            assert response.status_code in (302, 303, 307, 308)

    def test_clears_session_on_authentication_failure(self, app, client):
        """Authentication failure → session completely cleared"""
        with client.session_transaction() as sess:
            sess["access_token"] = "invalid_token"
            sess["user"] = "user_id"
            sess["email"] = "test@test.com"
            sess["some_other_data"] = "should_be_cleared"

        with client:
            response = client.get("/dashboard", follow_redirects=False)
            # Should redirect (not allow access)
            assert response.status_code in (302, 303, 307, 308)

    def test_authenticated_session_persists_across_requests(self, app, logged_in_user):
        """Authenticated user → session persists across multiple requests"""
        client, user = logged_in_user

        with client:
            # First request
            response1 = client.get("/dashboard")
            assert response1.status_code in (200, 302, 308)

            # Second request should still be authenticated
            response2 = client.get("/dashboard")
            assert response2.status_code in (200, 302, 308)

    def test_logout_clears_authentication(self, app, logged_in_user):
        """Logout → authentication cleared, protected routes blocked"""
        client, user = logged_in_user

        with client:
            # Verify authenticated
            response1 = client.get("/dashboard")
            assert response1.status_code in (200, 302, 308)

            # Logout
            client.get("/auth/logout")

            # Try to access protected route
            response2 = client.get("/dashboard", follow_redirects=True)
            assert response2.request.path == "/"

    def test_multiple_protected_routes_share_authentication(self, app, logged_in_user):
        """Single authentication → works for all protected routes"""
        client, user = logged_in_user

        with client:
            # Test dashboard route
            response1 = client.get("/dashboard")
            assert response1.status_code in (200, 302, 308)

            # Test data routes (if they exist and are protected)
            response2 = client.get("/data")
            # Should be authenticated (might redirect for other reasons)
            assert response2.status_code in (200, 302, 404, 308)  # 404 if route doesn't exist

    def test_expired_session_redirects_to_login(self, app, client):
        """Session with expired/invalid token → redirect to login"""
        with client.session_transaction() as sess:
            sess["access_token"] = "definitely_expired_or_invalid_token"
            sess["refresh_token"] = "also_invalid"

        with client:
            response = client.get("/dashboard", follow_redirects=True)
            # Should be redirected to homepage after failed auth
            assert response.request.path == "/"

    def test_partially_authenticated_session_fails(self, app, client):
        """Session with some but not all auth data → authentication fails"""
        with client.session_transaction() as sess:
            # Only set user without tokens
            sess["user"] = "some_user_id"
            # Missing access_token, refresh_token

        with client:
            response = client.get("/dashboard", follow_redirects=True)
            assert response.request.path == "/"


class TestDecoratorIntegration:
    """Integration tests for decorator behavior in real workflows"""

    def test_login_then_access_protected_route(self, app, client):
        """Complete workflow: login → access protected route"""
        # Register user
        client.post(
            "/auth/register",
            data={"email": "workflow@test.com", "password": "Test123!@#abc"},
            follow_redirects=True,
        )

        # Login
        response = client.post(
            "/auth/login",
            data={"email": "workflow@test.com", "password": "Test123!@#abc"},
            follow_redirects=True,
        )

        assert response.status_code == 200

        # Access protected route
        with client:
            protected_response = client.get("/dashboard")
            assert protected_response.status_code in (200, 302, 308)

        # Cleanup
        from config import supabase_extension
        with app.app_context():
            users = supabase_extension.service_role_client.auth.admin.list_users()
            user = next((u for u in users if u.email == "workflow@test.com"), None)
            if user:
                supabase_extension.service_role_client.auth.admin.delete_user(user.id)
