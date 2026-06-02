"""
helpers.py — thin bridge between the Flask routes and PBKFAIRModel,
plus DB helpers for persisting parameter sets and simulation runs.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

import psycopg2.extras
from flask import g

# PBKFAIRModel/ lives at the repository root (three levels up from
# backend/plugins/pbpk/). It is normally already importable via PYTHONPATH;
# this insert keeps the plugin runnable when it is not.
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from PBKFAIRModel import execute, SCENARIOS, DEFAULT_PARAMS  # noqa: E402


# ── Simulation helpers ────────────────────────────────────────────────────────

def run_scenario(user_params: dict) -> dict:
    """Validate basic inputs and delegate to runner.execute()."""
    valid_labels = {s["label"] for s in SCENARIOS}
    label = user_params.get("scenario", "no_bf")
    if label not in valid_labels:
        raise ValueError(
            f"Unknown scenario '{label}'. Valid options: {sorted(valid_labels)}"
        )
    half_life = user_params.get("HalfLife")
    if half_life is not None and float(half_life) <= 0:
        raise ValueError("HalfLife must be positive.")
    return execute(user_params)


def available_scenarios() -> list[dict]:
    """Return scenario metadata for the UI dropdown."""
    return [{"label": s["label"], "description": s["description"]} for s in SCENARIOS]


# ── DB helpers ────────────────────────────────────────────────────────────────

def store_parameter_set(
    name: str,
    description: str,
    params: dict,
    created_by: str,
    owner_id: str | None = None,
    source: str = "manual",
) -> int:
    """Insert a named parameter set and return its id."""
    cur = g.db.cursor()
    try:
        cur.execute(
            """
            INSERT INTO _fd.pbpk_parameter_sets (name, description, params, created_by, owner_id, source)
            VALUES (%s, %s, %s::jsonb, %s, %s, %s)
            RETURNING id
            """,
            (name, description, json.dumps(params), created_by, owner_id, source),
        )
        row = cur.fetchone()
        g.db.commit()
    except Exception:
        g.db.rollback()
        raise
    finally:
        cur.close()
    return row[0]


def fetch_parameter_set(param_set_id: int) -> dict | None:
    """Fetch one parameter set by id, including full params JSONB."""
    cur = g.db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        """
        SELECT id, name, description, model_id, params, created_by, created_at
        FROM _fd.pbpk_parameter_sets
        WHERE id = %s
        """,
        (param_set_id,),
    )
    row = cur.fetchone()
    cur.close()
    if row is None:
        return None
    result = dict(row)
    if isinstance(result["params"], str):
        result["params"] = json.loads(result["params"])
    result["created_at"] = result["created_at"].isoformat()
    return result


def list_parameter_sets(limit: int = 200) -> list[dict]:
    """Return parameter sets ordered by creation date, newest first."""
    cur = g.db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        """
        SELECT id, name, description, model_id, created_by, created_at
        FROM _fd.pbpk_parameter_sets
        ORDER BY created_at DESC
        LIMIT %s
        """,
        (limit,),
    )
    rows = cur.fetchall()
    cur.close()
    result = []
    for row in rows:
        r = dict(row)
        r["created_at"] = r["created_at"].isoformat()
        result.append(r)
    return result


def create_run(
    param_set_id: int,
    scenario: str,
    created_by: str,
    owner_id: str | None = None,
) -> int:
    """Insert a new simulation run with status='pending' and return its id."""
    cur = g.db.cursor()
    try:
        cur.execute(
            """
            INSERT INTO _fd.pbpk_simulation_runs
                (param_set_id, scenario, status, created_by, owner_id)
            VALUES (%s, %s, 'pending', %s, %s)
            RETURNING id
            """,
            (param_set_id, scenario, created_by, owner_id),
        )
        row = cur.fetchone()
        g.db.commit()
    except Exception:
        g.db.rollback()
        raise
    finally:
        cur.close()
    return row[0]


def update_run(
    run_id: int,
    status: str,
    summary: dict | None = None,
    timeseries: list | None = None,
    error_message: str | None = None,
) -> None:
    """Update run status, timestamps, and optionally results or error."""
    if not status:
        raise ValueError("status must be a non-empty string")
    now = datetime.now(timezone.utc)
    parts = ["status = %s"]
    values: list = [status]

    if status == "running":
        parts.append("started_at = %s")
        values.append(now)
    if status in ("done", "error"):
        parts.append("finished_at = %s")
        values.append(now)
    if summary is not None:
        parts.append("summary = %s::jsonb")
        values.append(json.dumps(summary))
    if timeseries is not None:
        parts.append("timeseries = %s::jsonb")
        values.append(json.dumps(timeseries))
    if error_message is not None:
        parts.append("error_message = %s")
        values.append(error_message)

    values.append(run_id)
    cur = g.db.cursor()
    try:
        cur.execute(
            f"UPDATE _fd.pbpk_simulation_runs SET {', '.join(parts)} WHERE id = %s",
            values,
        )
        g.db.commit()
    except Exception:
        g.db.rollback()
        raise
    finally:
        cur.close()


def fetch_run(run_id: int) -> dict | None:
    """Fetch one simulation run by id."""
    cur = g.db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        """
        SELECT id, param_set_id, scenario, status, started_at, finished_at,
               error_message, summary, timeseries, created_by, created_at
        FROM _fd.pbpk_simulation_runs
        WHERE id = %s
        """,
        (run_id,),
    )
    row = cur.fetchone()
    cur.close()
    if row is None:
        return None
    result = dict(row)
    for field in ("summary", "timeseries"):
        if isinstance(result.get(field), str):
            result[field] = json.loads(result[field])
    for field in ("started_at", "finished_at", "created_at"):
        if result.get(field) is not None:
            result[field] = result[field].isoformat()
    return result


def fetch_run_provenance(run_id: int) -> dict | None:
    """Return a W3C PROV-JSON document for run_id, or None if not found."""
    cur = g.db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute(
            """
            SELECT r.id, r.param_set_id, r.study_slug, r.scenario,
                   r.compound, r.engine, r.created_at, r.user_id,
                   ps.name AS param_set_name
            FROM _fd.pbpk_simulation_runs r
            LEFT JOIN _fd.pbpk_parameter_sets ps ON ps.id = r.param_set_id
            WHERE r.id = %s
            """,
            (run_id,),
        )
        row = cur.fetchone()
    finally:
        cur.close()

    if row is None:
        return None

    run_uri = f"fairdatabase:pbpk/runs/{row['id']}"
    ps_uri = (
        f"fairdatabase:pbpk/parameter-sets/{row['param_set_id']}"
        if row["param_set_id"]
        else None
    )
    user_uri = (
        f"fairdatabase:users/{row['user_id']}"
        if row["user_id"]
        else "fairdatabase:users/anonymous"
    )
    ts = row["created_at"].isoformat() if row["created_at"] else None

    doc: dict = {
        "prefix": {
            "fairdatabase": "https://github.com/SheratonMV/FAIRDatabase/",
            "prov": "http://www.w3.org/ns/prov#",
            "xsd": "http://www.w3.org/2001/XMLSchema#",
        },
        "entity": {
            run_uri: {
                "prov:type": "prov:Entity",
                "fairdatabase:run_id": row["id"],
                "fairdatabase:study_slug": row["study_slug"],
                "fairdatabase:scenario": row["scenario"],
                "fairdatabase:compound": row["compound"],
                "fairdatabase:engine": row["engine"],
            },
        },
        "activity": {
            f"fairdatabase:pbpk/simulation-events/{row['id']}": {
                k: v
                for k, v in {
                    "prov:type": "prov:Activity",
                    "prov:startedAtTime": (
                        {"$": ts, "type": "xsd:dateTime"} if ts else None
                    ),
                    "prov:endedAtTime": (
                        {"$": ts, "type": "xsd:dateTime"} if ts else None
                    ),
                }.items()
                if v is not None
            },
        },
        "agent": {
            user_uri: {
                "prov:type": "prov:Agent",
                "fairdatabase:user_id": (
                    str(row["user_id"]) if row["user_id"] else None
                ),
            },
        },
        "wasGeneratedBy": {
            f"_:wgb{row['id']}": {
                "prov:entity": run_uri,
                "prov:activity": f"fairdatabase:pbpk/simulation-events/{row['id']}",
            },
        },
        "wasAttributedTo": {
            f"_:wat{row['id']}": {
                "prov:entity": run_uri,
                "prov:agent": user_uri,
            },
        },
    }

    if ps_uri:
        doc["entity"][ps_uri] = {
            "prov:type": "prov:Entity",
            "fairdatabase:param_set_id": row["param_set_id"],
            "fairdatabase:param_set_name": row["param_set_name"],
        }
        doc["wasDerivedFrom"] = {
            f"_:wdf{row['id']}": {
                "prov:generatedEntity": run_uri,
                "prov:usedEntity": ps_uri,
            },
        }

    return doc


# ── RBAC: handler-level checks (load-bearing on the Flask path) ───────────────
#
# RLS on _fd.pbpk_* exists in pbpk_schema.sql but does NOT fire here because
# the Flask connection runs as a Postgres superuser. These helpers enforce
# ownership the same way dashboard.helpers.assert_can_*_table does for CSVs.

def _fetch_run_owner(cur, run_id: int) -> str | None:
    cur.execute(
        "SELECT owner_id FROM _fd.pbpk_simulation_runs WHERE id = %s",
        (run_id,),
    )
    row = cur.fetchone()
    return None if row is None else row[0]


def assert_can_read_run(cur, run_id: int, user_id: str, role: str) -> None:
    """Raise PermissionError unless the caller may read this run + its artifacts."""
    if role == "admin":
        if _fetch_run_owner(cur, run_id) is None:
            raise FileNotFoundError("run not found")
        return
    if not user_id or role not in ("curator", "accessor"):
        raise PermissionError("forbidden")
    owner = _fetch_run_owner(cur, run_id)
    if owner is None:
        raise FileNotFoundError("run not found")
    if str(owner) != str(user_id):
        raise PermissionError("forbidden")


def assert_can_modify_run(cur, run_id: int, user_id: str, role: str) -> None:
    """Raise PermissionError unless the caller may attach/delete artifacts."""
    if role == "admin":
        if _fetch_run_owner(cur, run_id) is None:
            raise FileNotFoundError("run not found")
        return
    if role != "curator" or not user_id:
        raise PermissionError("forbidden")
    owner = _fetch_run_owner(cur, run_id)
    if owner is None:
        raise FileNotFoundError("run not found")
    if str(owner) != str(user_id):
        raise PermissionError("forbidden")


# ── Artifact catalog helpers ──────────────────────────────────────────────────

def insert_artifact(
    run_id: int,
    owner_id: str,
    kind: str,
    storage_path: str,
    mime: str,
    size_bytes: int,
    original_name: str,
) -> int:
    cur = g.db.cursor()
    try:
        cur.execute(
            """
            INSERT INTO _fd.pbpk_run_artifacts
                (run_id, owner_id, kind, storage_path, mime, size_bytes, original_name)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (run_id, owner_id, kind, storage_path, mime, size_bytes, original_name),
        )
        new_id = cur.fetchone()[0]
        g.db.commit()
    except Exception:
        g.db.rollback()
        raise
    finally:
        cur.close()
    return new_id


