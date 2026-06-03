import pytest
from app import get_db


class TestPBPKHelpers:
    def test_store_and_fetch_parameter_set(self, app):
        from plugins.pbpk.helpers import store_parameter_set, fetch_parameter_set
        with app.app_context():
            db = get_db()
            params = {"HalfLife": 5.0, "RateInj": 0.3}
            ps_id = store_parameter_set("Test Chemical", "A test", params, "test@test.com")
            assert isinstance(ps_id, int)

            row = fetch_parameter_set(ps_id)
            assert row is not None
            assert row["name"] == "Test Chemical"
            assert row["description"] == "A test"
            assert row["params"]["HalfLife"] == 5.0
            assert row["params"]["RateInj"] == 0.3
            assert row["created_by"] == "test@test.com"
            assert row["model_id"] == "lifetime_pbpk"

            # Cleanup
            cur = db.cursor()
            cur.execute("DELETE FROM _fd.pbpk_parameter_sets WHERE id = %s", (ps_id,))
            db.commit()
            cur.close()

    def test_fetch_nonexistent_parameter_set_returns_none(self, app):
        from plugins.pbpk.helpers import fetch_parameter_set
        with app.app_context():
            get_db()
            assert fetch_parameter_set(999999999) is None

    def test_list_parameter_sets(self, app):
        from plugins.pbpk.helpers import store_parameter_set, list_parameter_sets
        with app.app_context():
            db = get_db()
            id1 = store_parameter_set("Chem A", "", {"HalfLife": 1.0}, "u@test.com")
            id2 = store_parameter_set("Chem B", "", {"HalfLife": 2.0}, "u@test.com")
            rows = list_parameter_sets()
            ids = [r["id"] for r in rows]
            assert id1 in ids
            assert id2 in ids
            assert all("params" not in r for r in rows)  # list omits params blob

            cur = db.cursor()
            cur.execute("DELETE FROM _fd.pbpk_parameter_sets WHERE id = ANY(%s)", ([id1, id2],))
            db.commit()
            cur.close()

    def test_create_and_fetch_run(self, app):
        from plugins.pbpk.helpers import store_parameter_set, create_run, fetch_run
        with app.app_context():
            db = get_db()
            ps_id = store_parameter_set("Run Test", "", {}, "u@test.com")
            run_id = create_run(ps_id, "no_bf", "u@test.com")
            assert isinstance(run_id, int)

            run = fetch_run(run_id)
            assert run["param_set_id"] == ps_id
            assert run["scenario"] == "no_bf"
            assert run["status"] == "pending"
            assert run["timeseries"] is None

            cur = db.cursor()
            cur.execute("DELETE FROM _fd.pbpk_simulation_runs WHERE id = %s", (run_id,))
            cur.execute("DELETE FROM _fd.pbpk_parameter_sets WHERE id = %s", (ps_id,))
            db.commit()
            cur.close()

    def test_update_run_to_done(self, app):
        from plugins.pbpk.helpers import store_parameter_set, create_run, update_run, fetch_run
        with app.app_context():
            db = get_db()
            ps_id = store_parameter_set("Update Test", "", {}, "u@test.com")
            run_id = create_run(ps_id, "no_bf", "u@test.com")

            update_run(run_id, "running")
            run = fetch_run(run_id)
            assert run["status"] == "running"
            assert run["started_at"] is not None

            summary = {"peak_C_ven": 0.05, "n_rows": 500}
            timeseries = [{"time": 0.0, "C_ven": 0.0}]
            update_run(run_id, "done", summary=summary, timeseries=timeseries)
            run = fetch_run(run_id)
            assert run["status"] == "done"
            assert run["summary"]["peak_C_ven"] == pytest.approx(0.05)
            assert run["timeseries"][0]["time"] == 0.0
            assert run["finished_at"] is not None

            cur = db.cursor()
            cur.execute("DELETE FROM _fd.pbpk_simulation_runs WHERE id = %s", (run_id,))
            cur.execute("DELETE FROM _fd.pbpk_parameter_sets WHERE id = %s", (ps_id,))
            db.commit()
            cur.close()

    def test_fetch_nonexistent_run_returns_none(self, app):
        from plugins.pbpk.helpers import fetch_run
        with app.app_context():
            get_db()
            assert fetch_run(999999999) is None


