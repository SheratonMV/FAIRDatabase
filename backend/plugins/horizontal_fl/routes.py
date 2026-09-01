"""
routes.py — horizontal federated-learning plugin blueprint.

Mounted by the plugin loader at url_prefix="/fl" (declared in plugin.py).

/fl/ui                                GET  — FL dashboard UI (login required)
/fl/tasks                             POST — create FL task / GET — list tasks
/fl/tasks/<id>                        GET  — task status
/fl/tasks/<id>/cancel                 POST — cancel a task
/fl/tasks/<id>/rounds                 GET  — list rounds
/fl/tasks/<id>/rounds/<n>/gradients   POST — submit encrypted client update
/fl/tasks/<id>/model                  GET  — latest aggregated weights
/fl/tasks/<id>/simulate               POST — run all rounds in-process (sim)
/fl/tasks/<id>/export                 GET  — export task config + round log
/fl/tasks/<id>/export-params          POST — export weights as PBPK param set

Migrated from src/federated/ (migration plan Phase 5). All imports are from
``kernel.*`` or this plugin; the PBPK hand-off goes over HTTP (guide §3).
"""
import csv
import io
import json
import logging

import numpy as np
import requests
from flask import (
    Blueprint, Response, current_app, g, jsonify, render_template, request,
    session,
)

from kernel import dp_budget
from kernel.auth import login_required
from kernel.crypto import decrypt_weights
from kernel.privacy import (
    add_gaussian_noise_dp,
    clip_gradients,
    compute_epsilon_spent,
    compute_noise_multiplier,
)

from . import db as fl_db

routes = Blueprint("horizontal_fl_routes", __name__)
_log = logging.getLogger(__name__)


def _load_task_authorized(task_id):
    """Fetch a task and enforce per-task ownership.

    Admins access any task; every other role may only access tasks they
    created. There is no cross-user grant table for FL, so a non-owner
    non-admin is rejected.

    Returns ``(task, None)`` on success or ``(None, error_response)`` where
    ``error_response`` is a ready-to-return Flask ``(body, status)`` tuple.
    """
    task = fl_db.get_task(g.db, task_id)
    if task is None:
        return None, (jsonify({"error": "Task not found"}), 404)
    owner = task.get("created_by")
    if g.role != "admin" and (owner is None or str(owner) != str(g.user)):
        return None, (jsonify({"error": "Forbidden"}), 403)
    return task, None


# ── UI ─────────────────────────────────────────────────────────────────────────

@routes.route("/ui", methods=["GET"])
@login_required()
def federated_ui():
    tasks = []
    try:
        with g.db.cursor() as cur:
            cur.execute(
                "SELECT id, status, rounds_total, rounds_done, algorithm, "
                "dp_epsilon, simulation FROM _fd.fl_tasks "
                "ORDER BY created_at DESC LIMIT 20"
            )
            cols = [d[0] for d in cur.description]
            tasks = [dict(zip(cols, r)) for r in cur.fetchall()]
    except Exception:
        g.db.rollback()
    return render_template(
        "horizontal_fl/federated_learning.html",
        tasks=tasks,
        user_email=session.get("email"),
        current_path=request.path,
        vfl_available="vertical_fl_routes" in current_app.blueprints,
    )


# ── Task endpoints ─────────────────────────────────────────────────────────────

