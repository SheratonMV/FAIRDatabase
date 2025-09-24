import pytest


class TestPrivacyRoutes:

    @pytest.fixture(autouse=True)
    def setup_method(self, logged_in_user, load_test_file):
        self.client, self.user = logged_in_user
        self.file = load_test_file

        with self.client.session_transaction() as sess:
            sess["email"] = self.user.email
            sess["uploaded_filepath"] = self.filepath
            sess["quasi_identifiers"] = ["age"]
            sess["sensitive_attributes"] = ["income"]
            sess["t_threshold"] = 0.5
            sess["k_threshold"] = 1
            sess["l_threshold"] = 0.0

    def test_privacy_processing_success(self):
        response = self.client.get("/privacy/privacy_processing")
        assert response.status_code == 200
        assert b"p29result" in response.data or b"result" in response.data


class TestDifferentialPrivacy:

    @pytest.fixture(autouse=True)
    def setup_method(self, logged_in_user, load_test_file):
        self.client, self.user = logged_in_user
        self.filepath = load_test_file

        with self.client.session_transaction() as sess:
            sess["email"] = self.user.email
            sess["uploaded_filepath"] = self.filepath
            sess["quasi_identifiers"] = ["age"]
            sess["sensitive_attributes"] = ["readmitted"]

    def test_differential_privacy_get_success(self):
        response = self.client.get("/privacy/differential_privacy")
        assert response.status_code == 200
        assert b"columns" in response.data or b"selected_columns" in response.data

    def test_differential_privacy_post_success(self):
        data = {
            "categorical_columns": ["gender", "race"],
            "numerical_columns": ["time_in_hospital", "num_lab_procedures"],
        }
        response = self.client.post(
            "/privacy/differential_privacy", data=data, follow_redirects=True
        )
        assert response.status_code == 200
        assert b"selected_columns" in response.data or b"columns" in response.data

    def test_differential_privacy_invalid_column_selection(self):
        data = {
            "categorical_columns": ["gender", "time_in_hospital"],
            "numerical_columns": ["time_in_hospital"],
        }
        response = self.client.post("/privacy/differential_privacy", data=data)
        assert response.status_code == 400
        assert b"Please select all columns" in response.data