class TestEnsureSeeded:
    def test_seed_models_not_called_when_already_populated(self, app, monkeypatch):
        """ensure_seeded() must not call seed_models() when models already exist."""
        from plugins.pbpk import catalogue as cat

        # Force cold-worker state so ensure_seeded won't short-circuit on the flag.
        cat._seeded = False

        calls = []
        original = cat.seed_models

        def spy(*a, **kw):
            calls.append(1)
            return original(*a, **kw)

        monkeypatch.setattr(cat, "seed_models", spy)

        with app.app_context():
            get_db()
            cat.ensure_seeded()   # table already has rows from migrations
            assert len(calls) == 0, "seed_models() should not run when catalogue is populated"

        cat._seeded = False  # reset so other tests start clean

    def test_seed_models_called_when_empty(self, app, monkeypatch):
        """ensure_seeded() must call seed_models() when the table is empty."""
        from plugins.pbpk import catalogue as cat

        cat._seeded = False

        calls = []
        original = cat.seed_models

        def spy(*a, **kw):
            calls.append(1)
            return original(*a, **kw)

        monkeypatch.setattr(cat, "seed_models", spy)

        with app.app_context():
            db = get_db()
            # Temporarily clear the table to simulate a fresh DB.
            cur = db.cursor()
            cur.execute("DELETE FROM _fd.pbpk_models")
            db.commit()
            cur.close()

            try:
                cat.ensure_seeded()
                assert len(calls) == 1, "seed_models() must run when catalogue is empty"
            finally:
                # Restore: seed again so downstream tests see a populated catalogue.
                cat._seeded = False
                cat.seed_models()
                db.commit()

        cat._seeded = False


class TestFetchRunChecked:
    def test_returns_run_for_admin(self, app):
        """Admin can fetch any run regardless of owner."""
        from plugins.pbpk.helpers import (
            store_parameter_set, create_run, fetch_run_checked,
        )
        with app.app_context():
            db = get_db()
            ps_id = store_parameter_set("Checked Test", "", {}, "u@test.com")
            run_id = create_run(ps_id, "no_bf", "u@test.com")

            run = fetch_run_checked(run_id, user_id="some-uuid", role="admin")
            assert run is not None
            assert run["id"] == run_id
            assert "owner_id" not in run

            cur = db.cursor()
            cur.execute("DELETE FROM _fd.pbpk_simulation_runs WHERE id = %s", (run_id,))
            cur.execute("DELETE FROM _fd.pbpk_parameter_sets WHERE id = %s", (ps_id,))
            db.commit()
            cur.close()

    def test_raises_file_not_found_for_missing_run(self, app):
        from plugins.pbpk.helpers import fetch_run_checked
        with app.app_context():
            get_db()
            with pytest.raises(FileNotFoundError):
                fetch_run_checked(999999999, user_id="x", role="admin")

    def test_raises_permission_error_for_wrong_owner(self, app):
        """Non-admin user cannot read a run they do not own."""
        import uuid
        from plugins.pbpk.helpers import (
            store_parameter_set, create_run, fetch_run_checked,
        )
        with app.app_context():
            db = get_db()
            ps_id = store_parameter_set("Auth Test", "", {}, "u@test.com")
            run_id = create_run(ps_id, "no_bf", "u@test.com", owner_id=None)

            with pytest.raises(PermissionError):
                fetch_run_checked(run_id, user_id=str(uuid.uuid4()), role="curator")

            cur = db.cursor()
            cur.execute("DELETE FROM _fd.pbpk_simulation_runs WHERE id = %s", (run_id,))
            cur.execute("DELETE FROM _fd.pbpk_parameter_sets WHERE id = %s", (ps_id,))
            db.commit()
            cur.close()
