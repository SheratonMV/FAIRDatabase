"""
db.py — PostgreSQL CRUD for the vertical FL plugin (_fd.vfl_* tables).

All functions accept a psycopg2 connection and operate within the caller's
transaction. The caller is responsible for commit/rollback.
"""
from __future__ import annotations

import json
import uuid
from typing import Optional


def create_task(conn, *, n_parties: int, n_tasks: int, task_types: list,
                task_sigma: dict, dp_epsilon: float, dp_delta: float,
                dp_clip_norm: float, rounds_total: int, simulation: bool,
                sim_n_clients: int, sim_alpha: float, model_arch: dict,
                created_by: Optional[str], dataset_id: Optional[str] = None) -> str:
    task_id = str(uuid.uuid4())
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO _fd.vfl_tasks
                (id, n_parties, n_tasks, task_types, task_sigma,
                 dp_epsilon, dp_delta, dp_clip_norm, rounds_total,
                 simulation, sim_n_clients, sim_alpha,
                 model_arch, created_by, dataset_id)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (task_id, n_parties, n_tasks,
             json.dumps(task_types), json.dumps(task_sigma),
             dp_epsilon, dp_delta, dp_clip_norm, rounds_total,
             simulation, sim_n_clients, sim_alpha,
             json.dumps(model_arch), created_by, dataset_id),
        )
    conn.commit()
    return task_id


def get_task(conn, task_id: str) -> Optional[dict]:
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM _fd.vfl_tasks WHERE id = %s", (task_id,))
        row = cur.fetchone()
        if row is None:
            return None
        cols = [d[0] for d in cur.description]
        return dict(zip(cols, row))


def list_tasks(conn, *, user_id: str, is_admin: bool) -> list[dict]:
    with conn.cursor() as cur:
        if is_admin:
            cur.execute(
                "SELECT id, status, psi_status, n_parties, n_tasks, "
                "rounds_total, rounds_done, dp_epsilon, simulation, created_at "
                "FROM _fd.vfl_tasks ORDER BY created_at DESC LIMIT 50"
            )
        else:
            cur.execute(
                "SELECT id, status, psi_status, n_parties, n_tasks, "
                "rounds_total, rounds_done, dp_epsilon, simulation, created_at "
                "FROM _fd.vfl_tasks WHERE created_by = %s "
                "ORDER BY created_at DESC LIMIT 50",
                (user_id,),
            )
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


def set_task_status(conn, task_id: str, status: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE _fd.vfl_tasks SET status = %s WHERE id = %s",
            (status, task_id),
        )
    conn.commit()


def advance_task_round(conn, task_id: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE _fd.vfl_tasks SET rounds_done = rounds_done + 1 WHERE id = %s",
            (task_id,),
        )
    conn.commit()


# ── Parties ────────────────────────────────────────────────────────────────────

