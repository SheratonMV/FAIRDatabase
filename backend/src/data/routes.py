"""Flask routes managing data generalization workflow and
   p29 score calculation with user authentication."""

import math
import os

from flask import (
    session,
    request,
    render_template,
    redirect,
    Blueprint,
    url_for,
    abort,
    flash,
    send_file,
    g,
    jsonify,
)

from src.auth.decorators import login_required
from src.dashboard.helpers import assert_can_modify_dataset, assert_can_modify_table
from .form import DataGeneralizationHandler, DataP29ScoreHandler
from kernel import dp_budget as fl_db

import asyncio

import logging
_log = logging.getLogger(__name__)

routes = Blueprint("data_generalization_routes", __name__)


@routes.route("/data_generalization", methods=["GET", "POST"])
@login_required("admin", "curator")
def data_generalization():
    """
    Perform data generalization through a user-guided, stepwise process.
    ---
    tags:
      - data-generalization
    parameters:
      - name: file
        in: formData
        type: file
        required: false
        description: CSV file to upload for processing.
      - name: submit_button
        in: formData
        type: string
        required: true
        description: Indicates the form action submitted by the user.
    responses:
      200:
        description: Data generalization form rendered.
      401:
        description: User not authenticated.
      400:
        description: Bad input or session error.
    """
    handler = DataGeneralizationHandler()

    if request.method == "POST":
        btn = request.form.get("submit_button", "")
        if "file" in request.files:
            asyncio.run(handler.handle_file_upload(request.files["file"]))
        elif btn == "submit_columns":
            asyncio.run(handler.handle_columns_drop())
        elif btn == "submit_missing_values":
            asyncio.run(handler.handle_missing_values())
        elif btn == "submit_quasi_identifiers":
            asyncio.run(handler.handle_quasi_identifiers())
        elif btn == "submit_mapping":
            asyncio.run(handler.handle_mapping())

    return render_template("/data/data_generalization.html", **handler.ctx)


@routes.route("/consolidated_return", methods=["GET", "POST"])
@login_required("admin", "curator")
def consolidated_return():
    """
    Handles step transitions in the data generalization process by updating
    session states.
    ---
    tags:
      - data-generalization
    parameters:
      - name: state
        in: formData
        type: string
        required: true
        description: Step identifier indicating progress in the
        generalization workflow.
    responses:
      302:
        description: Redirect to the data generalization page with
        context updated.
    """
    state = request.form.get("state")

    if state == "1":
        uploaded = False
        columns_dropped = False
        missing_values_reviewed = False
        quasi_identifiers_selected = False
        current_quasi_identifier = False
        all_steps_completed = False
        session["uploaded"] = uploaded
        session["columns_dropped"] = columns_dropped
        session["missing_values_reviewed"] = missing_values_reviewed
        session["quasi_identifiers_selected"] = quasi_identifiers_selected
        session["current_quasi_identifier"] = current_quasi_identifier
        session["all_steps_completed"] = all_steps_completed
        return redirect(url_for("data_generalization_routes.data_generalization"))
    elif state == "2":
        uploaded = True
        columns_dropped = False
        session["uploaded"] = uploaded
        session["columns_dropped"] = columns_dropped
        return redirect(url_for("data_generalization_routes.data_generalization"))
    elif state == "3":
        uploaded = True
        columns_dropped = True
        missing_values_reviewed = False
        session["uploaded"] = uploaded
        session["columns_dropped"] = columns_dropped
        session["missing_values_reviewed"] = missing_values_reviewed
        return redirect(url_for("data_generalization_routes.data_generalization"))
    elif state == "4":
        uploaded = True
        columns_dropped = True
        missing_values_reviewed = True
        quasi_identifiers_selected = False
        current_quasi_identifier = False
        session["uploaded"] = uploaded
        session["columns_dropped"] = columns_dropped
        session["missing_values_reviewed"] = missing_values_reviewed
        session["quasi_identifiers_selected"] = quasi_identifiers_selected
        session["current_quasi_identifier"] = current_quasi_identifier
        return redirect(url_for("data_generalization_routes.data_generalization"))

    return redirect(url_for("data_generalization_routes.data_generalization"))


@routes.route("/reset_generalization", methods=["GET"])
@login_required("admin", "curator")
def reset_generalization():
    """
    Clear all data-generalization session state so the user can upload a new dataset.
    ---
    tags:
      - data-generalization
    responses:
      302:
        description: Redirects to data_generalization with a clean session.
    """
    _keys = [
        "uploaded", "columns_dropped", "missing_values_reviewed",
        "quasi_identifiers_selected", "all_steps_completed",
        "column_names", "columns_to_drop", "quasi_identifiers",
        "quasi_identifier_values", "distinct_values",
        "current_quasi_identifier", "current_quasi_identifier_index",
        "mappings", "missing_percentages", "updated_percentages",
        "uploaded_filepath",
    ]
    for k in _keys:
        session.pop(k, None)
    return redirect(url_for("data_generalization_routes.data_generalization"))


