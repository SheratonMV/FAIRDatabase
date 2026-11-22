import hashlib
import json

import pytest


class TestStudyRunIdempotency:
    """Content-hash idempotency caching for bundled study runs."""

    def test_content_hash_computed(self, curator_user, app):
        """study_run returns run_id for /model/studies/ratier/run."""
        client, _ = curator_user
        payload = {"scenario": "no_bf", "HalfLife": 3.5, "RateInj": 0.451695, "BirthYear": 2007}
        resp = client.post(
            "/model/studies/ratier/run",
            json=payload,
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert "run_id" in data
        assert isinstance(data["run_id"], int)

        with app.app_context():
            from app import get_db
            db = get_db()
            cur = db.cursor()
            cur.execute("DELETE FROM _fd.pbpk_simulation_runs WHERE id = %s", (data["run_id"],))
            db.commit()
            cur.close()

    def test_cache_hit_on_duplicate_payload(self, curator_user, app):
        """Submitting the same payload twice returns cache_hit=True on second call."""
        client, _ = curator_user
        payload = {"scenario": "no_bf", "HalfLife": 3.5, "RateInj": 0.451695, "BirthYear": 2007}
        resp1 = client.post(
            "/model/studies/ratier/run",
            json=payload,
            content_type="application/json",
        )
        resp2 = client.post(
            "/model/studies/ratier/run",
            json=payload,
            content_type="application/json",
        )
        assert resp1.status_code == 200
        assert resp2.status_code == 200
        data1 = resp1.get_json()
        data2 = resp2.get_json()
        assert data2.get("cache_hit") is True
        # Cache hit should return the same run
        assert data2.get("run_id") == data1.get("run_id")

        with app.app_context():
            from app import get_db
            db = get_db()
            cur = db.cursor()
            cur.execute(
                "DELETE FROM _fd.pbpk_simulation_runs WHERE id = %s",
                (data1["run_id"],),
            )
            db.commit()
            cur.close()


class TestSimulationRunRoutes:
    def test_create_run_returns_200_with_results(self, curator_user, app):
        client, _ = curator_user
        ps_resp = client.post(
            "/model/parameter-sets",
            json={"name": "Run Route Test", "params": {"HalfLife": 2.5}},
            content_type="application/json",
        )
        ps_id = ps_resp.get_json()["id"]

        run_resp = client.post(
            "/model/runs",
            json={"param_set_id": ps_id, "scenario": "no_bf"},
            content_type="application/json",
        )
        assert run_resp.status_code == 200
        data = run_resp.get_json()
        assert "run_id" in data
        assert data["scenario"] == "no_bf"
        assert isinstance(data["peak_C_ven"], float)
        assert isinstance(data["timeseries"], list)
        assert len(data["timeseries"]) > 0

        with app.app_context():
            from app import get_db
            db = get_db()
            cur = db.cursor()
            cur.execute("DELETE FROM _fd.pbpk_simulation_runs WHERE id = %s", (data["run_id"],))
            cur.execute("DELETE FROM _fd.pbpk_parameter_sets WHERE id = %s", (ps_id,))
            db.commit()
            cur.close()

    def test_create_run_missing_param_set_id_returns_400(self, curator_user):
        client, _ = curator_user
        resp = client.post(
            "/model/runs",
            json={"scenario": "no_bf"},
            content_type="application/json",
        )
        assert resp.status_code == 400
        assert "param_set_id" in resp.get_json()["error"]

    def test_create_run_nonexistent_param_set_returns_404(self, curator_user):
        client, _ = curator_user
        resp = client.post(
            "/model/runs",
            json={"param_set_id": 999999999, "scenario": "no_bf"},
            content_type="application/json",
        )
        assert resp.status_code == 404

    def test_create_run_persists_status_done(self, curator_user, app):
        client, _ = curator_user
        ps_resp = client.post(
            "/model/parameter-sets",
            json={"name": "Persist Test", "params": {}},
            content_type="application/json",
        )
        ps_id = ps_resp.get_json()["id"]

        run_resp = client.post(
            "/model/runs",
            json={"param_set_id": ps_id, "scenario": "no_bf"},
            content_type="application/json",
        )
        run_id = run_resp.get_json()["run_id"]

        fetch_resp = client.get(f"/model/runs/{run_id}")
        assert fetch_resp.status_code == 200
        run = fetch_resp.get_json()
        assert run["status"] == "done"
        assert run["summary"] is not None
        assert run["timeseries"] is not None
        assert run["finished_at"] is not None

        with app.app_context():
            from app import get_db
            db = get_db()
            cur = db.cursor()
            cur.execute("DELETE FROM _fd.pbpk_simulation_runs WHERE id = %s", (run_id,))
            cur.execute("DELETE FROM _fd.pbpk_parameter_sets WHERE id = %s", (ps_id,))
            db.commit()
            cur.close()

    def test_get_nonexistent_run_returns_404(self, curator_user):
        client, _ = curator_user
        resp = client.get("/model/runs/999999999")
        assert resp.status_code == 404

    def test_study_run_status_is_done_not_running(self, curator_user, app):
        """Study run should go pending → done without a visible 'running' state.

        Removing the intermediate update_run('running') call means the run is
        never observable as 'running' — it goes directly to 'done' or 'error'.
        started_at must still be set (via COALESCE in update_run).
        """
        client, _ = curator_user
        payload = {"scenario": "no_bf", "HalfLife": 3.5, "RateInj": 0.451695, "BirthYear": 2007}
        resp = client.post(
            "/model/studies/ratier/run",
            json=payload,
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        run_id = data["run_id"]

        with app.app_context():
            from app import get_db
            from plugins.pbpk.helpers import fetch_run
            get_db()
            run = fetch_run(run_id)
            assert run["status"] == "done"
            assert run["started_at"] is not None, "started_at must be set via COALESCE"
            assert run["finished_at"] is not None

            db = get_db()
            cur = db.cursor()
            cur.execute("DELETE FROM _fd.pbpk_simulation_runs WHERE id = %s", (run_id,))
            db.commit()
            cur.close()

    def test_invalid_scenario_sets_run_status_error(self, curator_user, app):
        client, _ = curator_user
        ps_resp = client.post(
            "/model/parameter-sets",
            json={"name": "Error Test", "params": {}},
            content_type="application/json",
        )
        ps_id = ps_resp.get_json()["id"]

        run_resp = client.post(
            "/model/runs",
            json={"param_set_id": ps_id, "scenario": "invalid_scenario"},
            content_type="application/json",
        )
        assert run_resp.status_code == 400
        data = run_resp.get_json()
        assert "run_id" in data

        fetch_resp = client.get(f"/model/runs/{data['run_id']}")
        assert fetch_resp.get_json()["status"] == "error"
        assert fetch_resp.get_json()["error_message"] is not None

        with app.app_context():
            from app import get_db
            db = get_db()
            cur = db.cursor()
            cur.execute("DELETE FROM _fd.pbpk_simulation_runs WHERE id = %s", (data["run_id"],))
            cur.execute("DELETE FROM _fd.pbpk_parameter_sets WHERE id = %s", (ps_id,))
            db.commit()
            cur.close()


def _delete_runs(app, *run_ids):
    with app.app_context():
        from app import get_db
        db = get_db()
        cur = db.cursor()
        cur.execute(
            "DELETE FROM _fd.pbpk_simulation_runs WHERE id = ANY(%s)",
            ([r for r in run_ids if r is not None],),
        )
        db.commit()
        cur.close()


class TestCachedRunMatchesFreshRun:
    """A cache hit must give the study page the same numbers as a fresh run."""

    @pytest.mark.parametrize(
        "slug, payload, keys",
        [
            (
                "ratier",
                {"scenario": "no_bf", "HalfLife": 3.1, "RateInj": 0.451695, "BirthYear": 2007},
                ("peak_C_ven", "peak_Age_yr", "final_C_ven", "final_Age_yr"),
            ),
            (
                "generic",
                {"compound": "PFOA", "scenario": "no_bf", "n_pts": 50},
                ("peak_CA_maternal_mgL", "peak_age_yr", "peak_CA_fetal_mgL",
                 "final_CA_maternal_mgL", "final_age_yr"),
            ),
        ],
    )
    def test_cache_hit_returns_the_same_results(self, curator_user, app, slug, payload, keys):
        client, _ = curator_user
        url = f"/model/studies/{slug}/run"
        fresh = client.post(url, json=payload).get_json()
        cached = client.post(url, json=payload).get_json()
        try:
            assert cached.get("cache_hit") is True
            for key in keys:
                assert fresh.get(key) is not None, f"fresh run has no {key}"
                assert cached.get(key) == pytest.approx(fresh[key]), key
            assert len(cached["timeseries"]) == len(fresh["timeseries"])
        finally:
            _delete_runs(app, fresh.get("run_id"))


class TestStudyRunAccess:
    def test_visualizer_cannot_run_a_study(self, logged_in_user, app):
        """Visualizers cannot open results, so they must not be able to start a run."""
        client, _ = logged_in_user
        resp = client.post(
            "/model/studies/ratier/run",
            json={"scenario": "no_bf", "HalfLife": 3.2, "RateInj": 0.451695, "BirthYear": 2007},
        )
        assert resp.status_code == 403


class TestResultsPage:
    def test_results_page_names_the_model_used(self, curator_user, app):
        client, _ = curator_user
        run = client.post(
            "/model/studies/ratier/run",
            json={"scenario": "no_bf", "HalfLife": 3.3, "RateInj": 0.451695, "BirthYear": 2007},
        ).get_json()
        try:
            resp = client.get(f"/model/results/{run['run_id']}")
            assert resp.status_code == 200
            assert b"This simulation used the" in resp.data
        finally:
            _delete_runs(app, run.get("run_id"))
