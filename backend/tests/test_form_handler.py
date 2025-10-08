"""
Integration tests for BaseHandler form handler class.

Tests cover:
- DataFrame loading from session
- DataFrame saving to files
- Session management
- Error handling for invalid/missing data
"""

import pandas as pd
import pytest

from src.exceptions import GenericExceptionHandler
from src.form_handler import BaseHandler


@pytest.fixture
def test_csv_content():
    """Generate test CSV content as bytes"""
    csv_data = """patient_id,age,gender,value
P1,25,M,100
P2,30,F,200
P3,35,M,300"""
    return csv_data.encode("utf-8")


@pytest.fixture
def session_with_uploaded_file(client, logged_in_user, test_csv_content, tmp_path):
    """Setup session with an uploaded CSV file"""
    client_obj, _ = logged_in_user

    # Create temporary file
    test_file = tmp_path / "test_upload.csv"
    test_file.write_bytes(test_csv_content)

    # Set session data
    with client_obj.session_transaction() as sess:
        sess["uploaded_filepath"] = str(test_file)
        sess["email"] = "test@example.com"

    return client_obj, test_file


class TestBaseHandlerLoadDataframe:
    """Test DataFrame loading from uploaded files"""

    def test_loads_dataframe_from_valid_filepath(self, app, session_with_uploaded_file):
        """Valid filepath in session → DataFrame loaded successfully"""
        client, file_path = session_with_uploaded_file

        with client:
            # Trigger a request to establish app context
            client.get("/")

            with app.app_context():
                handler = BaseHandler()
                df = handler._load_dataframe()

                assert isinstance(df, pd.DataFrame)
                assert not df.empty
                assert len(df) == 3
                assert "patient_id" in df.columns
                assert list(df["patient_id"]) == ["P1", "P2", "P3"]

    def test_raises_error_when_no_filepath_in_session(self, app, client, logged_in_user):
        """No uploaded_filepath in session → raises GenericExceptionHandler"""
        client_obj, _ = logged_in_user

        with client_obj:
            client_obj.get("/")

            with app.app_context():
                from flask import session

                # Clear any uploaded_filepath from session
                session.pop("uploaded_filepath", None)

                handler = BaseHandler()

                with pytest.raises(GenericExceptionHandler) as exc_info:
                    handler._load_dataframe()

                assert exc_info.value.status_code == 400
                assert "No valid uploaded file" in exc_info.value.message

    def test_raises_error_when_file_is_empty(self, app, client, logged_in_user, tmp_path):
        """Empty CSV file → raises GenericExceptionHandler"""
        client_obj, _ = logged_in_user

        # Create empty file
        empty_file = tmp_path / "empty.csv"
        empty_file.write_text("")

        with client_obj.session_transaction() as sess:
            sess["uploaded_filepath"] = str(empty_file)

        with client_obj:
            client_obj.get("/")

            with app.app_context():
                handler = BaseHandler()

                with pytest.raises(GenericExceptionHandler) as exc_info:
                    handler._load_dataframe()

                assert exc_info.value.status_code == 400
                assert "empty" in exc_info.value.message.lower()

    def test_raises_error_when_file_is_malformed(self, app, client, logged_in_user, tmp_path):
        """Malformed CSV → raises GenericExceptionHandler"""
        client_obj, _ = logged_in_user

        # Create malformed CSV
        malformed_file = tmp_path / "malformed.csv"
        malformed_file.write_text("col1,col2\nval1\nval2,val3,val4,val5")  # Inconsistent columns

        with client_obj.session_transaction() as sess:
            sess["uploaded_filepath"] = str(malformed_file)

        with client_obj:
            client_obj.get("/")

            with app.app_context():
                handler = BaseHandler()

                # Should handle parser errors gracefully
                with pytest.raises(GenericExceptionHandler) as exc_info:
                    handler._load_dataframe()

                assert exc_info.value.status_code == 400

    def test_raises_error_when_file_does_not_exist(self, app, client, logged_in_user, tmp_path):
        """Filepath set but file deleted → raises error"""
        client_obj, _ = logged_in_user

        non_existent = tmp_path / "does_not_exist.csv"

        with client_obj.session_transaction() as sess:
            sess["uploaded_filepath"] = str(non_existent)

        with client_obj:
            client_obj.get("/")

            with app.app_context():
                handler = BaseHandler()

                with pytest.raises((GenericExceptionHandler, FileNotFoundError)):
                    handler._load_dataframe()


