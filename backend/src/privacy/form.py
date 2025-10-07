"""
Handlers for privacy processing and differential privacy noise addition in data anonymization workflows.
"""

from flask import request, session

from src.anonymization.enforce_privacy import enforce_privacy
from src.anonymization.p_29 import P_29_score
from src.exceptions import GenericExceptionHandler
from src.form_handler import BaseHandler

from .helpers import add_noise_to_df, validate_column_selection


class PrivacyProcessingHandler(BaseHandler):
    """
    Manage privacy processing, including P29 score calculation and enforcement.
    """

    def __init__(self):
        """
        Initialize handler, set file path and update context with user info
        and request path.
        ---
        tags:
          - privacy-processing
        responses:
          200:
            description: Context initialized with user and file info.
        """
        super().__init__()
        self._filepath = session.get("uploaded_filepath")
        self._update_context(
            {
                "user_email": session.get("email"),
                "filepath": self._filepath,
                "current_path": request.path,
            }
        )

    def handle_p29_score(self):
        """
        Entrypoint for P29 score calculation and privacy enforcement.
        ---
        tags:
          - privacy-processing
        responses:
          200:
            description: P29 score calculated and context updated with results.
          400:
            description: Missing quasi-identifiers or sensitive attributes.
          500:
            description: Internal error during P29 score processing.
        """
        try:
            df = self._load_dataframe()
            quasi_idents, sens_attr, t_thresh, k_thresh, l_thresh = self._get_privacy_params()

            if not quasi_idents or not sens_attr:
                self._ctx["error"] = (
                    "Please select both quasi-identifiers and sensitive attributes."
                )
                return

            filtered_df = self._apply_privacy_enforcement(
                df, quasi_idents, sens_attr, t_thresh, k_thresh, l_thresh
            )
            self._save_dataframe(filtered_df)
            self._evaluate_and_update_context(df, quasi_idents, sens_attr)

        except Exception as e:
            raise GenericExceptionHandler(f"Failed to handle p_29 score: {str(e)}", status_code=500)

    def _get_privacy_params(self):
        """
        Extract privacy parameters from session.
        ---
        tags:
          - privacy-processing
        responses:
          200:
            description: Returns tuple (quasi_identifiers, sensitive_attributes, t_threshold, k_threshold, l_threshold).
        """
        return (
            session.get("quasi_identifiers", []),
            session.get("sensitive_attributes", []),
            session.get("t_threshold", 0.5),
            session.get("k_threshold", 1),
            session.get("l_threshold", 0.0),
        )

    def _apply_privacy_enforcement(self, df, quasi_idents, sens_attr, t, k, l):
        """
        Apply privacy enforcement algorithm to dataframe.
        ---
        tags:
          - privacy-processing
        parameters:
          - name: df
            in: body
            type: object
            required: true
            description: Input dataframe.
          - name: quasi_idents
            in: body
            type: array
            items:
              type: string
            required: true
            description: Quasi-identifiers.
          - name: sens_attr
            in: body
            type: array
            items:
              type: string
            required: true
            description: Sensitive attributes.
          - name: t
            in: body
            type: number
            required: true
            description: Threshold t.
          - name: k
            in: body
            type: number
            required: true
            description: Threshold k.
          - name: l
            in: body
            type: number
            required: true
            description: Threshold l.
        responses:
          200:
            description: Returns dataframe with privacy enforcement applied.
        """
        return enforce_privacy(df, quasi_idents, sens_attr, t, k, l)

    def _evaluate_and_update_context(self, df, quasi_idents, sens_attr):
        """
        Calculate P29 score and update context with results.
        ---
        tags:
          - privacy-processing
        parameters:
          - name: df
            in: body
            type: object
            required: true
            description: Original dataframe.
          - name: quasi_idents
            in: body
            type: array
            items:
              type: string
            required: true
            description: Quasi-identifiers.
          - name: sens_attr
            in: body
            type: array
            items:
              type: string
            required: true
            description: Sensitive attributes.
        responses:
          200:
            description: Context updated with P29 results.
        """
        res = P_29_score(df, quasi_idents, sens_attr)
        p29, problems, reasons, k_anon, min_l, max_t, _ = res

        self._update_context(
            {
                "result": res,
                "p29result": round(p29, 3),
                "minlresult": round(min_l, 3),
                "maxtresult": round(float(max_t), 3),
                "k_anonresult": k_anon,
                "reason_result": list(reasons)[:10],
                "problems_result": list(problems)[:10],
            }
        )


