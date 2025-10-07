"""
Handlers for data generalization and P29 score calculation.
"""

import os

from flask import current_app, request, session
from werkzeug.utils import secure_filename

from src.anonymization.p_29 import P_29_score
from src.exceptions import GenericExceptionHandler
from src.form_handler import BaseHandler

from .helpers import (
    allowed_file,
    calculate_missing_percentages,
    drop_columns,
    identify_quasi_identifiers_with_distinct_values,
    map_values_and_output_percentages,
)


class DataGeneralizationHandler(BaseHandler):
    """
    Manage dataset upload, column dropping, missing values handling, quasi-identifier selection, and mapping for anonymization.

    ---
    tags:
    - data-generalization
    summary: Perform dataset preparation and generalization steps for anonymization.
    """

    def __init__(self):
        super().__init__()
        self._ctx.update(
            {
                "uploaded": session.get("uploaded", False),
                "columns_dropped": session.get("columns_dropped", False),
                "missing_values_reviewed": session.get("missing_values_reviewed", False),
                "quasi_identifiers_selected": session.get("quasi_identifiers_selected", False),
                "all_steps_completed": session.get("all_steps_completed", False),
                "column_names": session.get("column_names", []),
                "columns_to_drop": session.get("columns_to_drop", []),
                "quasi_identifiers": session.get("quasi_identifiers", []),
                "quasi_identifier_values": session.get("quasi_identifier_values", {}),
                "distinct_values": session.get("distinct_values", {}),
                "current_quasi_identifier": session.get("current_quasi_identifier", None),
                "mappings": session.get("mappings", {}),
                "missing_percentages": session.get("missing_percentages", {}),
                "updated_percentages": session.get("updated_percentages", {}),
                "message": None,
            }
        )

    def _validate_file(self, file):
        """
        Validate the uploaded file.

        ---
        tags:
        - data-generalization
        summary: Ensure file is present and has an allowed extension.
        responses:
            400:
                description: Invalid or missing file
        """
        if not file or not hasattr(file, "filename") or not allowed_file(file.filename):
            raise GenericExceptionHandler("Invalid or missing file.")
        return True

    async def handle_file_upload(self, file):
        """
        Handle the file upload and load dataset.

        ---
        tags:
        - data-generalization
        summary: Save uploaded file, load dataframe, and update session state.
        responses:
            200:
                description: File imported successfully
            400:
                description: File upload failed
        """
        self._validate_file(file)
        filename = secure_filename(file.filename)
        self._filepath = os.path.join(current_app.config["UPLOAD_FOLDER"], filename)

        try:
            file.save(self._filepath)
            df = self._load_dataframe()
            updates = {
                "uploaded": True,
                "column_names": df.columns.tolist(),
                "uploaded_filepath": self._filepath,
                "message": "File imported successfully.",
            }
            self._update_session_and_context(updates)
        except Exception as e:
            raise GenericExceptionHandler(f"File upload failed: {str(e)}", status_code=400)

    async def handle_columns_drop(self):
        """
        Drop selected columns from the dataset.

        ---
        tags:
        - data-generalization
        summary: Remove columns specified by the user and update session state.
        """
        df = self._load_dataframe()
        columns_to_drop = request.form.getlist("columns_to_drop")

        if not columns_to_drop:
            return

        if drop_columns(df, columns_to_drop):
            self._save_dataframe(df)
            updates = {
                "columns_dropped": True,
                "column_names": df.columns.tolist(),
                "missing_percentages": calculate_missing_percentages(df),
                "message": "Direct identifiers dropped successfully.",
            }
            self._update_session_and_context(updates)

    async def handle_missing_values(self):
        """
        Handle columns with missing values by dropping them.

        ---
        tags:
        - data-generalization
        summary: Drop columns with missing values as specified by the user.
        """
        df = self._load_dataframe()
        columns_to_drop = request.form.getlist("columns_to_drop")

        if not columns_to_drop:
            return

        if drop_columns(df, columns_to_drop):
            self._save_dataframe(df)
            updates = {
                "missing_values_reviewed": True,
                "column_names": df.columns.tolist(),
                "message": "Columns with missing values dropped successfully.",
            }
            self._update_session_and_context(updates)

    async def handle_quasi_identifiers(self):
        """
        Process selected quasi-identifiers and prepare for mapping.

        ---
        tags:
        - data-generalization
        summary: Identify quasi-identifiers and collect distinct values for mapping.
        """
        df = self._load_dataframe()
        quasi_identifiers = request.form.getlist("quasi_identifiers")
        self._update_session_and_context({"quasi_identifiers": quasi_identifiers})

        if not quasi_identifiers:
            updates = {
                "quasi_identifiers_selected": True,
                "all_steps_completed": True,
                "message": "No quasi-identifiers selected. Dataset has been generalized.",
            }
            self._update_session_and_context(updates)
        else:
            distinct_vals, qi_values = identify_quasi_identifiers_with_distinct_values(
                df, quasi_identifiers
            )
            updates = {
                "quasi_identifiers_selected": True,
                "distinct_values": distinct_vals,
                "quasi_identifier_values": qi_values,
                "current_quasi_identifier": quasi_identifiers[0],
                "current_quasi_identifier_index": 0,
                "message": "Quasi-identifiers selected",
            }
            self._update_session_and_context(updates)

    async def handle_mapping(self):
        """
        Map quasi-identifier values to generalized values.

        ---
        tags:
        - data-generalization
        summary: Update dataset with mapped values for quasi-identifiers and
                 progress through mapping steps.
        responses:
            400:
                description: No current quasi-identifier set
        """
        df = self._load_dataframe()
        mappings = session.get("mappings", {})
        current_qi = session.get("current_quasi_identifier")

        if not current_qi:
            raise GenericExceptionHandler("No current quasi-identifier set.", status_code=400)

        if current_qi not in mappings:
            mappings[current_qi] = {}

        for key in request.form:
            if key.startswith("mapping_"):
                _, val = key.rsplit("_", 1)
                mappings[current_qi][val] = request.form[key]

        df, updated = map_values_and_output_percentages(df, [current_qi], mappings)
        self._save_dataframe(df)

        updates = {
            "mappings": mappings,
            "quasi_identifier_values": {
                **session.get("quasi_identifier_values", {}),
                current_qi: updated[current_qi],
            },
            "updated_percentages": updated,
            "message": f"Values for '{current_qi}' mapped successfully.",
        }
        self._update_session_and_context(updates)

        qi_index = session.get("current_quasi_identifier_index", 0)
        if qi_index + 1 < len(session["quasi_identifiers"]):
            next_qi = session["quasi_identifiers"][qi_index + 1]
            self._update_session_and_context(
                {
                    "current_quasi_identifier_index": qi_index + 1,
                    "current_quasi_identifier": next_qi,
                }
            )
        else:
            self._update_session_and_context(
                {
                    "current_quasi_identifier": None,
                    "all_steps_completed": True,
                    "message": "All quasi-identifier values mapped successfully.",
                }
            )