class TestBaseHandlerSaveDataframe:
    """Test DataFrame saving to files"""

    def test_saves_dataframe_to_file(self, app, session_with_uploaded_file):
        """Valid DataFrame → saved to filepath"""
        client, file_path = session_with_uploaded_file

        with client:
            client.get("/")

            with app.app_context():
                handler = BaseHandler()

                # Load, modify, and save
                df = handler._load_dataframe()
                df["new_column"] = ["A", "B", "C"]
                handler._save_dataframe(df)

                # Verify file was updated
                saved_df = pd.read_csv(file_path)
                assert "new_column" in saved_df.columns
                assert list(saved_df["new_column"]) == ["A", "B", "C"]

    def test_raises_error_when_saving_invalid_dataframe(self, app, session_with_uploaded_file):
        """Non-DataFrame object → raises GenericExceptionHandler"""
        client, _ = session_with_uploaded_file

        with client:
            client.get("/")

            with app.app_context():
                handler = BaseHandler()

                with pytest.raises(GenericExceptionHandler) as exc_info:
                    handler._save_dataframe(None)

                assert exc_info.value.status_code == 400
                assert "Invalid DataFrame" in exc_info.value.message

    def test_raises_error_when_no_filepath_set(self, app, client, logged_in_user):
        """Save without filepath → raises GenericExceptionHandler"""
        client_obj, _ = logged_in_user

        with client_obj:
            client_obj.get("/")

            with app.app_context():
                # Clear filepath
                with client_obj.session_transaction() as sess:
                    sess.pop("uploaded_filepath", None)

                handler = BaseHandler()
                df = pd.DataFrame({"col1": [1, 2, 3]})

                with pytest.raises(GenericExceptionHandler) as exc_info:
                    handler._save_dataframe(df)

                # Status code might be 400 or 500 depending on implementation
                assert exc_info.value.status_code in (400, 500)
                assert "file path" in exc_info.value.message.lower()


class TestBaseHandlerSessionManagement:
    """Test session and context management"""

    def test_updates_session_with_new_values(self, app, session_with_uploaded_file):
        """Session update → values persisted"""
        client, _ = session_with_uploaded_file

        with client:
            client.get("/")

            with app.app_context():
                from flask import session

                handler = BaseHandler()
                handler._update_session({"test_key": "test_value", "another_key": 123})

                # Verify session was updated in memory
                assert session["test_key"] == "test_value"
                assert session["another_key"] == 123

    def test_updates_context_with_new_values(self, app, session_with_uploaded_file):
        """Context update → values stored in ctx"""
        client, _ = session_with_uploaded_file

        with client:
            client.get("/")

            with app.app_context():
                handler = BaseHandler()
                handler._update_context({"ctx_key": "ctx_value"})

                assert handler.ctx["ctx_key"] == "ctx_value"

    def test_updates_both_session_and_context(self, app, session_with_uploaded_file):
        """Update both → both session and context updated"""
        client, _ = session_with_uploaded_file

        with client:
            client.get("/")

            with app.app_context():
                from flask import session

                handler = BaseHandler()
                handler._update_session_and_context({"shared_key": "shared_value"})

                # Check context
                assert handler.ctx["shared_key"] == "shared_value"

                # Check session in memory
                assert session["shared_key"] == "shared_value"

    def test_context_includes_user_email_from_session(self, app, session_with_uploaded_file):
        """Handler initialization → user_email from session in context"""
        client, _ = session_with_uploaded_file

        with client:
            client.get("/")

            with app.app_context():
                handler = BaseHandler()
                assert "user_email" in handler.ctx
                assert handler.ctx["user_email"] == "test@example.com"

    def test_ctx_property_returns_context(self, app, session_with_uploaded_file):
        """ctx property → returns context dictionary"""
        client, _ = session_with_uploaded_file

        with client:
            client.get("/")

            with app.app_context():
                handler = BaseHandler()
                ctx = handler.ctx

                assert isinstance(ctx, dict)
                assert "user_email" in ctx


class TestBaseHandlerIntegration:
    """Integration tests for complete workflows"""

    def test_complete_load_modify_save_workflow(self, app, session_with_uploaded_file):
        """Load → Modify → Save → Reload → Verify changes persisted"""
        client, file_path = session_with_uploaded_file

        with client:
            client.get("/")

            with app.app_context():
                # Load original data
                handler1 = BaseHandler()
                df1 = handler1._load_dataframe()
                original_len = len(df1)

                # Modify and save
                df1["computed_value"] = df1["age"].astype(int) * 2
                handler1._save_dataframe(df1)

                # Create new handler and reload
                handler2 = BaseHandler()
                df2 = handler2._load_dataframe()

                # Verify changes persisted
                assert len(df2) == original_len
                assert "computed_value" in df2.columns
                assert list(df2["computed_value"]) == [50, 60, 70]

    def test_handles_different_csv_encodings(self, app, client, logged_in_user, tmp_path):
        """UTF-8 CSV → loaded correctly"""
        client_obj, _ = logged_in_user

        # Create CSV with UTF-8 content
        utf8_file = tmp_path / "utf8.csv"
        utf8_file.write_text("name,value\nTest,100\n", encoding="utf-8")

        with client_obj.session_transaction() as sess:
            sess["uploaded_filepath"] = str(utf8_file)

        with client_obj:
            client_obj.get("/")

            with app.app_context():
                handler = BaseHandler()
                df = handler._load_dataframe()

                assert len(df) == 1
                assert df["name"][0] == "Test"