class DifferentialPrivacyHandler(BaseHandler):
    """
    Manage differential privacy noise addition to dataset columns.
    """

    def __init__(self):
        """
        Initialize handler and update context with path and column selections.
        ---
        tags:
          - differential-privacy
        responses:
          200:
            description: Context initialized.
        """
        super().__init__()

        # Load columns for display on GET requests
        try:
            df = self._load_dataframe()
            quasi_idents, sensitive_attr = self._get_quasi_and_sensitive()
            other_columns = self._get_other_columns(df, quasi_idents, sensitive_attr)
            columns = other_columns
        except:
            columns = []

        self._update_context(
            {
                "current_path": request.path,
                "columns": columns,
                "selected_columns": False,
            }
        )

    def handle_add_noise(self):
        """
        Add noise for differential privacy to selected columns.
        ---
        tags:
          - differential-privacy
        responses:
          200:
            description: Noise added and dataframe saved.
          400:
            description: Invalid column selection.
          500:
            description: Error during noise addition.
        """
        try:
            df = self._load_dataframe()
            quasi_idents, sensitive_attr = self._get_quasi_and_sensitive()
            other_columns = self._get_other_columns(df, quasi_idents, sensitive_attr)
            self._ctx.update({"columns": other_columns})

            categorical, numerical = self._get_selected_columns()

            if not self._validate_column_selection(other_columns, categorical, numerical):
                self._ctx["error"] = (
                    "Please select all columns. You cannot select a column in both lists."
                )
                return

            self._update_selected_columns(categorical, numerical)
            df_noisy = self._add_noise(df, categorical, numerical, epsilon=2.0)
            self._save_dataframe(df_noisy)

            self._update_context({"selected_columns": True})

        except Exception as e:
            raise GenericExceptionHandler(f"Noise addition failed: {str(e)}", status_code=500)

    def _get_quasi_and_sensitive(self):
        """
        Retrieve quasi-identifiers and sensitive attributes from session.
        ---
        tags:
          - differential-privacy
        responses:
          200:
            description: Returns tuple (quasi_identifiers, sensitive_attributes).
        """
        return (
            session.get("quasi_identifiers", []),
            session.get("sensitive_attributes", []),
        )

    def _get_other_columns(self, df, quasi_idents, sensitive_attr):
        """
        Get columns excluding quasi-identifiers and sensitive attributes.
        ---
        tags:
          - differential-privacy
        parameters:
          - name: df
            in: body
            type: object
            required: true
            description: Input dataframe.
          - name: quasi_idents
            in: body
            type: array
            items:
              type: string
            required: true
            description: Quasi-identifiers.
          - name: sensitive_attr
            in: body
            type: array
            items:
              type: string
            required: true
            description: Sensitive attributes.
        responses:
          200:
            description: List of column names not in quasi-identifiers or sensitive attributes.
        """
        all_columns = df.columns.tolist()
        return [col for col in all_columns if col not in quasi_idents + sensitive_attr]

    def _get_selected_columns(self):
        """
        Get selected categorical and numerical columns from form request.
        ---
        tags:
          - differential-privacy
        responses:
          200:
            description: Tuple (categorical_columns, numerical_columns) selected by user.
        """
        return (
            request.form.getlist("categorical_columns"),
            request.form.getlist("numerical_columns"),
        )

    def _validate_column_selection(self, valid_columns, categorical, numerical):
        """
        Validate selected columns are subsets of valid columns and disjoint.
        ---
        tags:
          - differential-privacy
        parameters:
          - name: valid_columns
            in: body
            type: array
            items:
              type: string
            required: true
            description: Valid columns for selection.
          - name: categorical
            in: body
            type: array
            items:
              type: string
            required: true
            description: Selected categorical columns.
          - name: numerical
            in: body
            type: array
            items:
              type: string
            required: true
            description: Selected numerical columns.
        responses:
          200:
            description: True if selection is valid, else False.
        """
        return validate_column_selection(valid_columns, categorical, numerical)

    def _update_selected_columns(self, categorical, numerical):
        """
        Save selected categorical and numerical columns to session.
        ---
        tags:
          - differential-privacy
        parameters:
          - name: categorical
            in: body
            type: array
            items:
              type: string
            required: true
            description: Selected categorical columns.
          - name: numerical
            in: body
            type: array
            items:
              type: string
            required: true
            description: Selected numerical columns.
        responses:
          200:
            description: Session updated with selected columns.
        """
        self._update_session(
            {
                "categorical_columns": categorical,
                "numerical_columns": numerical,
            }
        )

    def _add_noise(self, df, categorical, numerical, epsilon):
        """
        Add differential privacy noise to specified columns in dataframe.
        ---
        tags:
          - differential-privacy
        parameters:
          - name: df
            in: body
            type: object
            required: true
            description: Input dataframe.
          - name: categorical
            in: body
            type: array
            items:
              type: string
            required: true
            description: Categorical columns to add noise to.
          - name: numerical
            in: body
            type: array
            items:
              type: string
            required: true
            description: Numerical columns to add noise to.
          - name: epsilon
            in: body
            type: number
            required: true
            description: Privacy budget parameter.
        responses:
          200:
            description: Dataframe with noise added.
        """
        return add_noise_to_df(df, categorical, numerical, epsilon)
