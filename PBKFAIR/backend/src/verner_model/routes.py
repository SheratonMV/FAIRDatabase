"""
routes.py — Flask blueprint for the Verner 2015 pregnancy PBPK model.

Registered in app.py with url_prefix="/verner".

Endpoints
---------
GET  /verner/ui        Renders the simulation UI (login required)
POST /verner/run       Runs MC simulation, returns JSON results
GET  /verner/compounds Returns available compound list as JSON
"""
from __future__ import annotations

from flask import Blueprint, jsonify, render_template, request, session

from src.auth.decorators import login_required
from .helpers import run_scenario, available_compounds

routes = Blueprint("verner_model_routes", __name__)


@routes.route("/ui", methods=["GET"])
@login_required()
def model_ui():
    """Render the Verner 2015 PBPK simulation interface."""
    return render_template(
        "verner_model/Ouidir2025FAIR.html",
        compounds=available_compounds(),
        user_email=session.get("email"),
        current_path=request.path,
    )


@routes.route("/run", methods=["POST"])
@login_required()
def run():
    """
    Run Monte Carlo Verner 2015 PBPK simulation.

    Request body (JSON):
        compound  (str) — PFOA | PFOS
        n_iter    (int) — MC iterations (default 100, max 1000)
        seed      (int) — RNG seed (default 42)

    Response (JSON):
        compound, n_iter, n_rows, t_end_h,
        timeseries (9 rows, months 1–9) each with:
            month, time_h, CA_mean_mgL, CA_p5_mgL, CA_p25_mgL,
            CA_p75_mgL, CA_p95_mgL, CA_f_mean_mgL
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