@routes.route("/p29score", methods=["GET", "POST"])
@login_required("admin", "curator", "accessor")
def data_p29score():
    """
    Calculate the p29 score based on selected quasi-identifiers and sensitive attributes.
    ---
    tags:
      - data-anonymization
    responses:
      200:
        description: P29 score calculated and form rendered.
      400:
        description: Bad input or session error.
    """
    handler = DataP29ScoreHandler()
    handler.prepare_form()

    if request.method == "POST":
        btn = request.form.get("submit_button", "")
        if btn == "Calculate Score":
            handler.handle_score_calculation()

    return render_template("/data/p29score.html", **handler.ctx)


@routes.route("/download_generalized", methods=["GET"])
@login_required("admin", "curator")
def download_generalized():
    """
    Download the anonymised/generalised CSV dataset from the current session.
    ---
    tags:
      - data-generalization
    responses:
      200:
        description: Sends the anonymised CSV file as an attachment.
      302:
        description: Redirects back to data_generalization if no file is in session.
    """
    filepath = session.get("uploaded_filepath")
    if not filepath or not os.path.exists(filepath):
        flash("No anonymised dataset available for download.", "danger")
        return redirect(url_for("data_generalization_routes.data_generalization"))
    return send_file(
        filepath,
        as_attachment=True,
        download_name="anonymized_dataset.csv",
        mimetype="text/csv",
    )


@routes.route("/upload_metadata/<table_name>", methods=["GET", "POST"])
@login_required("admin", "curator")
def upload_metadata(table_name):
    """Upload sample metadata for a dataset."""
    from .metadata_helpers import validate_metadata_csv, store_metadata
    from flask import flash

    conn = g.db
    with conn.cursor() as ownership_cur:
        try:
            assert_can_modify_table(ownership_cur, table_name, g.user, g.role)
        except PermissionError:
            abort(403)

    if request.method == "POST":
        if 'metadata_file' not in request.files:
            flash("No file uploaded", "danger")
            return redirect(request.url)

        file = request.files['metadata_file']
        if file.filename == '':
            flash("No file selected", "danger")
            return redirect(request.url)

        # Validate
        valid, errors, df = validate_metadata_csv(file, table_name, conn)

        if not valid:
            for error in errors:
                flash(error, "danger")
            return redirect(request.url)

        # Store metadata
        try:
            store_metadata(df, table_name, conn)
            flash(f"Metadata uploaded successfully for {table_name}!", "success")
            return redirect(url_for('visualization_routes.visualization'))
        except Exception:
            _log.exception("storing sample metadata failed")
            flash("Error storing metadata.", "danger")
            return redirect(request.url)

    return render_template("/data/upload_metadata.html",
                          table_name=table_name)


@routes.route("/datasets/<dataset_id>/fl-enroll", methods=["POST"])
@login_required("admin", "curator")
def fl_enroll(dataset_id):
    """
    Mark a dataset as FL-eligible after P29 assessment passes.

    Creates a fl_epsilon_budget row with the provided total_budget (default 10.0 ε).
    Only datasets that have completed data generalisation should be enrolled.
    """
    payload = request.get_json(silent=True) or {}
    try:
        total_budget = float(payload.get("total_budget", 10.0))
    except (TypeError, ValueError):
        return jsonify({"error": "total_budget must be a number"}), 400

    # isfinite: JSON "Infinity" parses to float('inf'), which would be an
    # unlimited privacy budget. NaN also fails here.
    if not math.isfinite(total_budget) or total_budget <= 0:
        return jsonify({"error": "total_budget must be a positive finite number"}), 400

    # Enrolling sets (or resets) the dataset's privacy budget, so only its
    # owner or an admin may do it.
    try:
        with g.db.cursor() as cur:
            assert_can_modify_dataset(cur, dataset_id, g.user, g.role)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except PermissionError:
        return jsonify({"error": "dataset not found"}), 404

    try:
        fl_db.enroll_dataset(g.db, dataset_id, total_budget)
    except Exception:
        g.db.rollback()
        _log.exception("FL enrolment failed")
        return jsonify({"error": "enrolment failed"}), 500

    return jsonify({
        "dataset_id": dataset_id,
        "fl_eligible": True,
        "total_budget": total_budget,
    }), 200
