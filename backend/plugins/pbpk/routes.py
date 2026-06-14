"""
routes.py — Flask blueprint for the lifetime PBPK model.

Migrated from src/model/routes.py (migration plan Phase 4). Mounted by the
plugin loader at url_prefix="/model" (declared in plugin.py).

Endpoints
---------
GET  /model/ui                        Renders the simulation UI (login required)
POST /model/run                       Runs one scenario in-memory, returns JSON
GET  /model/scenarios                 Returns available scenario list as JSON
POST /model/parameter-sets            Store a named parameter set
GET  /model/parameter-sets            List all public parameter sets
GET  /model/parameter-sets/<id>       Fetch one parameter set with full params
POST /model/runs                      Create + execute a simulation run
GET  /model/runs/<id>                 Fetch one simulation run
GET  /model/runs/<id>/provenance      Return W3C PROV-JSON provenance document
POST /model/runs/<id>/artifacts       Upload a binary artifact for a run
GET  /model/runs/<id>/artifacts       List a run's artifacts (signed URLs)
DELETE /model/artifacts/<id>          Delete an artifact (blob + catalog row)
"""
from __future__ import annotations

import os
import pathlib
import tempfile
import uuid as _uuid

from flask import Blueprint, abort, g, jsonify, redirect, render_template, request, send_file, session, url_for
from werkzeug.utils import secure_filename

from kernel.auth import login_required
from kernel.storage import delete_object, signed_url, upload_stream

from .helpers import (
    DEFAULT_PARAMS,
    assert_can_modify_run,
    assert_can_read_run,
    available_scenarios,
    create_run,
    delete_artifact_row,
    fetch_artifact,
    fetch_parameter_set,
    fetch_run,
    fetch_run_checked,
    fetch_run_provenance,
    insert_artifact,
    list_artifacts,
    list_parameter_sets,
    run_scenario,
    store_parameter_set,
    update_run,
)
from .catalogue import (
    list_models,
    fetch_model,
    list_thresholds,
    create_threshold,
    list_run_history,
    fetch_runs_for_compare,
)

# ── Artifact upload config ────────────────────────────────────────────────────
ARTIFACT_BUCKET = "pbpk-artifacts"        # keep in sync with plugin.py manifest
ARTIFACT_MAX_BYTES = 200 * 1024 * 1024    # 200 MB
ARTIFACT_SIGNED_URL_TTL = 60 * 10         # 10 minutes
ARTIFACT_CHUNK_BYTES = 1 * 1024 * 1024    # 1 MB stream chunks

# mime -> (kind, allowed extensions) — vtk has no registered MIME so we accept
# octet-stream + extension match.
_ARTIFACT_TYPES = {
    "image/jpeg": ("image", {".jpg", ".jpeg"}),
    "image/png":  ("image", {".png"}),
    "video/mp4":  ("video", {".mp4"}),
    "application/octet-stream": ("mesh", {".vtk", ".vtu", ".vtp"}),
}


def _classify_artifact(mime: str, filename: str) -> tuple[str, str]:
    """Return (kind, normalized_mime) or raise ValueError."""
    ext = os.path.splitext(filename)[1].lower()
    mime = (mime or "").lower()
    if mime in _ARTIFACT_TYPES:
        kind, exts = _ARTIFACT_TYPES[mime]
        if ext not in exts:
            raise ValueError(f"extension {ext!r} does not match mime {mime!r}")
        return kind, mime
    if ext in {".vtk", ".vtu", ".vtp"}:
        return "mesh", "application/octet-stream"
    raise ValueError(f"unsupported artifact type: mime={mime!r} ext={ext!r}")


routes = Blueprint("pbpk_routes", __name__)

# Attach bundled FAIR study models under /model/studies/<slug>/...
from . import studies as _studies  # noqa: E402
from . import study_routes as _study_routes  # noqa: E402
_study_routes.register(routes)


# Make the in-plugin tab strip data available to every pbpk template without
# each route having to pass it explicitly. ``pbpk_active_tab`` is still per-
# route (slug for study pages, ``"lifetime"`` for the main UI).
@routes.context_processor
def _inject_pbpk_studies():
    return {
        "plugin_studies": [
            {
                "slug": m["slug"],
                "label": m["label"],
                "href": f"/model/studies/{m['slug']}/ui",
            }
            for m in _studies.STUDIES.values()
        ],
    }