@routes.route("/tasks", methods=["POST"])
@login_required("admin", "curator")
def create_task():
    payload = request.get_json(silent=True) or {}
    required = {"dp_epsilon", "rounds_total"}
    missing = required - set(payload)
    if missing:
        return jsonify({"error": f"Missing fields: {sorted(missing)}"}), 400

    dp_epsilon = float(payload["dp_epsilon"])
    dp_delta = float(payload.get("dp_delta", 1e-5))
    rounds_total = int(payload["rounds_total"])

    # Whitelist the algorithm: it is persisted and later rendered in the FL
    # dashboard. Rejecting unknown values here keeps untrusted strings out of
    # the task table (defense against stored XSS / bad engine dispatch).
    algorithm = payload.get("algorithm", "fedprox")
    allowed_algorithms = {"fedprox", "fedavg"}
    if algorithm not in allowed_algorithms:
        return (
            jsonify(
                {"error": f"Invalid algorithm; allowed: {sorted(allowed_algorithms)}"}
            ),
            400,
        )

    noise_mult = compute_noise_multiplier(
        epsilon=dp_epsilon, delta=dp_delta, rounds=rounds_total
    )

    task_id = fl_db.create_task(
        g.db,
        algorithm=algorithm,
        rounds_total=rounds_total,
        mu=float(payload.get("mu", 0.01)),
        dp_epsilon=dp_epsilon,
        dp_delta=dp_delta,
        dp_noise_mult=noise_mult,
        dp_clip_norm=float(payload.get("dp_clip_norm", 1.0)),
        simulation=bool(payload.get("simulation", False)),
        sim_alpha=float(payload.get("sim_alpha", 0.5)),
        sim_n_clients=int(payload.get("sim_n_clients", 5)),
        model_arch=payload.get("model_arch", {}),
        created_by=g.user,
        # Bound at creation; submit_gradients reads it from the task, never
        # from the per-request payload (closes the budget-bypass vector).
        dataset_id=payload.get("dataset_id"),
    )
    return jsonify({"task_id": task_id, "dp_noise_mult": noise_mult}), 201


@routes.route("/tasks", methods=["GET"])
@login_required()
def list_tasks():
    """Return all FL tasks as JSON (used by the UI to refresh the tasks table)."""
    try:
        with g.db.cursor() as cur:
            base_sql = (
                "SELECT id, status, algorithm, rounds_total, rounds_done, "
                "dp_epsilon, simulation, created_at FROM _fd.fl_tasks "
            )
            # Non-admins only see tasks they created (per-task ownership,
            # consistent with _load_task_authorized).
            if g.role == "admin":
                cur.execute(base_sql + "ORDER BY created_at DESC LIMIT 50")
            else:
                cur.execute(
                    base_sql
                    + "WHERE created_by = %s ORDER BY created_at DESC LIMIT 50",
                    (g.user,),
                )
            cols = [d[0] for d in cur.description]
            tasks = [dict(zip(cols, r)) for r in cur.fetchall()]
        for t in tasks:
            if t.get("created_at"):
                t["created_at"] = str(t["created_at"])
        return jsonify(tasks), 200
    except Exception as exc:
        g.db.rollback()
        return jsonify({"error": str(exc)}), 500


@routes.route("/tasks/<task_id>", methods=["GET"])
@login_required()
def get_task(task_id):
    task, _authz_err = _load_task_authorized(task_id)
    if _authz_err:
        return _authz_err
    return jsonify(task), 200


@routes.route("/tasks/<task_id>/cancel", methods=["POST"])
@login_required("admin", "curator")
def cancel_task(task_id):
    """Mark a stuck or unwanted task as cancelled (status → failed)."""
    task, _authz_err = _load_task_authorized(task_id)
    if _authz_err:
        return _authz_err
    if task.get("status") == "completed":
        return jsonify({"error": "Cannot cancel a completed task"}), 400
    fl_db.set_task_status(g.db, task_id, "failed")
    return jsonify({"task_id": task_id, "status": "failed"}), 200


