"""Main application routes handling user landing and dashboard rendering based
on authentication."""

from flask import Blueprint, render_template, session

routes = Blueprint("main_routes", __name__)


@routes.route("/")
def index():
    """
    Route to render the appropriate homepage based on user authentication status.
    ---
    tags:
      - main
    responses:
      200:
        description: Renders the dashboard page if the user is logged in, otherwise renders the login page.
      401:
        description: Error response if the user is not authenticated (handled by redirect to login page).
    """
    if "user" in session:
        return render_template("/dashboard/dashboard.html"), 200
    return render_template("/auth/login.html"), 200
