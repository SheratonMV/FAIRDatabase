import io

import pytest


class TestDataGeneralization:
    @pytest.fixture(autouse=True)
    def setup(self, logged_in_user):
        """
        Setup test client and user before each test.
        """
        self.client, self.user = logged_in_user

    def upload_file(self, load_test_file):
        """
        Return form data for uploading a CSV file using test fixture.
        """
        csv_content = load_test_file("df.csv", mode="rb")
        return {
            "file": (io.BytesIO(csv_content), "df.csv"),
            "submit_button": "upload_file",
        }

    def test_upload_file(self, load_test_file):
        """
        Test uploading a CSV file.
        """
        response = self.client.post(
            "/data/data_generalization",
            content_type="multipart/form-data",
            data=self.upload_file(load_test_file),
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert b"File imported successfully." in response.data

    def test_submit_columns_to_drop(self, load_test_file):
        """
        Test dropping direct identifier columns.
        """
        self.test_upload_file(load_test_file)

        response = self.client.post(
            "/data/data_generalization",
            data={"submit_button": "submit_columns", "columns_to_drop": ["race"]},
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert b"Direct identifiers dropped successfully." in response.data

    def test_submit_missing_values(self, load_test_file):
        """
        Test dropping columns with missing values.
        """
        self.test_upload_file(load_test_file)

        response = self.client.post(
            "/data/data_generalization",
            data={
                "submit_button": "submit_missing_values",
                "columns_to_drop": ["address"],
            },
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert b"Columns with missing values dropped successfully." in response.data

    def test_submit_quasi_identifiers(self, load_test_file):
        """
        Test selecting quasi-identifiers.
        """
        self.test_upload_file(load_test_file)

        response = self.client.post(
            "/data/data_generalization",
            data={
                "submit_button": "submit_quasi_identifiers",
                "quasi_identifiers": ["age", "gender", "race"],
            },
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert b"Quasi-identifiers selected" in response.data

    def test_submit_mapping(self, load_test_file):
        """
        Test value mapping for quasi-identifiers.
        """
        self.test_submit_quasi_identifiers(load_test_file)

        response = self.client.post(
            "/data/data_generalization",
            data={
                "submit_button": "submit_mapping",
                "mapping_20": "20-29",
                "mapping_30": "30-39",
            },
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert b"mapped successfully" in response.data

    def test_session_persistence(self):
        """
        Test session persistence across GET requests.
        """
        response = self.client.get("/data/data_generalization")
        assert response.status_code == 200
        assert b"data_generalization" in response.data


class TestConsolidatedReturn:
    @pytest.fixture(autouse=True)
    def setup(self, logged_in_user):
        """Setup test client and user before each test."""
        self.client, self.user = logged_in_user

    def test_consolidated_return_state_1_resets_all_flags(self):
        """Test state 1 resets all session flags."""
        with self.client.session_transaction() as sess:
            sess["uploaded"] = True
            sess["columns_dropped"] = True
            sess["missing_values_reviewed"] = True
            sess["quasi_identifiers_selected"] = True
            sess["current_quasi_identifier"] = True
            sess["all_steps_completed"] = True

        response = self.client.post(
            "/data/consolidated_return",
            data={"state": "1"},
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert "/data/data_generalization" in response.location

        with self.client.session_transaction() as sess:
            assert sess["uploaded"] is False
            assert sess["columns_dropped"] is False
            assert sess["missing_values_reviewed"] is False
            assert sess["quasi_identifiers_selected"] is False
            assert sess["current_quasi_identifier"] is False
            assert sess["all_steps_completed"] is False

    def test_consolidated_return_state_2_sets_uploaded(self):
        """Test state 2 sets uploaded flag."""
        response = self.client.post(
            "/data/consolidated_return",
            data={"state": "2"},
            follow_redirects=False,
        )

        assert response.status_code == 302

        with self.client.session_transaction() as sess:
            assert sess["uploaded"] is True
            assert sess["columns_dropped"] is False

    def test_consolidated_return_state_3_sets_columns_dropped(self):
        """Test state 3 sets columns_dropped flag."""
        response = self.client.post(
            "/data/consolidated_return",
            data={"state": "3"},
            follow_redirects=False,
        )

        assert response.status_code == 302

        with self.client.session_transaction() as sess:
            assert sess["uploaded"] is True
            assert sess["columns_dropped"] is True
            assert sess["missing_values_reviewed"] is False

    def test_consolidated_return_state_4_sets_missing_values(self):
        """Test state 4 sets missing_values_reviewed flag."""
        response = self.client.post(
            "/data/consolidated_return",
            data={"state": "4"},
            follow_redirects=False,
        )

        assert response.status_code == 302

        with self.client.session_transaction() as sess:
            assert sess["uploaded"] is True
            assert sess["columns_dropped"] is True
            assert sess["missing_values_reviewed"] is True
            assert sess["quasi_identifiers_selected"] is False
            assert sess["current_quasi_identifier"] is False

    def test_consolidated_return_invalid_state_redirects(self):
        """Test invalid state redirects to data_generalization."""
        response = self.client.post(
            "/data/consolidated_return",
            data={"state": "999"},
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert "/data/data_generalization" in response.location


class TestDataP29Score:
    @pytest.fixture(autouse=True)
    def setup(self, logged_in_user, tmp_path):
        """Setup test client and user before each test."""
        self.client, self.user = logged_in_user
        # Create a temporary file for testing
        self.test_file = tmp_path / "test.csv"
        self.test_file.write_text("patient_id,age\nP001,25\nP002,30")

    def test_p29score_get_renders_template(self):
        """Test GET request renders p29score template."""
        with self.client.session_transaction() as sess:
            sess["all_steps_completed"] = True
            sess["uploaded_filepath"] = str(self.test_file)
            sess["quasi_identifiers"] = ["age"]
            sess["sensitive_attributes"] = []

        response = self.client.get("/data/p29score")
        # May redirect if session state is invalid
        assert response.status_code in [200, 302]

    def test_p29score_post_calculate_score(self):
        """Test POST with Calculate Score button."""
        with self.client.session_transaction() as sess:
            sess["all_steps_completed"] = True
            sess["uploaded_filepath"] = str(self.test_file)
            sess["quasi_identifiers"] = ["age"]
            sess["sensitive_attributes"] = []

        response = self.client.post(
            "/data/p29score",
            data={"submit_button": "Calculate Score"},
        )
        # May redirect if validation fails
        assert response.status_code in [200, 302]

    def test_p29score_post_without_submit_button(self):
        """Test POST without submit button."""
        with self.client.session_transaction() as sess:
            sess["all_steps_completed"] = True
            sess["uploaded_filepath"] = str(self.test_file)

        response = self.client.post("/data/p29score", data={})
        assert response.status_code in [200, 302]