def list_artifacts(run_id: int) -> list[dict]:
    cur = g.db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        """
        SELECT id, run_id, owner_id, kind, storage_path, mime, size_bytes,
               original_name, created_at
        FROM _fd.pbpk_run_artifacts
        WHERE run_id = %s
        ORDER BY created_at DESC
        """,
        (run_id,),
    )
    rows = cur.fetchall()
    cur.close()
    out = []
    for row in rows:
        r = dict(row)
        r["owner_id"] = str(r["owner_id"]) if r["owner_id"] is not None else None
        r["created_at"] = r["created_at"].isoformat()
        out.append(r)
    return out


def fetch_artifact(artifact_id: int) -> dict | None:
    cur = g.db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        """
        SELECT id, run_id, owner_id, kind, storage_path, mime, size_bytes,
               original_name, created_at
        FROM _fd.pbpk_run_artifacts
        WHERE id = %s
        """,
        (artifact_id,),
    )
    row = cur.fetchone()
    cur.close()
    if row is None:
        return None
    r = dict(row)
    r["owner_id"] = str(r["owner_id"]) if r["owner_id"] is not None else None
    r["created_at"] = r["created_at"].isoformat()
    return r


def delete_artifact_row(artifact_id: int) -> None:
    cur = g.db.cursor()
    try:
        cur.execute(
            "DELETE FROM _fd.pbpk_run_artifacts WHERE id = %s",
            (artifact_id,),
        )
        g.db.commit()
    except Exception:
        g.db.rollback()
        raise
    finally:
        cur.close()