# ── Existing endpoints ────────────────────────────────────────────────────────

@routes.route("/ui", methods=["GET"])
@login_required()
def model_ui():
    return redirect(url_for("pbpk_routes.catalogue"))


@routes.route("/run", methods=["POST"])
@login_required()
def run():
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
    return jsonify(available_scenarios()), 200


# ── Parameter set endpoints ───────────────────────────────────────────────────

@routes.route("/parameter-sets", methods=["POST"])
@login_required("admin", "curator")
def create_parameter_set():
    payload = request.get_json(silent=True) or {}
    name = payload.get("name", "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400
    params = payload.get("params", {})
    if not isinstance(params, dict):
        return jsonify({"error": "params must be a JSON object"}), 400
    description = payload.get("description", "")
    # 'source' tracks how the set was created ("manual" by default, "federated"
    # when the horizontal_fl plugin exports aggregated weights here).
    source = payload.get("source", "manual")
    if source not in ("manual", "federated"):
        return jsonify({"error": "invalid source"}), 400
    created_by = session.get("email", "")
    ps_id = store_parameter_set(
        name, description, params, created_by, owner_id=g.user, source=source
    )
    return jsonify({"id": ps_id, "name": name}), 201


@routes.route("/parameter-sets", methods=["GET"])
@login_required()
def get_parameter_sets():
    return jsonify(list_parameter_sets()), 200


@routes.route("/parameter-sets/<int:param_set_id>", methods=["GET"])
@login_required()
def get_parameter_set(param_set_id):
    ps = fetch_parameter_set(param_set_id)
    if ps is None:
        return jsonify({"error": "Parameter set not found"}), 404
    return jsonify(ps), 200


# ── Simulation run endpoints ──────────────────────────────────────────────────

@routes.route("/runs", methods=["POST"])
@login_required("admin", "curator")
def create_simulation_run():
    payload = request.get_json(silent=True) or {}
    param_set_id = payload.get("param_set_id")
    if param_set_id is None:
        return jsonify({"error": "param_set_id is required"}), 400

    ps = fetch_parameter_set(int(param_set_id))
    if ps is None:
        return jsonify({"error": "Parameter set not found"}), 404

    scenario = payload.get("scenario", "no_bf")
    created_by = session.get("email", "")

    run_id = create_run(int(param_set_id), scenario, created_by, owner_id=g.user)

    merged_params = {**DEFAULT_PARAMS, **ps["params"], "scenario": scenario}

    try:
        result = run_scenario(merged_params)
    except ValueError as exc:
        update_run(run_id, "error", error_message=str(exc))
        return jsonify({"error": str(exc), "run_id": run_id}), 400
    except RuntimeError as exc:
        update_run(run_id, "error", error_message=str(exc))
        return jsonify({"error": f"Simulation failed: {exc}", "run_id": run_id}), 500

    summary = {
        "peak_C_ven": result.get("peak_C_ven"),
        "peak_Age_yr": result.get("peak_Age_yr"),
        "final_C_ven": result.get("final_C_ven"),
        "final_Age_yr": result.get("final_Age_yr"),
        "n_rows": result.get("n_rows"),
    }
    update_run(run_id, "done", summary=summary, timeseries=result.get("timeseries"))

    return jsonify({"run_id": run_id, **result}), 200


@routes.route("/runs/<int:run_id>", methods=["GET"])
@login_required("admin", "curator", "accessor")
def get_simulation_run(run_id):
    try:
        run = fetch_run_checked(run_id, g.user, g.role)
    except FileNotFoundError:
        return jsonify({"error": "Run not found"}), 404
    except PermissionError:
        abort(403)
    return jsonify(run), 200


@routes.route("/runs/<int:run_id>/provenance", methods=["GET"])
@login_required("admin", "curator", "accessor")
def get_run_provenance(run_id):
    """Return a W3C PROV-JSON document for the specified simulation run."""
    cur = g.db.cursor()
    try:
        assert_can_read_run(cur, run_id, g.user, g.role)
    except FileNotFoundError:
        return jsonify({"error": "Run not found"}), 404
    except PermissionError:
        abort(403)
    finally:
        cur.close()
    doc = fetch_run_provenance(run_id)
    if doc is None:
        return jsonify({"error": "Run not found"}), 404
    return jsonify(doc), 200


# ── Artifact endpoints (PoC) ──────────────────────────────────────────────────
#
# Bytes live in Supabase Storage bucket ``pbpk-artifacts``; this plugin manages
# the catalog row in _fd.pbpk_run_artifacts and short-lived signed URLs via
# kernel.storage. Bucket + storage.objects policies are applied out of band
# (see sql/pbpk_storage_policies.sql and the plugin README).

@routes.route("/runs/<int:run_id>/artifacts", methods=["POST"])
@login_required("admin", "curator")
def upload_run_artifact(run_id):
    cur = g.db.cursor()
    try:
        assert_can_modify_run(cur, run_id, g.user, g.role)
    except FileNotFoundError:
        return jsonify({"error": "Run not found"}), 404
    except PermissionError:
        abort(403)
    finally:
        cur.close()

    file = request.files.get("file")
    if file is None or not file.filename:
        return jsonify({"error": "file is required (multipart field 'file')"}), 400

    safe_name = secure_filename(file.filename)
    if not safe_name:
        return jsonify({"error": "invalid filename"}), 400

    try:
        kind, mime = _classify_artifact(file.mimetype, safe_name)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    # Stream the upload to a tempfile in fixed-size chunks instead of calling
    # file.read() (which would materialize up to ARTIFACT_MAX_BYTES in RAM per
    # concurrent upload). Werkzeug already spools the request body to disk for
    # large uploads, but reading it back into a single bytes object defeats
    # that. Peak RAM here is one chunk per worker.
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(safe_name)[1])
    tmp_path = tmp.name
    size = 0
    try:
        try:
            while True:
                chunk = file.stream.read(ARTIFACT_CHUNK_BYTES)
                if not chunk:
                    break
                size += len(chunk)
                if size > ARTIFACT_MAX_BYTES:
                    return jsonify({
                        "error": f"file exceeds {ARTIFACT_MAX_BYTES} byte limit"
                    }), 413
                tmp.write(chunk)
        finally:
            tmp.close()

        if size == 0:
            return jsonify({"error": "empty file"}), 400

        object_key = f"run_{run_id}/{_uuid.uuid4().hex}_{safe_name}"

        try:
            with open(tmp_path, "rb") as fh:
                storage_path = upload_stream(ARTIFACT_BUCKET, object_key, fh, mime)
        except Exception as exc:
            return jsonify({"error": f"storage upload failed: {exc}"}), 502

        try:
            artifact_id = insert_artifact(
                run_id=run_id,
                owner_id=g.user,
                kind=kind,
                storage_path=storage_path,
                mime=mime,
                size_bytes=size,
                original_name=safe_name,
            )
        except Exception as exc:
            # Best-effort cleanup so we don't leak orphan blobs.
            delete_object(storage_path)
            return jsonify({"error": f"catalog insert failed: {exc}"}), 500

        return jsonify({
            "id": artifact_id,
            "run_id": run_id,
            "kind": kind,
            "mime": mime,
            "size_bytes": size,
            "original_name": safe_name,
            "storage_path": storage_path,
            "url": signed_url(storage_path, ARTIFACT_SIGNED_URL_TTL),
        }), 201
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


