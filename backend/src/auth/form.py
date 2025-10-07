"""Authentication form handlers for login and registration."""

import time

from flask import (
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from supabase import AuthApiError, AuthRetryableError, AuthWeakPasswordError

from config import supabase_extension


class LoginHandler:
    """
    Handle user login using Supabase authentication.

    ---
    tags:
    - auth
    summary: Handle login with provided credentials and set user session.
    """

    def __init__(self):
        try:
            self.email = request.form.get("email", "")
            self.password = request.form.get("password", "")
        except (AttributeError, KeyError):
            self.email = self.password = None

    def handle_auth(self):
        """
        Authenticate user using Supabase with provided email and password.

        ---
        tags:
        - auth
        summary: Verify login credentials and redirect to dashboard on success.
        responses:
            200:
                description: Successful login
            400:
                description: Invalid login credentials or missing fields
        """
        if not self.email or not self.password:
            flash("Email and password are required", "danger")
            return render_template("auth/login.html"), 400
        try:
            signup_resp = supabase_extension.client.auth.sign_in_with_password(
                {"email": self.email, "password": self.password}
            )
        except AuthApiError:
            flash("Invalid email or password", "danger")
            return render_template("auth/login.html"), 400

        session["email"] = self.email
        session["user"] = signup_resp.user.id

        return redirect(url_for("dashboard_routes.dashboard"))


class RegisterHandler:
    """
    Handle user registration using Supabase with retry mechanism.

    ---
    tags:
    - auth
    summary: Register new user account and handle possible Supabase errors.
    """

    def __init__(self):
        """
        Extract email and password from the registration form request.
        """
        self.email = request.form.get("email")
        self.password = request.form.get("password")

    def _try_sign_up_with_retries(self, max_attempts=3, delay_seconds=2):
        """
        Attempt user registration via Supabase with retry mechanism.

        ---
        tags:
        - auth
        summary: Attempt to sign up a new user with retries on transient errors.
        parameters:
        - name: max_attempts
            in: query
            type: integer
            required: false
            description: Maximum number of retry attempts on transient errors.
        - name: delay_seconds
            in: query
            type: integer
            required: false
            description: Seconds to wait between each retry attempt.
        """
        attempt = 0
        while attempt < max_attempts:
            try:
                response = supabase_extension.client.auth.sign_up(
                    {"email": self.email, "password": self.password}
                )
                return response
            except AuthRetryableError:
                attempt += 1
                time.sleep(delay_seconds)
            except Exception as e:
                raise e
        raise AuthRetryableError("Max retries exceeded.")

    def handle_auth(self):
        """
        Handle the full registration flow including error management.

        ---
        tags:
        - auth
        summary: Register user, handle errors, and redirect to login on success.
        responses:
            200:
                description: Registration successful
            400:
                description: Validation or API error
            409:
                description: User already exists
            503:
                description: Retryable error - service unavailable
            500:
                description: Unexpected error
        """
        if not self.email or not self.password:
            flash("Email and password are required", "error")
            return render_template("auth/register.html", email=self.email), 400

        try:
            signup_resp = self._try_sign_up_with_retries()
        except AuthWeakPasswordError as e:
            flash(f"Registration failed. {str(e)}", "error")
            return render_template("auth/register.html", email=self.email), 400
        except AuthApiError as e:
            if e.code == "user_already_exists":
                flash("An account with this email already exists.", "error")
                return render_template("auth/register.html", email=self.email), 409
            else:
                flash(f"Registration failed: {e.message}", "error")
            return render_template("auth/register.html", email=self.email), 400
        except AuthRetryableError:
            flash("Temporary issue with signup. Please try again shortly.", "error")
            return render_template("auth/register.html", email=self.email), 503
        except Exception as e:
            flash(f"An unexpected error occurred during registration: {e}", "error")
            return render_template("auth/register.html", email=self.email), 500

        if signup_resp is None:
            flash("Signup failed. Please try again later.", "error")
            return render_template("auth/register.html", email=self.email), 500

        return redirect(url_for("auth_routes.login"))
