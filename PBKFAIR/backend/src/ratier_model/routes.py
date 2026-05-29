"""
routes.py — Flask blueprint for the lifetime PBPK model.

Registered in app.py with url_prefix="/model".

Endpoints
---------
GET  /model/ui          Renders the simulation UI (login required)
POST /model/run         Runs one scenario, returns JSON results
GET  /model/scenarios   Returns available scenario list as JSON
"""
from __future__ import annotations

from flask import Blueprint, jsonify, render_template, request, session

from src.auth.decorators import login_required
from .helpers import run_scenario, available_scenarios

routes = Blueprint("model_routes", __name__)


@routes.route("/ui", methods=["GET"])
@login_required()
def model_ui():
    """Render the PBPK simulation interface."""
    return render_template(
        "ratier_model/Ratier2024FAIR.html",
        scenarios=available_scenarios(),
        user_email=session.get("email"),
        current_path=request.path,
    )


@routes.route("/run", methods=["POST"])
@login_required()
def run():
    """
    Run one breastfeeding scenario.

    Request body (JSON):
        scenario      (str)   — no_bf | bf_6mo | bf_1yr | bf_3yr
        HalfLife      (float) — optional, chemical half-life in years
        RateInj       (float) — optional, dietary intake ng/kg/min
        BirthYear     (float) — optional

    Response (JSON):
        scenario, peak_C_ven, peak_Age_yr, final_C_ven, final_Age_yr,
        n_rows, t_end_min, timeseries (up to 500 points)
    """
    payload = request.get_json(silent=True) or {}

    try:
        result = run_scenario(payload)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except RuntimeError as exc:
        return jsonify({"error": f"Simulation failed: {exc}"}), 500

    return jsonify(result), 200


@routes.route("/scenarios", methods=["GET"])
@login_required()
def scenarios():
    """Return metadata for all available breastfeeding scenarios."""
    return jsonify(available_scenarios()), 200
