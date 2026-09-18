"""
Three-layer PBPK stress test.

Layer 1 — Data integrity: params survive the JSONB round-trip exactly.
Layer 2 — Correctness: DB-routed simulation matches direct execute() output.
Layer 3 — Load: 50 concurrent runs complete without error under p95 < 10 s.
"""
import math
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest

from plugins.pbpk.studies.ratier.runner import execute, DEFAULT_PARAMS


# ── Layer 1: Data Integrity ────────────────────────────────────────────────────

class TestLayer1DataIntegrity:
    """Parameters written to DB must be fetched back bit-for-bit identical."""

    def _store_and_fetch(self, client, params, name="integrity-test"):
        resp = client.post(
            "/model/parameter-sets",
            json={"name": name, "params": params, "description": "stress test"},
            content_type="application/json",
        )
        assert resp.status_code == 201
        ps_id = resp.get_json()["id"]

        resp = client.get(f"/model/parameter-sets/{ps_id}")
        assert resp.status_code == 200
        return ps_id, resp.get_json()["params"]

    def test_full_default_params_round_trip(self, pbpk_client, pbpk_cleanup):
        client, _ = pbpk_client
        ps_ids, _ = pbpk_cleanup
        ps_id, fetched = self._store_and_fetch(client, DEFAULT_PARAMS, "full-defaults")
        ps_ids.append(ps_id)

        for key, expected in DEFAULT_PARAMS.items():
            assert key in fetched, f"Missing key: {key}"
            assert fetched[key] == pytest.approx(expected, rel=1e-9), (
                f"Value mismatch for {key}: stored {expected}, fetched {fetched[key]}"
            )

    def test_partial_params_round_trip(self, pbpk_client, pbpk_cleanup):
        client, _ = pbpk_client
        ps_ids, _ = pbpk_cleanup
        params = {"HalfLife": 7.123456789, "RateInj": 0.000123456}
        ps_id, fetched = self._store_and_fetch(client, params, "partial-params")
        ps_ids.append(ps_id)

        assert fetched["HalfLife"] == pytest.approx(7.123456789, rel=1e-9)
        assert fetched["RateInj"] == pytest.approx(0.000123456, rel=1e-9)
        assert len(fetched) == 2

    def test_unicode_name_and_description(self, pbpk_client, pbpk_cleanup):
        client, _ = pbpk_client
        ps_ids, _ = pbpk_cleanup
        resp = client.post(
            "/model/parameter-sets",
            json={
                "name": "PFAS — éléments chimiques",
                "description": "Modèle générique ≥ 1 composé",
                "params": {"HalfLife": 2.5},
            },
            content_type="application/json",
        )
        assert resp.status_code == 201
        ps_id = resp.get_json()["id"]
        ps_ids.append(ps_id)

        resp = client.get(f"/model/parameter-sets/{ps_id}")
        data = resp.get_json()
        assert data["name"] == "PFAS — éléments chimiques"
        assert data["description"] == "Modèle générique ≥ 1 composé"

    def test_empty_params_round_trip(self, pbpk_client, pbpk_cleanup):
        client, _ = pbpk_client
        ps_ids, _ = pbpk_cleanup
        ps_id, fetched = self._store_and_fetch(client, {}, "empty-params")
        ps_ids.append(ps_id)
        assert fetched == {}

    def test_extreme_float_values(self, pbpk_client, pbpk_cleanup):
        client, _ = pbpk_client
        ps_ids, _ = pbpk_cleanup
        params = {
            "HalfLife": 1e-10,
            "RateInj": 1e10,
            "PC_0": 0.0,
        }
        ps_id, fetched = self._store_and_fetch(client, params, "extreme-floats")
        ps_ids.append(ps_id)
        assert fetched["HalfLife"] == pytest.approx(1e-10, rel=1e-9)
        assert fetched["RateInj"] == pytest.approx(1e10, rel=1e-9)
        assert fetched["PC_0"] == 0.0


# ── Layer 2: Correctness ──────────────────────────────────────────────────────

