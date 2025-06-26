TEST_EMAIL = "test_user_1@test.com"
TEST_PASSWORD = "aBJ3%!fj0_f42h2pvw3"
TEST_FAULTY_REPEAT = TEST_PASSWORD + " "


class TestAuthenticationUserExists:
    def test_success_register(self, registered_user):
        response = registered_user[0]
        assert response.status_code == 200

    def test_dup_email(self, registered_user, client):
        _ = registered_user
        response = client.post(
            "/auth/register",
            data={"email": TEST_EMAIL, "password": TEST_PASSWORD},
        )
        assert response.status_code == 409

    def test_no_password(self, client):
        response = client.post("/auth/login", data={"email": TEST_EMAIL})
        assert response.status_code == 400

    def test_bad_passwords(self, client):
        responses = []
        for password in ["a", "aBc1", "ab#1", "AB#1", "aBc#"]:
            data = {"email": TEST_EMAIL, "password": password}
            responses.append(client.post("/auth/register", data=data))

        for response in responses:
            assert response.status_code == 400


class TestAuthenticationUserNotExists:
    def test_user_not_exist(self, client):
        response = client.post(
            "/auth/login", data={"email": TEST_EMAIL, "password": TEST_PASSWORD}
        )
        assert response.status_code == 400

    def test_no_password(self, client):
        response = client.post("/auth/login", data={"email": TEST_PASSWORD})
        assert response.status_code == 400

    def test_bad_passwords(self, client):
        responses = []
        for password in ["a", "aBc1", "ab#1", "AB#1", "aBc#"]:
            data = {"email": TEST_EMAIL, "password": password}
            responses.append(client.post("/auth/register", data=data))

        for response in responses:
            assert response.status_code == 400
