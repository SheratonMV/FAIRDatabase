import os
import shutil
import tempfile
import pytest


class TestPrivacyRoutes:

    @pytest.fixture(autouse=True)
    def setup_method(self, logged_in_user):
        self.client, self.user = logged_in_user
        # Construct filepath to test data file
        source_filepath = os.path.join(os.path.dirname(os.path.dirname(__file__)), "df.csv")

        # Create a temporary copy to avoid modifying the original test data
        self.temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False)
        self.temp_file.close()
        shutil.copy2(source_filepath, self.temp_file.name)
        self.filepath = self.temp_file.name

        with self.client.session_transaction() as sess:
            sess["email"] = self.user.email
            sess["uploaded_filepath"] = self.filepath
            sess["quasi_identifiers"] = ["age"]
            sess["sensitive_attributes"] = ["readmitted"]
            sess["t_threshold"] = 0.5
            sess["k_threshold"] = 1
            sess["l_threshold"] = 0.0

        yield

        # Cleanup temporary file
        if os.path.exists(self.filepath):
            os.unlink(self.filepath)

    def test_privacy_processing_success(self):
        response = self.client.get("/privacy/privacy_processing")
        assert response.status_code == 200
        assert b"p29result" in response.data or b"result" in response.data


class TestDifferentialPrivacy:

    @pytest.fixture(autouse=True)
    def setup_method(self, logged_in_user):
        self.client, self.user = logged_in_user
        # Construct filepath to test data file
        source_filepath = os.path.join(os.path.dirname(os.path.dirname(__file__)), "df.csv")

        # Create a temporary copy to avoid modifying the original test data
        self.temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False)
        self.temp_file.close()
        shutil.copy2(source_filepath, self.temp_file.name)
        self.filepath = self.temp_file.name

        with self.client.session_transaction() as sess:
            sess["email"] = self.user.email
            sess["uploaded_filepath"] = self.filepath
            sess["quasi_identifiers"] = ["age"]
            sess["sensitive_attributes"] = ["readmitted"]

        yield

        # Cleanup temporary file
        if os.path.exists(self.filepath):
            os.unlink(self.filepath)

    def test_differential_privacy_get_success(self):
        response = self.client.get("/privacy/differential_privacy")
        assert response.status_code == 200
        # Verify the page loaded successfully with differential privacy content
        assert b"Differential Privacy" in response.data or b"differential" in response.data.lower()

    def test_differential_privacy_post_success(self):
        # All columns excluding quasi_identifiers (age) and sensitive_attributes (readmitted)
        categorical_cols = [
            "A1Cresult", "acarbose", "acetohexamide", "admission_source_id",
            "change", "chlorpropamide", "citoglipton", "diabetesMed",
            "diag_1", "diag_2", "diag_3", "discharge_disposition_id",
            "examide", "gender", "glimepiride", "glimepiride-pioglitazone",
            "glipizide", "glipizide-metformin", "glyburide", "glyburide-metformin",
            "insulin", "max_glu_serum", "metformin", "metformin-pioglitazone",
            "metformin-rosiglitazone", "miglitol", "nateglinide", "pioglitazone",
            "race", "repaglinide", "rosiglitazone", "tolazamide",
            "tolbutamide", "troglitazone"
        ]
        numerical_cols = [
            "admission_type_id", "num_lab_procedures", "num_medications",
            "num_procedures", "number_diagnoses", "number_emergency",
            "number_inpatient", "number_outpatient", "time_in_hospital"
        ]
        data = {
            "categorical_columns": categorical_cols,
            "numerical_columns": numerical_cols,
        }
        response = self.client.post(
            "/privacy/differential_privacy", data=data, follow_redirects=True
        )
        assert response.status_code == 200
        # Verify the page loaded successfully with differential privacy content
        assert b"Differential Privacy" in response.data or b"differential" in response.data.lower()

    def test_differential_privacy_invalid_column_selection(self):
        data = {
            "categorical_columns": ["gender", "time_in_hospital"],
            "numerical_columns": ["time_in_hospital"],
        }
        response = self.client.post("/privacy/differential_privacy", data=data)
        assert response.status_code == 400
        assert b"Please select all columns" in response.data
