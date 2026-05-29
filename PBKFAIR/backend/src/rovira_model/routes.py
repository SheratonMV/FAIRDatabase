"""
routes.py — Flask blueprint for the Rovira 2019 pregnancy PBPK model.

Registered in app.py with url_prefix="/rovira".

Endpoints
---------
GET  /rovira/ui        Renders the simulation UI (login required)
POST /rovira/run       Runs one compound scenario, returns JSON results
GET  /rovira/compounds Returns available compound list as JSON
"""
from __future__ import annotations

from flask import Blueprint, jsonify, render_template, request, session

from src.auth.decorators import login_required
from .helpers import run_scenario, available_compounds

routes = Blueprint("rovira_model_routes", __name__)


@routes.route("/ui", methods=["GET"])
@login_required()
def model_ui():
    """Render the Rovira 2019 PBPK simulation interface."""
    return render_template(
        "rovira_model/Rovira2019FAIR.html",
        compounds=available_compounds(),
        user_email=session.get("email"),
        current_path=request.path,
    )


@routes.route("/run", methods=["POST"])
@login_required()
def run():
    """
    Run one Rovira 2019 PBPK simulation.

    Request body (JSON):
        compound  (str)   — PFOA | PFOS
        CVINIT    (float) — optional pre-pregnancy plasma (mg/L)
        BW0       (float) — optional pre-pregnancy body weight (kg)

    Response (JSON):
        compound, n_rows, t_end_h, peak_CA_maternal_mgL,
        CA_cord_mgL, transfer_ratio, timeseries (2 rows: GW12, GW38)
    """
    payload = request.get_json(silent=True) or {}

    try:
        result = run_scenario(payload)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except RuntimeError as exc:
        return jsonify({"error": f"Simulation failed: {exc}"}), 500

    return jsonify(result), 200


@routes.route("/compounds", methods=["GET"])
@login_required()
def compounds():
    """Return metadata for supported PFAS compounds."""
    return jsonify(available_compounds()), 200
