"""
Base handler module for managing session-based data operations
and DataFrame persistence.
"""

import pandas as pd
from flask import session
from src.exceptions import GenericExceptionHandler


class BaseHandler:
    """A base class for handling session-based data operations with robust error handling."""

    def __init__(self):
        """
        Initialize BaseHandler with session data.
        """
        self._session = session
        self._ctx = {
            "user_email": self._session.get("email"),
        }
        self._filepath = None

    def _load_dataframe(self):
        """
        Load DataFrame from the uploaded file path stored in session.
        """
        try:
            self._filepath = self._filepath or self._session.get(
                "uploaded_filepath", ""
            )

            if not self._filepath:
                raise GenericExceptionHandler(
                    "No valid uploaded file found in session.", status_code=400
                )

            df = pd.read_csv(self._filepath)
            if df.empty:
                raise GenericExceptionHandler(
                    "Uploaded file is empty.",
                    status_code=400,
                    redirect_to="dashboard_routes.return_to_dashboard",
                )
            return df

        except pd.errors.EmptyDataError:
            raise GenericExceptionHandler(
                "Uploaded file is empty or invalid.",
                status_code=400,
                redirect_to="dashboard.return_to_dashboard",
            )

        except pd.errors.ParserError as e:
            raise GenericExceptionHandler(
                f"Failed to parse CSV file: {str(e)}",
                status_code=400,
                redirect_to="dashboard.return_to_dashboard",
            )

    def _save_dataframe(self, df):
        """
        Save DataFrame to the uploaded file path.
        """
        if df is None or not isinstance(df, pd.DataFrame):
            raise GenericExceptionHandler(
                "Invalid DataFrame provided.", status_code=400
            )

        try:
            if not self._filepath:
                raise GenericExceptionHandler(
                    "No file path set for saving DataFrame.", status_code=400
                )

            df.to_csv(self._filepath, index=False)
        except Exception as e:
            raise GenericExceptionHandler(
                f"Failed to save DataFrame: {str(e)}", status_code=500
            )

    def _update_session(self, updates):
        """
        Update session with provided key-value pairs.
        """
        try:
            self._session.update(updates)
            if hasattr(self._session, "modified"):
                self._session.modified = True
        except Exception as e:
            raise GenericExceptionHandler(
                f"Failed to update session: {str(e)}", status_code=500
            )

    def _update_context(self, updates):
        """
        Update local context dictionary with provided key-value pairs.
        """
        self._ctx.update(updates)

    def _update_session_and_context(self, updates):
        """
        Update both session and context with provided key-value pairs.
        """
        self._update_session(updates)
        self._update_context(updates)

    @property
    def ctx(self):
        """Get the current context dictionary."""
        return self._ctx