@routes.route("/runs/<int:run_id>/artifacts", methods=["GET"])
@login_required("admin", "curator", "accessor")
def list_run_artifacts(run_id):
    cur = g.db.cursor()
    try:
        assert_can_read_run(cur, run_id, g.user, g.role)
    except FileNotFoundError:
        return jsonify({"error": "Run not found"}), 404
    except PermissionError:
        abort(403)
    finally:
        cur.close()

    rows = list_artifacts(run_id)
    for r in rows:
        r["url"] = signed_url(r["storage_path"], ARTIFACT_SIGNED_URL_TTL)
    return jsonify(rows), 200


# ── Catalogue HTML pages ──────────────────────────────────────────────────────

@routes.route("/catalogue", methods=["GET"])
@login_required()
def catalogue():
    models = list_models()
    return render_template(
        "pbpk/catalogue.html",
        models=models,
        user_email=session.get("email"),
        current_path=request.path,
        pbpk_active_tab="catalogue",
    )


@routes.route("/catalogue/<slug>", methods=["GET"])
@login_required()
def model_detail(slug):
    model = fetch_model(slug)
    if model is None:
        abort(404, description=f"Model '{slug}' not found")
    thresholds = list_thresholds()
    return render_template(
        "pbpk/model_detail.html",
        model=model,
        thresholds=thresholds,
        user_email=session.get("email"),
        current_path=request.path,
        pbpk_active_tab="catalogue",
    )


