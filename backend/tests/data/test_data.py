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