class TestLayer2Correctness:
    """
    For each scenario x parameter combination: direct execute() must match
    the DB-routed POST /model/runs result to within floating-point tolerance.
    """

    PARAM_COMBOS = [
        ("pfoa_default",   {}),
        ("high_halflife",  {"HalfLife": 10.0}),
        ("low_halflife",   {"HalfLife": 0.1}),
        ("zero_intake",    {"RateInj": 0.0}),
        ("early_birth",    {"BirthYear": 1990.0}),
    ]
    SCENARIOS = ["no_bf", "bf_6mo", "bf_1yr", "bf_3yr"]

    def _run_via_db(self, client, ps_id, scenario):
        resp = client.post(
            "/model/runs",
            json={"param_set_id": ps_id, "scenario": scenario},
            content_type="application/json",
        )
        assert resp.status_code == 200, resp.get_json()
        return resp.get_json()

    @pytest.mark.parametrize("label,extra_params", PARAM_COMBOS)
    @pytest.mark.parametrize("scenario", SCENARIOS)
    def test_db_route_matches_direct_execute(
        self, scenario, label, extra_params, pbpk_client, pbpk_cleanup
    ):
        client, _ = pbpk_client
        ps_ids, run_ids = pbpk_cleanup

        merged = {**DEFAULT_PARAMS, **extra_params}
        direct = execute({**merged, "scenario": scenario})

        resp = client.post(
            "/model/parameter-sets",
            json={"name": f"correctness-{label}-{scenario}", "params": extra_params},
            content_type="application/json",
        )
        assert resp.status_code == 201
        ps_id = resp.get_json()["id"]
        ps_ids.append(ps_id)

        db_result = self._run_via_db(client, ps_id, scenario)
        run_ids.append(db_result["run_id"])

        tol = 1e-6
        for field in ("peak_C_ven", "peak_Age_yr", "final_C_ven", "final_Age_yr"):
            direct_val = direct.get(field)
            db_val = db_result.get(field)
            if direct_val is None:
                assert db_val is None, f"{field}: expected None, got {db_val}"
            else:
                assert db_val == pytest.approx(direct_val, rel=tol), (
                    f"scenario={scenario} label={label} field={field}: "
                    f"direct={direct_val}, db={db_val}"
                )

        assert db_result["n_rows"] == direct["n_rows"]


# ── Layer 3: Load ─────────────────────────────────────────────────────────────

class TestLayer3Load:
    """
    50 concurrent simulations via ThreadPoolExecutor (10 workers).
    Assertions: all runs complete as 'done', p95 latency < PBPK_STRESS_LATENCY_P95 (default 10s).
    """

    N_RUNS = 50
    N_WORKERS = 10
    SCENARIOS = ["no_bf", "bf_6mo", "bf_1yr", "bf_3yr"]

    def _make_client_with_session(self, app, email):
        client = app.test_client()
        with client.session_transaction() as sess:
            sess["user"] = email
            sess["email"] = email
        return client

    def _fire_one_run(self, app, email, ps_id, scenario):
        client = self._make_client_with_session(app, email)
        t0 = time.monotonic()
        resp = client.post(
            "/model/runs",
            json={"param_set_id": ps_id, "scenario": scenario},
            content_type="application/json",
        )
        elapsed = time.monotonic() - t0
        return resp.status_code, resp.get_json(), elapsed

    @pytest.mark.slow
    def test_50_concurrent_runs(self, app, pbpk_client, pbpk_cleanup):
        import os
        client, email = pbpk_client
        ps_ids, run_ids = pbpk_cleanup
        p95_threshold = float(os.environ.get("PBPK_STRESS_LATENCY_P95", "10"))

        resp = client.post(
            "/model/parameter-sets",
            json={"name": "load-test-params", "params": {"HalfLife": 2.5}},
            content_type="application/json",
        )
        assert resp.status_code == 201
        ps_id = resp.get_json()["id"]
        ps_ids.append(ps_id)

        # Pre-warm SBML singleton to avoid race on first initialization
        warmup = self._make_client_with_session(app, email)
        warmup.post(
            "/model/runs",
            json={"param_set_id": ps_id, "scenario": "no_bf"},
            content_type="application/json",
        )

        rng = random.Random(42)
        jobs = [
            (app, email, ps_id, rng.choice(self.SCENARIOS))
            for _ in range(self.N_RUNS)
        ]

        latencies = []
        statuses = []
        results = []

        with ThreadPoolExecutor(max_workers=self.N_WORKERS) as pool:
            futures = [pool.submit(self._fire_one_run, *job) for job in jobs]
            for fut in as_completed(futures):
                status_code, data, elapsed = fut.result()
                statuses.append(status_code)
                latencies.append(elapsed)
                results.append(data)

        failed = [r for s, r in zip(statuses, results) if s != 200]
        assert not failed, f"{len(failed)} runs failed: {failed[:3]}"

        for data in results:
            run_ids.append(data["run_id"])

        for data in results:
            assert data.get("timeseries") is not None, (
                f"run_id={data.get('run_id')} has null timeseries"
            )

        latencies.sort()
        p95_idx = int(math.ceil(0.95 * len(latencies))) - 1
        p95 = latencies[p95_idx]
        assert p95 < p95_threshold, (
            f"p95 latency {p95:.2f}s exceeds threshold {p95_threshold}s"
        )