@routes.route("/tasks/<task_id>/export", methods=["GET"])
@login_required()
def export_task(task_id):
    """
    Export FL task results as JSON: task config + per-round epsilon log.
    Weights are excluded (privacy hygiene — use export-params to store them).
    """
    task, _authz_err = _load_task_authorized(task_id)
    if _authz_err:
        return _authz_err

    rounds = fl_db.list_rounds(g.db, task_id)
    for r in rounds:
        r.pop("aggregated_weights", None)  # never expose raw weights

    fmt = request.args.get("format", "json")
    if fmt == "csv":
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["round_n", "status", "client_count", "epsilon_spent", "loss", "created_at"])
        for r in rounds:
            writer.writerow([
                r.get("round_n"), r.get("status"), r.get("client_count"),
                r.get("epsilon_spent"), r.get("loss"), r.get("created_at"),
            ])
        return Response(
            buf.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": f"attachment; filename=fl_task_{task_id[:8]}_rounds.csv"},
        )

    # JSON export
    export = {
        "task_id": task_id,
        "algorithm": task.get("algorithm"),
        "rounds_total": task.get("rounds_total"),
        "rounds_done": task.get("rounds_done"),
        "dp_epsilon": task.get("dp_epsilon"),
        "dp_delta": task.get("dp_delta"),
        "dp_noise_mult": task.get("dp_noise_mult"),
        "dp_clip_norm": task.get("dp_clip_norm"),
        "mu": task.get("mu"),
        "simulation": task.get("simulation"),
        "sim_alpha": task.get("sim_alpha"),
        "sim_n_clients": task.get("sim_n_clients"),
        "model_arch": task.get("model_arch"),
        "status": task.get("status"),
        "created_at": str(task.get("created_at", "")),
        "rounds": [
            {
                "round_n": r.get("round_n"),
                "status": r.get("status"),
                "client_count": r.get("client_count"),
                "epsilon_spent": r.get("epsilon_spent"),
                "loss": r.get("loss"),
                "created_at": str(r.get("created_at", "")),
            }
            for r in rounds
        ],
    }
    return Response(
        json.dumps(export, indent=2),
        mimetype="application/json",
        headers={"Content-Disposition": f"attachment; filename=fl_task_{task_id[:8]}.json"},
    )


@routes.route("/tasks/<task_id>/rounds", methods=["GET"])
@login_required()
def list_rounds(task_id):
    task, _authz_err = _load_task_authorized(task_id)
    if _authz_err:
        return _authz_err
    rounds = fl_db.list_rounds(g.db, task_id)
    # Strip raw weights from response — never expose to clients
    for r in rounds:
        r.pop("aggregated_weights", None)
    return jsonify(rounds), 200


