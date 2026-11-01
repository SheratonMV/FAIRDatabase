"""
Routes for privacy enforcement and differential privacy functionality.
"""

from flask import (
    request,
    render_template,
    Blueprint,
    g,
    jsonify,
)

from src.auth.decorators import login_required
from src.dashboard.helpers import assert_can_modify_dataset
from .form import DifferentialPrivacyHandler, PrivacyProcessingHandler
from kernel import dp_budget as fl_db


routes = Blueprint("privacy_routes", __name__)


@routes.route("/privacy_processing")
@login_required("admin", "curator", "accessor")
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
@login_required("admin", "curator")
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
    handler.prepare_columns()

    if request.method == "POST":
        handler.handle_add_noise()

    return render_template("/privacy/differential_privacy.html", **handler.ctx)


@routes.route("/fl-budget/<dataset_id>", methods=["GET"])
@login_required("admin", "curator")
def fl_budget(dataset_id):
    """
    Return the remaining DP epsilon budget for a dataset enrolled in FL.

    Budget consumption is tracked in _fd.fl_epsilon_budget and decremented
    after each FL round that uses this dataset.
    """
    # Same owner-or-admin check as enrolment, so a curator cannot probe which
    # of other users' datasets are enrolled (404 vs 200).
    try:
        with g.db.cursor() as cur:
            assert_can_modify_dataset(cur, dataset_id, g.user, g.role)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except PermissionError:
        return jsonify({"error": "Dataset not enrolled in FL"}), 404

    budget = fl_db.get_epsilon_budget(g.db, dataset_id)
    if budget is None:
        return jsonify({"error": "Dataset not enrolled in FL"}), 404

    remaining = budget["total_budget"] - budget["spent"]
    return jsonify({
        "dataset_id": dataset_id,
        "total_budget": budget["total_budget"],
        "spent": budget["spent"],
        "remaining": remaining,
        "exhausted": remaining <= 0,
    }), 200