class DataP29ScoreHandler(BaseHandler):
    """
    Handle calculation of the P29 privacy score for anonymized datasets.

    ---
    tags:
    - scoring
    summary: Calculate P29 score based on quasi-identifiers and sensitive attributes.
    """

    def __init__(self):
        super().__init__()
        self._ctx.update(
            {
                "uploaded": session.get("uploaded", False),
                "columns": [],
                "quasi_identifiers": session.get("quasi_identifiers", []),
                "sensitive_attributes": session.get("sensitive_attributes", []),
                "error": None,
                "message": None,
            }
        )

    def prepare_form(self):
        """
        Prepare form with dataset columns.

        ---
        tags:
        - scoring
        summary: Load dataset columns for user selection.
        """
        self.df = self._load_dataframe()
        self._ctx["columns"] = self.df.columns.tolist()

    def handle_score_calculation(self):
        """
        Calculate the P29 score from selected quasi-identifiers and sensitive attributes.

        ---
        tags:
        - scoring
        summary: Validate inputs and calculate P29 score.
        responses:
            400:
                description: Validation errors such as overlapping columns or missing selections
            200:
                description: P29 score calculated successfully
        """
        quasi_idents = request.form.getlist("quasi_identifiers")
        sens_attr = request.form.getlist("sensitive_attributes")

        self._update_session_and_context(
            {
                "quasi_identifiers": quasi_idents,
                "sensitive_attributes": sens_attr,
            }
        )

        if set(quasi_idents) & set(sens_attr):
            self._ctx["error"] = (
                "A column cannot be both a quasi-identifier and a sensitive attribute."
            )
            return

        if not quasi_idents or not sens_attr:
            self._ctx["error"] = "Please select both quasi-identifiers and sensitive attributes."
            return

        res = P_29_score(self.df, quasi_idents, sens_attr)
        p29, problems, reasons, k_anon, min_l, max_t, _ = res
        self._ctx.update(
            {
                "result": res,
                "p29result": round(p29, 1),
                "minlresult": round(min_l, 1),
                "maxtresult": round(float(max_t), 1),
                "k_anonresult": k_anon,
                "reason_result": list(reasons),
                "problems_result": list(problems)[:10],
                "message": "p29 score calculated successfully.",
            }
        )