def register_party(conn, *, task_id: str, site_id: str,
                   feature_dim: int, feature_names: list) -> str:
    party_id = str(uuid.uuid4())
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO _fd.vfl_parties (id, task_id, site_id, feature_dim, feature_names)
            VALUES (%s,%s,%s,%s,%s)
            ON CONFLICT (task_id, site_id) DO UPDATE
                SET feature_dim = EXCLUDED.feature_dim,
                    feature_names = EXCLUDED.feature_names
            RETURNING id
            """,
            (party_id, task_id, site_id, feature_dim, json.dumps(feature_names)),
        )
        party_id = str(cur.fetchone()[0])
    conn.commit()
    return party_id


def list_parties(conn, task_id: str) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT * FROM _fd.vfl_parties WHERE task_id = %s ORDER BY registered_at",
            (task_id,),
        )
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


# ── PSI ────────────────────────────────────────────────────────────────────────

def submit_psi(conn, *, task_id: str, site_id: str,
               hashed_ids: list, n_parties: int) -> Optional[int]:
    """Store hashed IDs for one party. Returns cohort size if all parties have
    now submitted (intersection computed), otherwise None."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO _fd.vfl_psi (task_id, site_id, hashed_ids)
            VALUES (%s, %s, %s)
            ON CONFLICT (task_id, site_id) DO UPDATE SET hashed_ids = EXCLUDED.hashed_ids
            """,
            (task_id, site_id, json.dumps(hashed_ids)),
        )
        cur.execute(
            "SELECT COUNT(*) FROM _fd.vfl_psi WHERE task_id = %s", (task_id,)
        )
        submitted = int(cur.fetchone()[0])

    if submitted < n_parties:
        conn.commit()
        return None

    # All parties have submitted — delegate intersection to engine (pure function).
    from .engine import psi_intersect
    with conn.cursor() as cur:
        cur.execute(
            "SELECT hashed_ids FROM _fd.vfl_psi WHERE task_id = %s", (task_id,)
        )
        id_sets = [list(row[0]) for row in cur.fetchall()]

    cohort_size = len(psi_intersect(id_sets))

    with conn.cursor() as cur:
        cur.execute(
            "UPDATE _fd.vfl_tasks SET psi_status = 'aligned', psi_cohort_size = %s "
            "WHERE id = %s",
            (cohort_size, task_id),
        )
    conn.commit()
    return cohort_size


# ── Rounds ─────────────────────────────────────────────────────────────────────

def create_round(conn, task_id: str, round_n: int) -> str:
    round_id = str(uuid.uuid4())
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO _fd.vfl_rounds (id, task_id, round_n) VALUES (%s,%s,%s)",
            (round_id, task_id, round_n),
        )
    conn.commit()
    return round_id


def get_round(conn, task_id: str, round_n: int) -> Optional[dict]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT * FROM _fd.vfl_rounds WHERE task_id=%s AND round_n=%s",
            (task_id, round_n),
        )
        row = cur.fetchone()
        if row is None:
            return None
        cols = [d[0] for d in cur.description]
        return dict(zip(cols, row))


def list_rounds(conn, task_id: str) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT * FROM _fd.vfl_rounds WHERE task_id=%s ORDER BY round_n",
            (task_id,),
        )
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


def store_embeddings(conn, task_id: str, round_n: int,
                     site_id: str, embedding: list) -> int:
    """Accumulate one party's embedding into the round; returns total received."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT embeddings, embeddings_received FROM _fd.vfl_rounds "
            "WHERE task_id=%s AND round_n=%s",
            (task_id, round_n),
        )
        row = cur.fetchone()
        existing = row[0] or {}
        existing[site_id] = embedding
        new_count = int(row[1]) + 1
        cur.execute(
            "UPDATE _fd.vfl_rounds SET embeddings=%s, embeddings_received=%s "
            "WHERE task_id=%s AND round_n=%s",
            (json.dumps(existing), new_count, task_id, round_n),
        )
    conn.commit()
    return new_count


def store_top_weights(conn, task_id: str, round_n: int,
                      top_weights: list, loss_per_task: dict,
                      epsilon_per_task: dict) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE _fd.vfl_rounds
            SET top_model_weights=%s, loss_per_task=%s,
                epsilon_per_task=%s, status='done'
            WHERE task_id=%s AND round_n=%s
            """,
            (json.dumps(top_weights), json.dumps(loss_per_task),
             json.dumps(epsilon_per_task), task_id, round_n),
        )
    conn.commit()


def store_gradients(conn, task_id: str, round_n: int, gradients: dict) -> None:
    """Store per-party gradient slices for a completed round, keyed by site_id."""
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE _fd.vfl_rounds SET gradients=%s WHERE task_id=%s AND round_n=%s",
            (json.dumps(gradients), task_id, round_n),
        )
    conn.commit()


def consume_gradient(conn, task_id: str, round_n: int, site_id: str) -> Optional[list]:
    """Return one party's gradient slice and remove it (single-fetch)."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT gradients FROM _fd.vfl_rounds WHERE task_id=%s AND round_n=%s",
            (task_id, round_n),
        )
        row = cur.fetchone()
        gradients = (row[0] if row else None) or {}
        grad = gradients.pop(site_id, None)
        if grad is None:
            return None
        cur.execute(
            "UPDATE _fd.vfl_rounds SET gradients=%s WHERE task_id=%s AND round_n=%s",
            (json.dumps(gradients), task_id, round_n),
        )
    conn.commit()
    return grad


def purge_round_embeddings(conn, task_id: str, round_n: int) -> None:
    """Remove raw embeddings after gradients have been dispatched."""
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE _fd.vfl_rounds SET embeddings = NULL "
            "WHERE task_id=%s AND round_n=%s",
            (task_id, round_n),
        )
    conn.commit()


def get_latest_top_weights(conn, task_id: str) -> Optional[list]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT top_model_weights FROM _fd.vfl_rounds "
            "WHERE task_id=%s AND status='done' ORDER BY round_n DESC LIMIT 1",
            (task_id,),
        )
        row = cur.fetchone()
        return row[0] if row else None
