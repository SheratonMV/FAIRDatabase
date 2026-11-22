"""Simulations started at the same time must not disturb each other.

scipy's LSODA keeps its working state in process-wide Fortran memory, so two
solves running at once in different threads (the Flask server is threaded)
used to fail with IntegratorConcurrencyError, crash the process, or return
wrong numbers without any error. These tests need no database.
"""
import json
import os
import subprocess
import sys
import textwrap
import threading
import time
from pathlib import Path

import pytest

pytest.importorskip("libsbml")
pytest.importorskip("scipy")

BACKEND = Path(__file__).resolve().parents[3]


def test_solves_never_overlap(monkeypatch):
    from plugins.pbpk.studies import solver

    active = 0
    most_at_once = 0
    count_lock = threading.Lock()

    def slow_fake_solve(*args, **kwargs):
        nonlocal active, most_at_once
        with count_lock:
            active += 1
            most_at_once = max(most_at_once, active)
        time.sleep(0.02)
        with count_lock:
            active -= 1
        return "solved"

    monkeypatch.setattr(solver, "_scipy_solve_ivp", slow_fake_solve)
    threads = [threading.Thread(target=solver.solve_ivp, args=(None, (0, 1), [0]))
               for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert most_at_once == 1


def test_every_study_runner_uses_the_shared_solver():
    from plugins.pbpk import studies
    from plugins.pbpk.studies import solver

    for slug in studies.STUDIES:
        runner = studies.load(slug)
        assert runner.solve_ivp is solver.solve_ivp, (
            f"{slug} calls scipy's solve_ivp directly; import it from "
            "plugins.pbpk.studies.solver so its solves take turns"
        )


# Runs in a child process: before the fix this crashed the interpreter, which
# would otherwise take the whole pytest run down with it.
_PARALLEL_RUNS = textwrap.dedent("""
    import json, warnings
    from concurrent.futures import ThreadPoolExecutor
    warnings.simplefilter("ignore")
    from plugins.pbpk import studies

    jobs = [("ratier", {"scenario": "no_bf"}), ("ratier", {"scenario": "bf_1yr"}),
            ("rovira", {}), ("rovira", {"compound": "PFOS"})]
    runners = {slug: studies.load(slug) for slug, _ in jobs}

    def numbers(result):
        return {k: v for k, v in result.items() if isinstance(v, (int, float))}

    expected = [numbers(runners[slug].execute(dict(p))) for slug, p in jobs]

    def run(i):
        slug, payload = jobs[i % len(jobs)]
        try:
            got = numbers(runners[slug].execute(dict(payload)))
        except Exception as exc:
            return f"{slug}: {type(exc).__name__}: {exc}"
        return "same" if got == expected[i % len(jobs)] else f"{slug}: different numbers"

    with ThreadPoolExecutor(4) as pool:
        print(json.dumps(list(pool.map(run, range(8)))))
""")


def test_parallel_runs_match_one_at_a_time_runs():
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([str(BACKEND), str(BACKEND.parent)]))
    proc = subprocess.run(
        [sys.executable, "-c", _PARALLEL_RUNS],
        cwd=BACKEND, env=env, capture_output=True, text=True, timeout=300,
    )
    assert proc.returncode == 0, f"child process died ({proc.returncode}):\n{proc.stderr[-2000:]}"
    outcomes = json.loads(proc.stdout.strip().splitlines()[-1])
    assert outcomes == ["same"] * 8, outcomes
