"""Flask blueprint routes for visualization features: exploratory data analysis
   and visualization of datasets."""

from flask import (
    render_template,
    session,
    request,
    Blueprint,
)

from src.auth.decorators import login_required

routes = Blueprint("visualization_routes", __name__)


@routes.route("/")
@login_required()
def visualization():
    """
    Main visualization page for exploratory data analysis.
    ---
    tags:
      - visualization
    parameters:
      - name: user_email
        in: session
        type: string
        required: true
        description: Email of the logged-in user.
    responses:
      200:
        description: Renders the visualization page.
      401:
        description: Error response if the user is not logged in.
    """
    user_email = session.get("email", "")
    current_path = request.path

    return (
        render_template(
            "/visualization/visualization.html",
            user_email=user_email,
            current_path=current_path,
        ),
        200,
    )
