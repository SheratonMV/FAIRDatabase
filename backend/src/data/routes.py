"""Flask routes managing data generalization workflow and
   p29 score calculation with user authentication."""

from flask import (
    session,
    request,
    render_template,
    redirect,
    Blueprint,
    url_for,
)

from src.auth.decorators import login_required
from .form import DataGeneralizationHandler, DataP29ScoreHandler

import asyncio

routes = Blueprint("data_generalization_routes", __name__)


@routes.route("/data_generalization", methods=["GET", "POST"])
@login_required()
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
@login_required()
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


@routes.route("/p29score", methods=["GET", "POST"])
@login_required()
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
