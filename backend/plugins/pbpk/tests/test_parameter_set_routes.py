import pytest


class TestParameterSetRoutes:
    def test_create_parameter_set_returns_201(self, curator_user, app):
        client, _ = curator_user
        resp = client.post(
            "/model/parameter-sets",
            json={"name": "PFOA Default", "description": "Standard PFOA", "params": {"HalfLife": 2.5}},
            content_type="application/json",
        )
        assert resp.status_code == 201
        data = resp.get_json()
        assert "id" in data
        assert data["name"] == "PFOA Default"

        # Cleanup
        with app.app_context():
            from app import get_db
            db = get_db()
            cur = db.cursor()
            cur.execute("DELETE FROM _fd.pbpk_parameter_sets WHERE id = %s", (data["id"],))
            db.commit()
            cur.close()

    def test_create_parameter_set_missing_name_returns_400(self, curator_user):
        client, _ = curator_user
        resp = client.post(
            "/model/parameter-sets",
            json={"params": {"HalfLife": 2.5}},
            content_type="application/json",
        )
        assert resp.status_code == 400
        assert "name" in resp.get_json()["error"]

    def test_list_parameter_sets_returns_200(self, curator_user, app):
        client, _ = curator_user
        # Create one first
        resp = client.post(
            "/model/parameter-sets",
            json={"name": "List Test", "params": {}},
            content_type="application/json",
        )
        ps_id = resp.get_json()["id"]

        resp = client.get("/model/parameter-sets")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)
        ids = [r["id"] for r in data]
        assert ps_id in ids
        # Params blob must not be included in list
        assert all("params" not in r for r in data)

        with app.app_context():
            from app import get_db
            db = get_db()
            cur = db.cursor()
            cur.execute("DELETE FROM _fd.pbpk_parameter_sets WHERE id = %s", (ps_id,))
            db.commit()
            cur.close()

    def test_get_single_parameter_set_returns_200(self, curator_user, app):
        client, _ = curator_user
        resp = client.post(
            "/model/parameter-sets",
            json={"name": "Single Get Test", "params": {"HalfLife": 7.0, "RateInj": 0.2}},
            content_type="application/json",
        )
        ps_id = resp.get_json()["id"]

        resp = client.get(f"/model/parameter-sets/{ps_id}")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["id"] == ps_id
        assert data["params"]["HalfLife"] == pytest.approx(7.0)

        with app.app_context():
            from app import get_db
            db = get_db()
            cur = db.cursor()
            cur.execute("DELETE FROM _fd.pbpk_parameter_sets WHERE id = %s", (ps_id,))
            db.commit()
            cur.close()

    def test_get_nonexistent_parameter_set_returns_404(self, curator_user):
        client, _ = curator_user
        resp = client.get("/model/parameter-sets/999999999")
        assert resp.status_code == 404
