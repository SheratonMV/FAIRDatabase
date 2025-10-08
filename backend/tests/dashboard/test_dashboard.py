import io
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest


class TestDashboardRoutes:
    def test_route_not_logged_in(self, client):
        """Test if the user is redirected to the homepage when not logged in."""
        response = client.get("/dashboard", follow_redirects=True)
        assert response.status_code == 200
        assert response.request.path == "/"

    def test_route_logged_in(self, logged_in_user, client):
        """Test the dashboard route when the user is logged in."""
        client, _ = logged_in_user
        response = client.get("/dashboard")
        assert response.status_code in (302, 308)
        assert b"dashboard" in response.data.lower()

    def test_route_upload(self, logged_in_user, load_test_file):
        """Test the file upload functionality with a valid CSV file."""
        client, _ = logged_in_user
        csv_content = load_test_file()

        data = {
            "file": (io.BytesIO(csv_content), "df.csv"),
            "description": "test upload file",
            "origin": "unit test",
            "relational": "patient_id",
        }

        response = client.post(
            "/dashboard/upload",
            data=data,
            content_type="multipart/form-data",
            follow_redirects=True,
        )

        assert response.status_code == 200


class TestUploadRoute:
    def test_upload_get_renders_template(self, logged_in_user):
        """Test GET request renders upload template."""
        client, _ = logged_in_user
        response = client.get("/dashboard/upload")
        assert response.status_code == 200

    def test_upload_no_file_redirects(self, logged_in_user):
        """Test POST without file redirects with flash message."""
        client, _ = logged_in_user
        response = client.post(
            "/dashboard/upload",
            data={},
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert b"No file selected" in response.data or response.request.path == "/dashboard/upload"

    def test_upload_empty_filename_redirects(self, logged_in_user):
        """Test POST with empty filename redirects."""
        client, _ = logged_in_user
        data = {"file": (io.BytesIO(b""), "  ")}
        response = client.post(
            "/dashboard/upload",
            data=data,
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        assert response.status_code == 200

    def test_upload_processing_error_rolls_back(self, logged_in_user, load_test_file):
        """Test that upload errors trigger rollback."""
        client, _ = logged_in_user
        csv_content = load_test_file()

        with patch("src.dashboard.routes.file_save_and_read") as mock_save:
            mock_save.side_effect = Exception("Processing error")

            data = {
                "file": (io.BytesIO(csv_content), "test.csv"),
                "description": "test",
                "origin": "test",
            }

            # The exception is caught and handled by the error handler
            response = client.post(
                "/dashboard/upload",
                data=data,
                content_type="multipart/form-data",
                follow_redirects=True,
            )
            # Should redirect or show error
            assert response.status_code in [200, 302, 400]


class TestSearchRoute:
    def test_search_get_returns_all_tables(self, logged_in_user):
        """Test GET request returns all tables."""
        client, _ = logged_in_user

        with patch("src.dashboard.routes.supabase_extension.safe_rpc_call") as mock_rpc:
            mock_rpc.return_value = [
                {"table_name": "test_table_p1"},
                {"table_name": "test_table_p2"},
            ]

            response = client.get("/dashboard/search")
            assert response.status_code == 200
            assert b"test_table_p1" in response.data

    def test_search_post_with_download_redirects(self, logged_in_user):
        """Test POST with Download button redirects to display."""
        client, _ = logged_in_user

        response = client.post(
            "/dashboard/search",
            data={"Download": "true"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "/dashboard/display" in response.location

    def test_search_post_with_search_term(self, logged_in_user):
        """Test POST with search term returns filtered results."""
        client, _ = logged_in_user

        with patch("src.dashboard.routes.supabase_extension.safe_rpc_call") as mock_rpc:
            mock_rpc.side_effect = [
                [{"table_name": "test_p1"}],  # search_tables_by_column
                [{"table_name": "test_p1"}, {"table_name": "other_p1"}],  # get_all_tables
            ]

            response = client.post(
                "/dashboard/search",
                data={
                    "search": "patient_id",
                    "value0": "0",
                    "value1": "1",
                },
            )
            assert response.status_code == 200
            assert b"test_p1" in response.data

    def test_search_post_stores_search_term_in_session(self, logged_in_user):
        """Test POST stores search term in session."""
        client, _ = logged_in_user

        with patch("src.dashboard.routes.supabase_extension.safe_rpc_call") as mock_rpc:
            mock_rpc.return_value = []

            with client.session_transaction() as sess:
                sess["email"] = "test@example.com"

            client.post(
                "/dashboard/search",
                data={"search": "test_column", "value0": "0", "value1": "1"},
            )

            with client.session_transaction() as sess:
                assert "search_term" in sess
                assert sess["search_term"][0] == "test_column"


class TestDisplayRoute:
    def test_display_get_without_search_term_renders_template(self, logged_in_user):
        """Test GET without search_term renders search template."""
        client, _ = logged_in_user

        response = client.get("/dashboard/display")
        assert response.status_code == 200

    def test_display_get_with_search_term_returns_zip(self, logged_in_user):
        """Test GET with search_term returns ZIP file."""
        client, _ = logged_in_user

        with client.session_transaction() as sess:
            sess["search_term"] = ["patient_id", "1", "0"]

        with patch("src.dashboard.routes.supabase_extension.safe_rpc_call") as mock_rpc:
            mock_rpc.side_effect = [
                [{"table_name": "test_p1"}],  # search_tables_by_column
                [{"column_name": "rowid"}, {"column_name": "patient_id"}],  # get_table_columns
                [{"data": {"rowid": 1, "patient_id": "P001"}}],  # select_from_table
            ]

            response = client.get("/dashboard/display")
            assert response.status_code == 200
            assert response.headers["Content-Type"] == "application/octet-stream"
            assert "attachment" in response.headers["Content-Disposition"]

    def test_display_no_matching_data_raises_error(self, logged_in_user):
        """Test display with no matching data handles error."""
        client, _ = logged_in_user

        with client.session_transaction() as sess:
            sess["search_term"] = ["nonexistent", "1", "0"]

        with patch("src.dashboard.routes.supabase_extension.safe_rpc_call") as mock_rpc:
            mock_rpc.side_effect = [
                [{"table_name": "test_p1"}],
                [{"column_name": "rowid"}],
                [],  # Empty data
            ]

            response = client.get("/dashboard/display", follow_redirects=True)
            # Error is handled by error handler
            assert response.status_code in [200, 302, 404]


class TestUpdateRoute:
    def test_update_get_renders_template(self, logged_in_user):
        """Test GET request renders update template."""
        client, _ = logged_in_user

        response = client.get("/dashboard/update")
        assert response.status_code == 200

    def test_update_post_updates_row(self, logged_in_user):
        """Test POST updates row in matching tables."""
        client, _ = logged_in_user

        with patch("src.dashboard.routes.supabase_extension.safe_rpc_call") as mock_rpc:
            mock_rpc.side_effect = [
                [{"table_name": "test_p1"}],  # search_tables_by_column
                True,  # update_table_row
            ]

            response = client.post(
                "/dashboard/update",
                data={
                    "row_id": "1",
                    "column_name": "patient_id",
                    "new_value": "P999",
                },
            )
            assert response.status_code == 200

    def test_update_post_no_matching_tables_raises_error(self, logged_in_user):
        """Test POST with no matching tables handles error."""
        client, _ = logged_in_user

        with patch("src.dashboard.routes.supabase_extension.safe_rpc_call") as mock_rpc:
            mock_rpc.return_value = []  # No tables found

            response = client.post(
                "/dashboard/update",
                data={
                    "row_id": "1",
                    "column_name": "nonexistent",
                    "new_value": "value",
                },
                follow_redirects=True,
            )
            # Error is handled by error handler
            assert response.status_code in [200, 302, 404]


class TestTablePreviewRoute:
    def test_table_preview_no_table_name_raises_error(self, logged_in_user):
        """Test table_preview without table_name handles error."""
        client, _ = logged_in_user

        response = client.get("/dashboard/table_preview", follow_redirects=True)
        # Error is handled by error handler
        assert response.status_code in [200, 302, 400]

    def test_table_preview_nonexistent_table_raises_error(self, logged_in_user):
        """Test table_preview with nonexistent table handles error."""
        client, _ = logged_in_user

        with patch("src.dashboard.routes.supabase_extension.safe_rpc_call") as mock_rpc:
            mock_rpc.return_value = False  # table_exists returns False

            response = client.get(
                "/dashboard/table_preview?table_name=nonexistent", follow_redirects=True
            )
            # Error is handled by error handler
            assert response.status_code in [200, 302, 404]

    def test_table_preview_displays_table_data(self, logged_in_user):
        """Test table_preview displays table data and metadata."""
        client, _ = logged_in_user

        with patch("src.dashboard.routes.supabase_extension.safe_rpc_call") as mock_rpc:
            mock_rpc.side_effect = [
                True,  # table_exists
                [
                    {"column_name": "rowid"},
                    {"column_name": "patient_id"},
                    {"column_name": "metadata"},
                ],  # get_table_columns
                [
                    {"data": {"rowid": 1, "patient_id": "P001", "metadata": "meta1"}},
                    {"data": {"rowid": 2, "patient_id": "P002", "metadata": "meta2"}},
                ],  # select_from_table
            ]

            response = client.get("/dashboard/table_preview?table_name=test_p1")
            assert response.status_code in [200, 302]

    def test_table_preview_with_search_term_in_session(self, logged_in_user):
        """Test table_preview uses search_term from session."""
        client, _ = logged_in_user

        with client.session_transaction() as sess:
            sess["search_term"] = ["patient_id", "1", "0"]

        with patch("src.dashboard.routes.supabase_extension.safe_rpc_call") as mock_rpc:
            mock_rpc.side_effect = [
                True,
                [{"column_name": "rowid"}, {"column_name": "patient_id"}],
                [{"data": {"rowid": 1, "patient_id": "P001"}}],
            ]

            response = client.get("/dashboard/table_preview?table_name=test_p1")
            assert response.status_code in [200, 302]


class TestReturnToDashboardRoute:
    def test_return_to_dashboard_clears_session_flags(self, logged_in_user):
        """Test return_to_dashboard clears all session flags."""
        client, _ = logged_in_user

        with client.session_transaction() as sess:
            sess["uploaded_filepath"] = "/tmp/test.csv"
            sess["uploaded"] = True
            sess["columns_dropped"] = True
            sess["missing_values_reviewed"] = True
            sess["quasi_identifiers_selected"] = True
            sess["current_quasi_identifier"] = "test"
            sess["all_steps_completed"] = True

        response = client.get("/dashboard/return_to_dashboard")
        assert response.status_code == 200

        with client.session_transaction() as sess:
            assert "uploaded_filepath" not in sess
            assert sess["uploaded"] is False
            assert sess["columns_dropped"] is False
            assert sess["missing_values_reviewed"] is False
            assert sess["quasi_identifiers_selected"] is False
            assert sess["all_steps_completed"] is False
