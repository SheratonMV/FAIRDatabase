"""Live-DB tests for the /vfl blueprint — real engine, no upstream mocks.

Mutation routes require curator/admin, so most tests use the `curator_user`
fixture (see conftest.py) rather than the unauthenticated-302 style alone.
"""
import pytest


class TestUnauthenticated:
    def test_create_task_redirects_when_not_logged_in(self, client):
        resp = client.post("/vfl/tasks", json={}, content_type="application/json")
        assert resp.status_code == 302

    def test_list_tasks_redirects_when_not_logged_in(self, client):
        resp = client.get("/vfl/tasks")
        assert resp.status_code == 302

    def test_get_nonexistent_task_redirects_when_not_logged_in(self, client):
        resp = client.get("/vfl/tasks/00000000-0000-0000-0000-000000000000")
        assert resp.status_code == 302


class TestTaskCRUD:
    def test_create_task_missing_fields_returns_400(self, curator_user):
        client, _ = curator_user
        resp = client.post("/vfl/tasks", json={}, content_type="application/json")
        assert resp.status_code == 400
        assert "Missing fields" in resp.get_json()["error"]

    def test_create_task_calibrates_sigma_from_epsilon(self, curator_user, vfl_task_cleanup):
        """A tight epsilon budget must not fall back to the old flat sigma=1.0
        default — task_sigma should be calibrated and > 1.0 here."""
        client, _ = curator_user
        resp = client.post(
            "/vfl/tasks",
            json={"dp_epsilon": 0.1, "rounds_total": 10, "task_types": ["binary"], "n_parties": 2},
            content_type="application/json",
        )
        assert resp.status_code == 201
        task_id = resp.get_json()["task_id"]
        vfl_task_cleanup.append(task_id)

        task = client.get(f"/vfl/tasks/{task_id}").get_json()
        assert task["task_sigma"]
        assert task["task_sigma"]["task_0"] > 1.0

    def test_create_task_respects_explicit_task_sigma(self, curator_user, vfl_task_cleanup):
        client, _ = curator_user
        resp = client.post(
            "/vfl/tasks",
            json={
                "dp_epsilon": 1.0, "rounds_total": 10, "task_types": ["binary"],
                "task_sigma": {"task_0": 2.5},
            },
            content_type="application/json",
        )
        assert resp.status_code == 201
        task_id = resp.get_json()["task_id"]
        vfl_task_cleanup.append(task_id)

        task = client.get(f"/vfl/tasks/{task_id}").get_json()
        assert task["task_sigma"]["task_0"] == pytest.approx(2.5)

    def test_list_tasks_includes_created_task(self, curator_user, vfl_task_cleanup):
        client, _ = curator_user
        resp = client.post(
            "/vfl/tasks",
            json={"dp_epsilon": 1.0, "rounds_total": 5},
            content_type="application/json",
        )
        task_id = resp.get_json()["task_id"]
        vfl_task_cleanup.append(task_id)

        resp = client.get("/vfl/tasks")
        assert resp.status_code == 200
        ids = [t["id"] for t in resp.get_json()]
        assert task_id in ids

    def test_get_nonexistent_task_returns_404(self, curator_user):
        client, _ = curator_user
        resp = client.get("/vfl/tasks/00000000-0000-0000-0000-000000000000")
        assert resp.status_code == 404


class TestPartyRegistration:
    def test_register_party_missing_fields_returns_400(self, curator_user, vfl_task_cleanup):
        client, _ = curator_user
        task_id = self._create_task(client, vfl_task_cleanup)
        resp = client.post(f"/vfl/tasks/{task_id}/parties", json={}, content_type="application/json")
        assert resp.status_code == 400
        assert "Missing fields" in resp.get_json()["error"]

    def test_register_party_success(self, curator_user, vfl_task_cleanup):
        client, _ = curator_user
        task_id = self._create_task(client, vfl_task_cleanup)
        resp = client.post(
            f"/vfl/tasks/{task_id}/parties",
            json={"site_id": "site_a", "feature_dim": 7, "feature_names": ["hr", "sbp"]},
            content_type="application/json",
        )
        assert resp.status_code == 201
        assert "party_id" in resp.get_json()

    def test_register_party_nonexistent_task_returns_404(self, curator_user):
        client, _ = curator_user
        resp = client.post(
            "/vfl/tasks/00000000-0000-0000-0000-000000000000/parties",
            json={"site_id": "site_a", "feature_dim": 7},
            content_type="application/json",
        )
        assert resp.status_code == 404

    @staticmethod
    def _create_task(client, vfl_task_cleanup, **overrides):
        payload = {"dp_epsilon": 1.0, "rounds_total": 5, "n_parties": 2}
        payload.update(overrides)
        resp = client.post("/vfl/tasks", json=payload, content_type="application/json")
        task_id = resp.get_json()["task_id"]
        vfl_task_cleanup.append(task_id)
        return task_id


class TestPSI:
    def test_submit_psi_missing_fields_returns_400(self, curator_user, vfl_task_cleanup):
        client, _ = curator_user
        task_id = TestPartyRegistration._create_task(client, vfl_task_cleanup)
        resp = client.post(f"/vfl/tasks/{task_id}/psi", json={}, content_type="application/json")
        assert resp.status_code == 400

    def test_psi_status_nonexistent_task_returns_404(self, curator_user):
        client, _ = curator_user
        resp = client.get("/vfl/tasks/00000000-0000-0000-0000-000000000000/psi/status")
        assert resp.status_code == 404

    def test_psi_aligns_after_all_parties_submit(self, curator_user, vfl_task_cleanup):
        client, _ = curator_user
        task_id = TestPartyRegistration._create_task(client, vfl_task_cleanup, n_parties=2)

        resp = client.post(
            f"/vfl/tasks/{task_id}/psi",
            json={"site_id": "site_a", "hashed_ids": ["h1", "h2", "h3"]},
            content_type="application/json",
        )
        assert resp.get_json()["psi_status"] == "partial"

        resp = client.post(
            f"/vfl/tasks/{task_id}/psi",
            json={"site_id": "site_b", "hashed_ids": ["h2", "h3", "h4"]},
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert resp.get_json()["psi_status"] == "aligned"
        assert resp.get_json()["cohort_size"] == 2

        status = client.get(f"/vfl/tasks/{task_id}/psi/status").get_json()
        assert status["psi_status"] == "aligned"
        assert status["cohort_size"] == 2


class TestEmbeddingsGate:
    def test_submit_embeddings_blocked_before_psi_returns_400(self, curator_user, vfl_task_cleanup):
        client, _ = curator_user
        task_id = TestPartyRegistration._create_task(client, vfl_task_cleanup)
        resp = client.post(
            f"/vfl/tasks/{task_id}/rounds/1/embeddings",
            json={"site_id": "site_a", "embedding": [[0.1, 0.2]]},
            content_type="application/json",
        )
        assert resp.status_code == 400
        assert "PSI not complete" in resp.get_json()["error"]


class TestRBAC:
    def test_create_task_forbidden_for_default_role(self, logged_in_user):
        client, _ = logged_in_user
        resp = client.post(
            "/vfl/tasks",
            json={"dp_epsilon": 1.0, "rounds_total": 5},
            content_type="application/json",
        )
        assert resp.status_code == 403
