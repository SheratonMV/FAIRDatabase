"""Authentication routes for login, logout, and registration."""

from flask import (
    session,
    request,
    render_template,
    redirect,
    request,
    Blueprint,
    url_for,
)

from config import limiter
from .form import LoginHandler, RegisterHandler

routes = Blueprint("auth_routes", __name__)


@routes.route("/login", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def login():
    """
    Authenticate user and start a session.
    ---
    tags:
      - auth
    summary: Log in a user using email and password.
    parameters:
      - name: email
        in: formData
        type: string
        required: true
        description: User's email address.
      - name: password
        in: formData
        type: string
        required: true
        description: User's password.
    responses:
      200:
        description: Redirect to dashboard upon successful login.
      400:
        description: Missing email or password in request.
      401:
        description: Invalid email or password.
      429:
        description: Too many requests (rate-limited).
    """
    handle = LoginHandler()

    if request.method == "GET":
        return render_template("auth/login.html")

    if request.method == "POST":
        return handle.handle_auth()


@routes.route("/logout")
def logout():
    """
    Log out the current user and reset session state.

    ---
    tags:
      - auth
    summary: Log out the current user and clear related session variables.
    responses:
      302:
        description: Redirect to the home page after successful logout.
    """
    session.pop("user", None)
    session.pop("uploaded_filepath", None)
    uploaded = False
    columns_dropped = False
    missing_values_reviewed = False
    quasi_identifiers_selected = False
    current_quasi_identifier = False
    all_steps_completed = False
    session["uploaded"] = uploaded
    session["columns_dropped"] = columns_dropped
    session["missing_values_reviewed"] = missing_values_reviewed
    session["quasi_identifiers_selected"] = quasi_identifiers_selected
    session["current_quasi_identifier"] = current_quasi_identifier
    session["all_steps_completed"] = all_steps_completed

    return redirect(url_for("main_routes.index"))


@routes.route("/register", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def register():
    """
    Handle user registration via Supabase authentication.

    ---
    tags:
      - auth
    summary: Register a new user using email and password.
    parameters:
      - name: email
        in: formData
        type: string
        required: true
        description: User's email address.
      - name: password
        in: formData
        type: string
        required: true
        description: User's desired password.
    responses:
      201:
        description: User created successfully.
      400:
        description: Missing form data or weak password.
      429:
        description: Too many requests (rate-limited).
      500:
        description: Internal server error (including retryable errors).
    """
    handle = RegisterHandler()

    if request.method == "GET":
        return render_template("auth/register.html")

    if request.method == "POST":
        return handle.handle_auth()