@routes.route("/tasks/<task_id>/rounds/<int:round_n>/gradients", methods=["POST"])
@login_required("admin", "curator")
def submit_gradients(task_id, round_n):
    """
    Accept an encrypted client weight update, decrypt in memory,
    clip to L2 norm, add Gaussian DP noise, and aggregate.
    """
    task, _authz_err = _load_task_authorized(task_id)
    if _authz_err:
        return _authz_err

    payload = request.get_json(silent=True) or {}
    if "ciphertext" not in payload or "nonce" not in payload:
        return jsonify({"error": "Encrypted gradient payload required"}), 400

    # Epsilon budget is keyed to the dataset bound to the task at creation
    # time — NOT the client-supplied payload — so a client cannot skip
    # budget enforcement by omitting/altering dataset_id.
    dataset_id = task.get("dataset_id")
    if dataset_id:
        budget = dp_budget.get_epsilon_budget(g.db, dataset_id)
        if budget and (budget["spent"] >= budget["total_budget"]):
            return jsonify({"error": "Epsilon budget exhausted for this dataset"}), 403

    # Bind this submission to a distinct client for real-FL tasks: a client
    # may contribute at most once per round, so a single caller cannot satisfy
    # the round's client count by itself. Simulation tasks (one caller drives
    # all synthetic clients) are exempt.
    is_sim = bool(task.get("simulation"))
    if not is_sim:
        client_key = str(payload.get("site_id") or f"user:{g.user}")
        if not fl_db.register_round_submission(
            g.db, task_id, round_n, client_key
        ):
            return (
                jsonify(
                    {"error": "This client already submitted for this round"}
                ),
                409,
            )

    # Decrypt in memory — never written to disk. kernel.crypto resolves the
    # app SECRET_KEY internally; the plugin never handles the core secret.
    weights = decrypt_weights(payload, task_id)

    # DP pipeline: clip per client now; noise is added ONCE to the aggregated
    # sum below (standard DP-FedAvg). Adding noise per client and averaging
    # would shrink effective noise to ~sigma/sqrt(N), making the real epsilon
    # larger than what the RDP accountant (one GaussianDpEvent/round) reports.
    clip_norm = float(task["dp_clip_norm"])
    noise_mult = float(task["dp_noise_mult"])
    clipped = clip_gradients(weights, clip_norm)

    # Open or get current round
    rnd = fl_db.get_round(g.db, task_id, round_n)
    if rnd is None:
        fl_db.create_round(g.db, task_id, round_n)

    # Accumulate into round — fetch existing aggregated weights if present
    rnd = fl_db.get_round(g.db, task_id, round_n)
    existing = rnd.get("aggregated_weights") or []
    existing_count = rnd.get("client_count", 0)

    # Running sum of CLIPPED (un-noised) updates; noised on aggregation trigger
    if existing:
        acc = np.array(existing, dtype=np.float32) + clipped
    else:
        acc = clipped.copy()
    # For real FL the round size is the number of DISTINCT clients that have
    # registered a submission; simulation keeps the simple running counter.
    if is_sim:
        new_count = existing_count + 1
    else:
        new_count = fl_db.count_round_submissions(g.db, task_id, round_n)

    # Check if all expected clients have submitted
    clients_needed = int(task.get("sim_n_clients", 1))
    is_final = new_count >= clients_needed

    if is_final:
        # Add Gaussian noise ONCE to the accumulated sum (sensitivity = clip_norm
        # w.r.t. one client), then divide by client count to get the private
        # mean. This matches the accountant's one-Gaussian-per-round model.
        noised_sum = add_gaussian_noise_dp(acc, noise_mult, clip_norm)
        aggregated = np.nan_to_num(
            noised_sum / new_count, nan=0.0, posinf=0.0, neginf=0.0
        ).tolist()
        eps_spent = compute_epsilon_spent(
            noise_multiplier=noise_mult,
            delta=float(task["dp_delta"]),
            rounds_done=int(task["rounds_done"]) + 1,
        )

        # Atomically check-and-consume the budget BEFORE persisting the round,
        # under a row lock, so concurrent final submissions cannot overspend.
        if dataset_id and not dp_budget.consume_epsilon_guarded(
            g.db, dataset_id, eps_spent
        ):
            return (
                jsonify({"error": "Epsilon budget exhausted for this dataset"}),
                403,
            )

        fl_db.store_aggregated_weights(g.db, task_id, round_n,
                                        aggregated, eps_spent, None)
        fl_db.advance_task_round(g.db, task_id)

        if int(task["rounds_done"]) + 1 >= int(task["rounds_total"]):
            fl_db.set_task_status(g.db, task_id, "completed")
    else:
        # Store intermediate accumulation back into round
        with g.db.cursor() as cur:
            cur.execute(
                "UPDATE _fd.fl_rounds SET aggregated_weights=%s, client_count=%s WHERE task_id=%s AND round_n=%s",
                (json.dumps(acc.tolist()), new_count, task_id, round_n),
            )
        g.db.commit()

    return jsonify({"status": "accepted", "round": round_n, "clients": new_count}), 200


@routes.route("/tasks/<task_id>/model", methods=["GET"])
@login_required()
def get_model(task_id):
    task, _authz_err = _load_task_authorized(task_id)
    if _authz_err:
        return _authz_err
    weights = fl_db.get_latest_weights(g.db, task_id)
    if weights is None:
        return jsonify({"error": "No completed round yet"}), 404
    return jsonify({"task_id": task_id, "weights": weights}), 200