@routes.route("/catalogue/<slug>/sbml", methods=["GET"])
@login_required()
def download_sbml(slug):
    """Serve the SBML model file for direct download (§3.2 ideas)."""
    model = fetch_model(slug)
    if model is None:
        abort(404, description=f"Model '{slug}' not found")
    sbml_filename = model.get("sbml_file", "")
    if not sbml_filename:
        abort(404, description="No SBML file registered for this model")
    sbml_path = (
        pathlib.Path(__file__).parent / "studies" / slug / sbml_filename
    )
    if not sbml_path.exists():
        abort(404, description=f"SBML file '{sbml_filename}' not found on disk")
    return send_file(
        sbml_path,
        mimetype="application/xml",
        as_attachment=True,
        download_name=sbml_filename,
    )


@routes.route("/results/<int:run_id>", methods=["GET"])
@login_required("admin", "curator", "accessor")
def results_page(run_id):
    try:
        run = fetch_run_checked(run_id, g.user, g.role)
    except FileNotFoundError:
        abort(404)
    except PermissionError:
        abort(403)
    slug = run.get("study_slug") or ""
    model = fetch_model(slug) if slug else None
    thresholds = list_thresholds(chemical=run.get("compound") or None)
    return render_template(
        "pbpk/results.html",
        run=run,
        model=model,
        thresholds=thresholds,
        user_email=session.get("email"),
        current_path=request.path,
        pbpk_active_tab=slug or "lifetime",
    )


@routes.route("/validation", methods=["GET"])
@login_required()
def validation_page():
    return render_template(
        "pbpk/validation.html",
        user_email=session.get("email"),
        current_path=request.path,
        pbpk_active_tab="comparison",
    )


@routes.route("/history", methods=["GET"])
@login_required()
def run_history_page():
    try:
        limit = max(1, min(int(request.args.get("limit", 100)), 500))
    except (TypeError, ValueError):
        limit = 100
    runs = list_run_history(user_id=g.user, role=g.role, limit=limit)
    return render_template(
        "pbpk/run_history.html",
        runs=runs,
        user_email=session.get("email"),
        current_path=request.path,
        pbpk_active_tab="history",
    )


# ── JSON API endpoints (/model/api/...) ───────────────────────────────────────

@routes.route("/api/models", methods=["GET"])
@login_required()
def api_list_models():
    return jsonify(list_models()), 200


@routes.route("/api/models/<slug>", methods=["GET"])
@login_required()
def api_get_model(slug):
    model = fetch_model(slug)
    if model is None:
        return jsonify({"error": "Model not found"}), 404
    return jsonify(model), 200


