"""Routes for bundled FAIR PBPK study models.

Attached to the pbpk plugin's main Blueprint (see ``routes.py``). Endpoints are
mounted under ``/model/studies/<slug>/`` once the parent blueprint is registered
at ``url_prefix=/model``.

The heavy ``libsbml``/``scipy`` dependencies pulled in by the runners are
imported lazily through :mod:`plugins.pbpk.studies` so plugin discovery and
the rest of the pbpk routes keep working without them installed.

Every POST /model/studies/<slug>/run now persists the run to the database so
the results page at /model/results/<run_id> can display full provenance.
"""
from __future__ import annotations

from flask import abort, g, jsonify, redirect, render_template, request, session, url_for

from kernel.auth import login_required

from . import studies as _studies
from .catalogue import canonical_hash, create_study_run, find_cached_run, list_thresholds
from .helpers import fetch_run, update_run


def _meta(slug: str):
    meta = _studies.STUDIES.get(slug)
    if meta is None:
        abort(404, description=f"Unknown study '{slug}'")
    return meta


def _scenarios(mod) -> list[dict]:
    return [
        {"label": s["label"], "description": s["description"]}
        for s in getattr(mod, "SCENARIOS", [])
    ]


def _compounds(mod) -> list[dict]:
    return [
        {"label": c["label"], "description": c["description"]}
        for c in getattr(mod, "COMPOUNDS", [])
    ]


def register(routes):
    """Attach study endpoints to the given pbpk Blueprint."""

    @routes.route("/studies", methods=["GET"])
    @login_required()
    def studies_index():
        return jsonify([
            {"slug": m["slug"], "label": m["label"]}
            for m in _studies.STUDIES.values()
        ]), 200

    @routes.route("/studies/<slug>/ui", methods=["GET"])
    @login_required()
    def study_ui(slug):
        meta = _meta(slug)
        try:
            mod = _studies.load(slug)
        except ImportError:
            mod = None
        from plugins.pbpk import params as _params
        _spec_map = {
            "ratier": _params.RATIER,
            "rovira": _params.ROVIRA,
            "verner": _params.VERNER_UI,
            "generic": _params.GENERIC,
        }
        return render_template(
            meta["template"],
            scenarios=_scenarios(mod) if (mod and meta["has_scenarios"]) else [],
            compounds=_compounds(mod) if (mod and meta["has_compounds"]) else [],
            thresholds=list_thresholds(),
            pbpk_active_tab=slug,
            user_email=session.get("email"),
            current_path=request.path,
            param_specs=_spec_map.get(slug, {}),
            domain_js=_params.domain_js(slug),
        )

    @routes.route("/studies/<slug>/run", methods=["POST"])
    @login_required()
    def study_run(slug):
        _meta(slug)
        try:
            mod = _studies.load(slug)
        except ImportError as exc:
            return jsonify({"error": f"Study unavailable: {exc}"}), 503

        payload = request.get_json(silent=True) or {}

        # Determine scenario / compound for provenance storage
        scenario = payload.get("scenario", "")
        compound = payload.get("compound", "")
        created_by = session.get("email", "")
        owner_id = getattr(g, "user", None)

        # Content-hash idempotency: return cached run if identical params were run before
        c_hash = canonical_hash(slug, payload)
        try:
            cached_id = find_cached_run(c_hash)
        except Exception:
            cached_id = None

        if cached_id is not None:
            cached_run = fetch_run(cached_id)
            if cached_run is not None:
                cached_run["run_id"] = cached_id
                cached_run["cache_hit"] = True
                return jsonify(cached_run), 200

        # Persist run record before executing so run_id is always returned
        try:
            run_id = create_study_run(
                study_slug=slug,
                scenario=scenario,
                compound=compound or None,
                created_by=created_by,
                owner_id=owner_id,
                content_hash=c_hash,
            )
        except Exception:
            # DB failure should not block the simulation — return result without run_id
            run_id = None

        try:
            result = mod.execute(payload)
        except ValueError as exc:
            if run_id is not None:
                update_run(run_id, "error", error_message=str(exc))
            return jsonify({"error": str(exc)}), 400
        except RuntimeError as exc:
            if run_id is not None:
                update_run(run_id, "error", error_message=f"Simulation failed: {exc}")
            return jsonify({"error": f"Simulation failed: {exc}"}), 500

        if run_id is not None:
            summary = _extract_summary(result)
            update_run(
                run_id, "done",
                summary=summary,
                timeseries=result.get("timeseries"),
            )
            result["run_id"] = run_id

        return jsonify(result), 200

    @routes.route("/studies/<slug>/scenarios", methods=["GET"])
    @login_required()
    def study_scenarios(slug):
        meta = _meta(slug)
        if not meta["has_scenarios"]:
            return jsonify([]), 200
        return jsonify(_scenarios(_studies.load(slug))), 200

    @routes.route("/studies/<slug>/compounds", methods=["GET"])
    @login_required()
    def study_compounds(slug):
        meta = _meta(slug)
        if not meta["has_compounds"]:
            return jsonify([]), 200
        return jsonify(_compounds(_studies.load(slug))), 200


def _extract_summary(result: dict) -> dict:
    """Pull scalar KPIs from any runner's result dict for DB storage."""
    summary = {}
    # Ratier / generic runner keys
    for key in ("peak_C_ven", "peak_Age_yr", "final_C_ven", "final_Age_yr",
                "peak_CA_maternal_mgL", "peak_age_yr", "final_CA_maternal_mgL",
                "final_age_yr", "n_rows", "n_iter"):
        if key in result:
            summary[key] = result[key]
    # Rovira runner keys
    for key in ("CA_cord_mgL", "transfer_ratio"):
        if key in result:
            summary[key] = result[key]
    return summary