@routes.route("/tasks/<task_id>/simulate", methods=["POST"])
@login_required("admin", "curator")
def run_simulation(task_id):
    """
    Execute all FL rounds in-process for simulation tasks.

    Scientifically correct DP-FL protocol (McMahan et al. 2018):
      1. Each client trains locally → produces updated weights w_i
      2. Compute weight DELTA: Δ_i = w_i - w_global  (not w_i itself)
      3. Clip the DELTA to L2 norm C:  Δ_clipped = Δ_i * min(1, C/||Δ_i||)
         → This bounds client sensitivity to C, making the Gaussian mechanism valid
      4. Add Gaussian noise to the clipped delta: Δ_noised = Δ_clipped + N(0, σ²I)
         where σ = noise_mult * C
      5. Aggregate noised deltas: Δ_agg = weighted_mean(Δ_noised_i)
      6. Update global model: w_global ← w_global + Δ_agg

    Dirichlet partition uses quantile-binned targets for continuous regression,
    so α correctly controls IID/non-IID degree regardless of target type.
    """
    # torch is imported lazily here (Phase 5a): only this endpoint needs the
    # engine, so the plugin's task-CRUD surface loads even without torch.
    from .engine import (
        TabularMLP,
        dirichlet_partition,
        eval_loss,
        fedprox_aggregate,
        get_flat_weights,
        local_train_fedprox,
    )

    task, _authz_err = _load_task_authorized(task_id)
    if _authz_err:
        return _authz_err
    if not task.get("simulation"):
        return jsonify({"error": "Task is not a simulation task"}), 400
    if task.get("status") == "completed":
        return jsonify({"error": "Task already completed"}), 400

    arch       = task.get("model_arch") or {}
    input_dim  = int(arch.get("input_dim", 10))
    hidden     = arch.get("hidden_dims", [64, 32])
    output_dim = int(arch.get("output_dim", 1))
    ml_task    = arch.get("task", "regression")

    n_clients  = int(task.get("sim_n_clients", 5))
    alpha      = float(task.get("sim_alpha", 0.5))
    rounds     = int(task.get("rounds_total", 10))
    mu         = float(task.get("mu", 0.01))
    clip_norm  = float(task.get("dp_clip_norm", 1.0))
    noise_mult = float(task.get("dp_noise_mult") or 1.0)
    dp_delta   = float(task.get("dp_delta", 1e-5))

    # Synthetic dataset — large enough for signal to compete with DP noise.
    rng = np.random.default_rng(42)
    n_samples = max(n_clients * 300, 1500)
    X = rng.standard_normal((n_samples, input_dim)).astype(np.float32)
    true_w = rng.standard_normal(input_dim).astype(np.float32)
    if ml_task == "regression":
        y = (X @ true_w).astype(np.float32)
    else:
        y = rng.integers(0, max(output_dim, 2), n_samples).astype(np.float32)

    # Hold out 20% for validation loss (global convergence monitor)
    n_val = max(int(n_samples * 0.2), 50)
    X_val, y_val = X[:n_val], y[:n_val]
    X_train, y_train = X[n_val:], y[n_val:]

    # Dirichlet partition on training set (quantile-bins continuous y)
    partitions = dirichlet_partition(X_train, y_train, n_clients=n_clients, alpha=alpha)

    n_params = sum(
        np.prod(list(p.shape))
        for p in TabularMLP(input_dim, hidden, output_dim, ml_task).parameters()
    )
    sigma = noise_mult * clip_norm
    snr_note = (
        f"σ={sigma:.3f}, C={clip_norm}, params={n_params}. "
        f"Per-coord noise ≈ {sigma/np.sqrt(n_params):.4f} vs "
        f"max per-coord delta ≈ {clip_norm/np.sqrt(n_params):.4f}. "
        + ("SNR < 1 — increase ε for better convergence."
           if sigma > clip_norm else "SNR ≥ 1 — good privacy-utility tradeoff.")
    )

    model = TabularMLP(input_dim=input_dim, hidden_dims=hidden,
                       output_dim=output_dim, task=ml_task)
    global_weights = get_flat_weights(model)

    fl_db.set_task_status(g.db, task_id, "running")

    round_results = []
    for rnd in range(1, rounds + 1):
        fl_db.create_round(g.db, task_id, rnd)

        client_deltas = []
        client_sizes  = []
        for (px, py) in partitions:
            if len(px) == 0:
                continue
            local_w, _ = local_train_fedprox(
                model, global_weights, px, py,
                epochs=5, lr=0.01, mu=mu, task=ml_task
            )
            # DP-FL: clip the WEIGHT DELTA, not the full weights.
            delta = local_w - global_weights
            clipped_delta = clip_gradients(delta, clip_norm)
            noised_delta  = add_gaussian_noise_dp(clipped_delta, noise_mult, clip_norm)
            client_deltas.append(noised_delta)
            client_sizes.append(len(px))

        # Aggregate noised deltas and apply to global model
        agg_delta    = fedprox_aggregate(client_deltas, client_sizes)
        global_weights = global_weights + agg_delta

        # Detect divergence — NaN/Inf means noise overwhelmed signal entirely
        if np.any(np.isnan(global_weights)) or np.any(np.isinf(global_weights)):
            fl_db.set_task_status(g.db, task_id, "failed")
            return jsonify({
                "error": (
                    f"Model diverged at round {rnd}. "
                    f"Noise multiplier {noise_mult:.2f} too large for this "
                    f"ε/data combination. Increase ε or add more data."
                ),
                "snr_diagnostic": snr_note,
            }), 422

        # Compute validation loss on held-out set (global convergence monitor)
        val_loss = eval_loss(model, global_weights, X_val, y_val, task=ml_task)

        eps_spent = compute_epsilon_spent(
            noise_multiplier=noise_mult, delta=dp_delta, rounds_done=rnd
        )

        fl_db.store_aggregated_weights(
            g.db, task_id, rnd,
            global_weights.tolist(), eps_spent, val_loss
        )
        fl_db.advance_task_round(g.db, task_id)
        round_results.append({
            "round": rnd,
            "epsilon_spent": eps_spent,
            "val_loss": val_loss,
        })

    fl_db.set_task_status(g.db, task_id, "completed")

    total_eps = round_results[-1]["epsilon_spent"] if round_results else 0.0
    return jsonify({
        "task_id": task_id,
        "rounds_completed": rounds,
        "epsilon_spent": total_eps,
        "status": "completed",
        "snr_diagnostic": snr_note,
        "rounds": round_results,
    }), 200