@routes.route("/api/models/<slug>/ontology", methods=["GET"])
@login_required()
def api_model_ontology(slug):
    """Return all SBML CV-term annotations for a model with resolved labels.

    Response shape::

        {
          "slug": "rovira",
          "total_terms": 392,
          "resolved_labels": 378,
          "terms": [
            {
              "element_id": "V_plas",
              "element_type": "compartment",
              "qualifier": "BQB_IS",
              "iri": "http://purl.obolibrary.org/obo/PBPKO_00488",
              "ontology": "PBPKO",
              "local_id": "PBPKO:00488",
              "label": "plasma compartment"
            }, ...
          ]
        }
    """
    from .catalogue import ensure_seeded
    ensure_seeded()

    with g.db.cursor() as cur:
        cur.execute(
            """
            SELECT ct.element_id, ct.element_type, ct.qualifier,
                   ct.iri, il.ontology, il.local_id, il.label
            FROM _fd.pbpk_cv_terms   ct
            JOIN _fd.pbpk_iri_labels il ON il.iri = ct.iri
            WHERE ct.study_slug = %s
            ORDER BY ct.element_type, ct.element_id, ct.qualifier
            """,
            (slug,),
        )
        rows = cur.fetchall()

    if not rows:
        return jsonify({"error": "Model not found or ontology terms not yet seeded"}), 404

    terms = [
        {
            "element_id":   r[0],
            "element_type": r[1],
            "qualifier":    r[2],
            "iri":          r[3],
            "ontology":     r[4],
            "local_id":     r[5],
            "label":        r[6] if r[6] else r[5],   # fall back to local_id
        }
        for r in rows
    ]
    resolved = sum(1 for t in terms if t["label"] != t["local_id"])
    return jsonify({
        "slug": slug,
        "total_terms": len(terms),
        "resolved_labels": resolved,
        "terms": terms,
    }), 200


@routes.route("/api/thresholds", methods=["GET"])
@login_required()
def api_list_thresholds():
    chemical = request.args.get("chemical")
    return jsonify(list_thresholds(chemical=chemical)), 200


@routes.route("/api/thresholds", methods=["POST"])
@login_required("admin", "curator")
def api_create_threshold():
    payload = request.get_json(silent=True) or {}
    required = ["chemical", "value", "units"]
    missing = [f for f in required if not payload.get(f)]
    if missing:
        return jsonify({"error": f"Missing fields: {', '.join(missing)}"}), 400
    try:
        value = float(payload["value"])
    except (TypeError, ValueError):
        return jsonify({"error": "value must be a number"}), 400
    new_id = create_threshold(
        chemical=payload["chemical"].strip(),
        endpoint=payload.get("endpoint", "plasma").strip(),
        value=value,
        units=payload["units"].strip(),
        basis=payload.get("basis", "").strip(),
        doi=payload.get("doi", "").strip(),
    )
    return jsonify({"id": new_id}), 201


@routes.route("/api/runs", methods=["GET"])
@login_required()
def api_list_runs():
    try:
        limit = min(int(request.args.get("limit", 50)), 200)
    except (TypeError, ValueError):
        limit = 50
    runs = list_run_history(user_id=g.user, role=g.role, limit=limit)
    return jsonify(runs), 200


@routes.route("/api/runs/compare", methods=["POST"])
@login_required()
def api_compare_runs():
    """Compare multiple completed runs side-by-side.

    Body: {"run_ids": [id1, id2, ...]}  (2–6 IDs)

    Returns each run's summary and timeseries so the client can overlay
    concentration-time curves and diff parameters. Only returns runs that
    are visible to the caller (admin sees all; others see their own runs).
    """
    payload = request.get_json(silent=True) or {}
    run_ids = payload.get("run_ids", [])
    if not isinstance(run_ids, list):
        return jsonify({"error": "run_ids must be a list"}), 400
    if len(run_ids) < 2 or len(run_ids) > 6:
        return jsonify({"error": "run_ids must contain 2–6 IDs"}), 400
    try:
        run_ids = [int(rid) for rid in run_ids]
    except (TypeError, ValueError):
        return jsonify({"error": "run_ids must be integers"}), 400

    runs = fetch_runs_for_compare(run_ids, g.user, g.role)
    not_found = set(run_ids) - {r["id"] for r in runs}
    return jsonify({"runs": runs, "not_found": sorted(not_found)}), 200


# ── Artifact endpoints ────────────────────────────────────────────────────────

@routes.route("/artifacts/<int:artifact_id>", methods=["DELETE"])
@login_required("admin", "curator")
def delete_run_artifact(artifact_id):
    artifact = fetch_artifact(artifact_id)
    if artifact is None:
        return jsonify({"error": "Artifact not found"}), 404

    if g.role != "admin" and str(artifact["owner_id"]) != str(g.user):
        abort(403)

    # Don't block catalog cleanup on a missing blob — delete_object is
    # best-effort and swallows its own failures.
    delete_object(artifact["storage_path"])

    delete_artifact_row(artifact_id)
    return jsonify({"deleted": artifact_id}), 200
