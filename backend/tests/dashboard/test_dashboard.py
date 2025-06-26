import io


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
