"""
Routes for privacy enforcement and differential privacy functionality.
"""

from flask import (
    request,
    render_template,
    request,
    Blueprint,
)

from src.auth.decorators import login_required
from .form import DifferentialPrivacyHandler, PrivacyProcessingHandler


routes = Blueprint("privacy_routes", __name__)


@routes.route("/privacy_processing")
@login_required()
def privacy_processing():
    """
    Run privacy enforcement analysis on uploaded data.
    ---
    tags:
      - privacy-processing
    responses:
      200:
        description: Privacy metrics computed and rendered.
      400:
        description: File missing or session expired.
      401:
        description: User not authenticated.
    """
    handler = PrivacyProcessingHandler()
    handler.handle_p29_score()

    return render_template("/data/privacy_processing.html", **handler.ctx)


@routes.route("/differential_privacy", methods=["GET", "POST"])
@login_required()
def differential_privacy():
    """
    Add differential privacy noise to selected data columns.
    ---
    tags:
      - differential-privacy
    responses:
      200:
        description: Differential privacy form rendered or processed.
      400:
        description: File missing or invalid column selection.
      401:
        description: User not authenticated.
    """
    handler = DifferentialPrivacyHandler()

    if request.method == "POST":
        handler.handle_add_noise()

    status_code = 400 if handler.ctx.get("error") else 200
    return render_template("/privacy/differential_privacy.html", **handler.ctx), status_code
