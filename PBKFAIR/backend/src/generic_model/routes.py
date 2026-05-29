"""
routes.py — Flask blueprint for the Generic PFAS PBPK model.

Registered in app.py with url_prefix="/generic".

Endpoints
---------
GET  /generic/ui          Renders the simulation UI (login required)
POST /generic/run         Runs one compound/scenario, returns JSON results
GET  /generic/scenarios   Returns available scenario list as JSON
GET  /generic/compounds   Returns available compound list as JSON
"""
from __future__ import annotations

from flask import Blueprint, jsonify, render_template, request, session

from src.auth.decorators import login_required
from .helpers import run_scenario, available_scenarios, available_compounds

routes = Blueprint("generic_model_routes", __name__)


@routes.route("/ui", methods=["GET"])
@login_required()
def model_ui():
    """Render the Generic PFAS PBPK simulation interface."""
    return render_template(
        "generic_model/GenericPBKFAIR.html",
        scenarios=available_scenarios(),
        compounds=available_compounds(),
        user_email=session.get("email"),
        current_path=request.path,
    )


@routes.route("/run", methods=["POST"])
@login_required()
def run():
    """
    Run one Generic PFAS PBPK simulation.

    Request body (JSON):
        compound   (str)   — PFOA | PFOS
        scenario   (str)   — no_bf | bf_6mo | bf_1yr | bf_2yr
        Ratio_GFR  (float) — optional GFR scaling factor (default 1.0)
        t_end_h    (float) — optional simulation end time in hours
        n_pts      (int)   — optional output resolution

    Response (JSON):
        compound, scenario, n_rows, t_end_h,
        peak_CA_maternal_mgL, peak_age_yr, peak_CA_fetal_mgL,
        final_CA_maternal_mgL, final_age_yr,
        timeseries (up to 500 points)
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


@routes.route("/compounds", methods=["GET"])
@login_required()
def compounds():
    """Return metadata for supported PFAS compounds."""
    return jsonify(available_compounds()), 200