@routes.route("/tasks/<task_id>/export-params", methods=["POST"])
@login_required("admin", "curator")
def export_params(task_id):
    """Export final aggregated FL weights as a named PBPK parameter set.

    Cross-plugin hand-off: posts to the PBPK plugin's HTTP API rather than
    importing it (guide §3). The caller's session cookie is forwarded so
    PBPK's own @login_required + ownership checks apply to the write.
    """
    task, _authz_err = _load_task_authorized(task_id)
    if _authz_err:
        return _authz_err
    weights = fl_db.get_latest_weights(g.db, task_id)
    if weights is None:
        return jsonify({"error": "No model to export yet"}), 404

    payload = request.get_json(silent=True) or {}
    name = payload.get("name", f"FL-task-{task_id[:8]}")
    description = payload.get(
        "description", f"Federated learning aggregated weights (task {task_id})"
    )

    try:
        resp = requests.post(
            request.host_url.rstrip("/") + "/model/parameter-sets",
            json={
                "name": name,
                "description": description,
                "params": {"fl_weights": weights, "fl_task_id": task_id},
                "source": "federated",
            },
            cookies=request.cookies,
            timeout=30,
        )
    except requests.RequestException as exc:
        return jsonify({"error": f"parameter-set export failed: {exc}"}), 502
    if resp.status_code != 201:
        return jsonify({
            "error": "parameter-set export rejected by PBPK plugin",
            "detail": resp.text,
        }), 502
    ps_id = resp.json().get("id")

    # Purge raw weights from DB after export (privacy hygiene)
    fl_db.purge_round_weights(g.db, task_id)

    return jsonify({"parameter_set_id": ps_id, "name": name}), 201
