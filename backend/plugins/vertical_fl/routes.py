"""Routes for the vertical FL plugin. See docs/PLUGIN_GUIDE.md §6.

Every import is from ``kernel.*`` — never reach into ``src.*`` or a sibling
plugin (guide §3). UI is served by the horizontal_fl dashboard (/fl/ui).

/vfl/tasks                                      POST — create task / GET — list
/vfl/tasks/<id>                                 GET  — task status
/vfl/tasks/<id>/parties                         POST — register party
/vfl/tasks/<id>/psi                             POST — submit hashed IDs
/vfl/tasks/<id>/psi/status                      GET  — PSI status + cohort size
/vfl/tasks/<id>/rounds/<n>/embeddings           POST — submit embeddings
/vfl/tasks/<id>/rounds/<n>/gradients/<site_id>  GET  — retrieve gradient slice
/vfl/tasks/<id>/model                           GET  — top model weights
/vfl/tasks/<id>/simulate                        POST — run all rounds in-process
/vfl/tasks/<id>/export                          GET  — export config + round log
"""
from flask import Blueprint, g, jsonify, request

from kernel.auth import login_required

from . import db as vfl_db

routes = Blueprint("vertical_fl_routes", __name__)


def _load_task_authorized(task_id):
    task = vfl_db.get_task(g.db, task_id)
    if task is None:
        return None, (jsonify({"error": "Task not found"}), 404)
    owner = task.get("created_by")
    if g.role != "admin" and (owner is None or str(owner) != str(g.user)):
        return None, (jsonify({"error": "Forbidden"}), 403)
    return task, None


# ── Task endpoints ─────────────────────────────────────────────────────────────

@routes.post("/tasks")
@login_required("admin", "curator")
def create_task():
    payload = request.get_json(silent=True) or {}
    missing = {"dp_epsilon", "rounds_total"} - set(payload)
    if missing:
        return jsonify({"error": f"Missing fields: {sorted(missing)}"}), 400

    task_types = payload.get("task_types", ["binary"])
    dp_epsilon = float(payload["dp_epsilon"])
    dp_delta = float(payload.get("dp_delta", 1e-5))
    rounds_total = int(payload["rounds_total"])

    task_sigma = payload.get("task_sigma")
    if not task_sigma:
        from .engine import calibrate_task_sigma
        task_sigma = calibrate_task_sigma(dp_epsilon, dp_delta, rounds_total, task_types)

    task_id = vfl_db.create_task(
        g.db,
        n_parties=int(payload.get("n_parties", 3)),
        n_tasks=int(payload.get("n_tasks", 1)),
        task_types=task_types,
        task_sigma=task_sigma,
        dp_epsilon=dp_epsilon,
        dp_delta=dp_delta,
        dp_clip_norm=float(payload.get("dp_clip_norm", 1.0)),
        rounds_total=rounds_total,
        simulation=bool(payload.get("simulation", False)),
        sim_n_clients=int(payload.get("sim_n_clients", 3)),
        sim_alpha=float(payload.get("sim_alpha", 0.5)),
        model_arch=payload.get("model_arch", {}),
        dataset_id=payload.get("dataset_id"),
        created_by=g.user,
    )
    return jsonify({"task_id": task_id}), 201


@routes.get("/tasks")
@login_required()
def list_tasks():
    tasks = vfl_db.list_tasks(g.db, user_id=g.user, is_admin=(g.role == "admin"))
    for t in tasks:
        if t.get("created_at"):
            t["created_at"] = str(t["created_at"])
    return jsonify(tasks), 200


@routes.get("/tasks/<task_id>")
@login_required()
def get_task(task_id):
    task, err = _load_task_authorized(task_id)
    if err:
        return err
    return jsonify(task), 200


# ── Party registration ─────────────────────────────────────────────────────────

@routes.post("/tasks/<task_id>/parties")
@login_required("admin", "curator")
def register_party(task_id):
    task, err = _load_task_authorized(task_id)
    if err:
        return err
    payload = request.get_json(silent=True) or {}
    missing = {"site_id", "feature_dim"} - set(payload)
    if missing:
        return jsonify({"error": f"Missing fields: {sorted(missing)}"}), 400

    party_id = vfl_db.register_party(
        g.db,
        task_id=task_id,
        site_id=payload["site_id"],
        feature_dim=int(payload["feature_dim"]),
        feature_names=payload.get("feature_names", []),
    )
    return jsonify({"party_id": party_id}), 201


# ── PSI ────────────────────────────────────────────────────────────────────────

@routes.post("/tasks/<task_id>/psi")
@login_required("admin", "curator")
def submit_psi(task_id):
    task, err = _load_task_authorized(task_id)
    if err:
        return err
    payload = request.get_json(silent=True) or {}
    missing = {"site_id", "hashed_ids"} - set(payload)
    if missing:
        return jsonify({"error": f"Missing fields: {sorted(missing)}"}), 400

    cohort_size = vfl_db.submit_psi(
        g.db,
        task_id=task_id,
        site_id=payload["site_id"],
        hashed_ids=payload["hashed_ids"],
        n_parties=int(task["n_parties"]),
    )
    status = "aligned" if cohort_size is not None else "partial"
    return jsonify({"psi_status": status, "cohort_size": cohort_size}), 200


@routes.get("/tasks/<task_id>/psi/status")
@login_required()
def psi_status(task_id):
    task, err = _load_task_authorized(task_id)
    if err:
        return err
    return jsonify({
        "psi_status": task.get("psi_status"),
        "cohort_size": task.get("psi_cohort_size"),
    }), 200


# ── Round: embeddings + gradients ─────────────────────────────────────────────

@routes.post("/tasks/<task_id>/rounds/<int:round_n>/embeddings")
@login_required("admin", "curator")
def submit_embeddings(task_id, round_n):
    # torch imported lazily — plugin loads without it installed
    import numpy as np
    from .engine import VFLTopModel, split_backward, vfl_aggregate_embeddings

    task, err = _load_task_authorized(task_id)
    if err:
        return err
    if task.get("psi_status") != "aligned":
        return jsonify({"error": "PSI not complete"}), 400

    payload = request.get_json(silent=True) or {}
    missing = {"site_id", "embedding"} - set(payload)
    if missing:
        return jsonify({"error": f"Missing fields: {sorted(missing)}"}), 400

    # Ensure the round row exists before accumulating
    rnd = vfl_db.get_round(g.db, task_id, round_n)
    if rnd is None:
        vfl_db.create_round(g.db, task_id, round_n)

    received = vfl_db.store_embeddings(
        g.db, task_id, round_n,
        site_id=payload["site_id"],
        embedding=payload["embedding"],
    )

    n_parties = int(task["n_parties"])
    if received < n_parties:
        return jsonify({"status": "waiting", "received": received}), 200

    # All parties have submitted — run top-model forward+backward
    rnd = vfl_db.get_round(g.db, task_id, round_n)
    arch = task.get("model_arch") or {}
    task_types = task.get("task_types") or ["binary"]
    embed_dim = int(arch.get("embed_dim", 64))
    agg_dim = n_parties * embed_dim

    top_model = VFLTopModel(
        agg_dim=agg_dim,
        task_types=task_types,
        n_experts=int(arch.get("n_experts", 4)),
    )

    # Reconstruct aggregated embedding from stored per-party embeddings
    embeddings_dict = rnd.get("embeddings") or {}
    import torch
    z_parts = [torch.tensor(embeddings_dict[sid], dtype=torch.float32)
               for sid in sorted(embeddings_dict)]
    z_concat = vfl_aggregate_embeddings(z_parts).detach().numpy()

    # Labels come from the payload on the final submission (simulation passes them)
    labels = payload.get("labels") or [
        np.zeros((z_concat.shape[0], 1), dtype=np.float32)
        for _ in task_types
    ]
    sigma_per_task = list(task.get("task_sigma", {}).values()) or [1.0] * len(task_types)

    grad_slices, losses = split_backward(
        top_model, z_concat, labels,
        sigma_per_task=sigma_per_task,
        clip_norm=float(task.get("dp_clip_norm", 1.0)),
        party_embed_dims=[embed_dim] * n_parties,
    )

    from kernel.rdp_accountant import compute_epsilon_spent
    dp_delta = float(task.get("dp_delta", 1e-5))
    rounds_done = int(task.get("rounds_done", 0)) + 1
    epsilon_per_task = {
        f"task_{k}": compute_epsilon_spent(s, dp_delta, rounds_done)
        for k, s in enumerate(sigma_per_task)
    }

    site_ids_sorted = sorted(embeddings_dict)
    vfl_db.store_gradients(
        g.db, task_id, round_n,
        gradients={sid: grad_slices[i].tolist() for i, sid in enumerate(site_ids_sorted)},
    )

    vfl_db.store_top_weights(
        g.db, task_id, round_n,
        top_weights=list(top_model.state_dict().values())[0].tolist(),
        loss_per_task={f"task_{k}": v for k, v in enumerate(losses)},
        epsilon_per_task=epsilon_per_task,
    )
    vfl_db.advance_task_round(g.db, task_id)

    if rounds_done >= int(task["rounds_total"]):
        vfl_db.set_task_status(g.db, task_id, "completed")

    # Purge raw embeddings after gradients are stored (privacy hygiene)
    vfl_db.purge_round_embeddings(g.db, task_id, round_n)

    return jsonify({
        "status": "aggregated",
        "round": round_n,
        "losses": losses,
        "epsilon_per_task": epsilon_per_task,
    }), 200


@routes.get("/tasks/<task_id>/rounds/<int:round_n>/gradients/<site_id>")
@login_required("admin", "curator")
def get_gradients(task_id, round_n, site_id):
    # Parties poll this after submitting embeddings to get their gradient slice
    task, err = _load_task_authorized(task_id)
    if err:
        return err

    parties = vfl_db.list_parties(g.db, task_id)
    site_ids = sorted(p["site_id"] for p in parties)
    if site_id not in site_ids:
        return jsonify({"error": "Unknown site_id"}), 404

    rnd = vfl_db.get_round(g.db, task_id, round_n)
    if rnd is None or rnd.get("status") != "done":
        return jsonify({"error": "Round not complete"}), 404

    # Single-fetch: a repeat call 410s instead of re-serving the slice.
    grad = vfl_db.consume_gradient(g.db, task_id, round_n, site_id)
    if grad is None:
        return jsonify({"error": "Gradient no longer available — fetch immediately after round closes"}), 410
    return jsonify({"site_id": site_id, "gradient": grad}), 200


# ── Model + simulate + export ─────────────────────────────────────────────────

@routes.get("/tasks/<task_id>/model")
@login_required()
def get_model(task_id):
    task, err = _load_task_authorized(task_id)
    if err:
        return err
    weights = vfl_db.get_latest_top_weights(g.db, task_id)
    if weights is None:
        return jsonify({"error": "No completed round yet"}), 404
    return jsonify({"task_id": task_id, "top_model_weights": weights}), 200


@routes.post("/tasks/<task_id>/simulate")
@login_required("admin", "curator")
def run_simulation(task_id):
    # torch imported lazily — plugin loads without it installed
    import numpy as np
    import torch
    from .engine import (
        SiteEncoder, VFLTopModel, dirichlet_feature_partition,
        renyi_epsilon_per_task, split_backward, vfl_aggregate_embeddings,
    )

    task, err = _load_task_authorized(task_id)
    if err:
        return err
    if not task.get("simulation"):
        return jsonify({"error": "Not a simulation task"}), 400
    if task.get("status") == "completed":
        return jsonify({"error": "Task already completed"}), 400

    arch          = task.get("model_arch") or {}
    n_parties     = int(task.get("n_parties", 3))
    task_types    = task.get("task_types") or ["binary"]
    embed_dim     = int(arch.get("embed_dim", 64))
    hidden_dim    = int(arch.get("hidden_dim", 128))
    n_experts     = int(arch.get("n_experts", 4))
    rounds_total  = int(task.get("rounds_total", 10))
    dp_clip_norm  = float(task.get("dp_clip_norm", 1.0))
    dp_delta      = float(task.get("dp_delta", 1e-5))
    sim_alpha     = float(task.get("sim_alpha", 0.5))
    sigma_list    = list(task.get("task_sigma", {}).values()) or [1.0] * len(task_types)

    # Synthetic dataset — one time step per sample for simplicity
    rng = np.random.default_rng(42)
    n_samples = max(int(task.get("sim_n_clients", 3)) * 200, 600)
    n_features = int(arch.get("input_dim", 14))
    X = rng.standard_normal((n_samples, 1, n_features)).astype(np.float32)

    feature_groups = arch.get("feature_groups")
    X_parts = dirichlet_feature_partition(
        X.squeeze(1), n_parties=n_parties, feature_groups=feature_groups
    )
    # Re-add time dimension for LSTM: (batch, 1, features_per_party)
    X_parts = [p[:, np.newaxis, :] for p in X_parts]

    # Synthetic labels per task type
    labels = []
    for tt in task_types:
        if tt.startswith("multilabel_"):
            k = int(tt.split("_")[1])
            labels.append(rng.integers(0, 2, (n_samples, k)).astype(np.float32))
        else:
            labels.append(rng.integers(0, 2, (n_samples, 1)).astype(np.float32))

    encoders = [
        SiteEncoder(input_dim=X_parts[i].shape[2], hidden_dim=hidden_dim, embed_dim=embed_dim)
        for i in range(n_parties)
    ]
    top_model = VFLTopModel(agg_dim=n_parties * embed_dim, task_types=task_types,
                            n_experts=n_experts)
    encoder_optimizers = [torch.optim.Adam(enc.parameters(), lr=1e-3) for enc in encoders]

    vfl_db.set_task_status(g.db, task_id, "running")
    round_results = []

    for rnd in range(1, rounds_total + 1):
        vfl_db.create_round(g.db, task_id, rnd)

        # Forward: each encoder produces an embedding
        z_parts = [enc(torch.tensor(X_parts[i])) for i, enc in enumerate(encoders)]
        z_concat_np = vfl_aggregate_embeddings(z_parts).detach().numpy()

        grad_slices, losses = split_backward(
            top_model, z_concat_np, labels,
            sigma_per_task=sigma_list,
            clip_norm=dp_clip_norm,
            party_embed_dims=[embed_dim] * n_parties,
        )

        # Backward: each encoder uses its gradient slice to update weights
        for i, (enc, opt, grad_np) in enumerate(zip(encoders, encoder_optimizers, grad_slices)):
            opt.zero_grad()
            z = enc(torch.tensor(X_parts[i]))
            z.backward(torch.tensor(grad_np))
            opt.step()

        eps_per_task = renyi_epsilon_per_task(sigma_list, dp_delta, rnd)
        vfl_db.store_top_weights(
            g.db, task_id, rnd,
            top_weights=[],  # top model weights not persisted in sim for brevity
            loss_per_task={f"task_{k}": v for k, v in enumerate(losses)},
            epsilon_per_task=eps_per_task,
        )
        vfl_db.advance_task_round(g.db, task_id)
        round_results.append({"round": rnd, "losses": losses, "epsilon": eps_per_task})

    vfl_db.set_task_status(g.db, task_id, "completed")
    return jsonify({
        "task_id": task_id,
        "rounds_completed": rounds_total,
        "status": "completed",
        "rounds": round_results,
    }), 200


@routes.get("/tasks/<task_id>/export")
@login_required()
def export_task(task_id):
    import json as _json
    task, err = _load_task_authorized(task_id)
    if err:
        return err
    rounds = vfl_db.list_rounds(g.db, task_id)
    for r in rounds:
        r.pop("embeddings", None)  # never expose raw embeddings
        r.pop("gradients", None)   # or unconsumed gradient slices
        if r.get("created_at"):
            r["created_at"] = str(r["created_at"])
    export = {
        "task_id": task_id,
        "status": task.get("status"),
        "n_parties": task.get("n_parties"),
        "n_tasks": task.get("n_tasks"),
        "task_types": task.get("task_types"),
        "dp_epsilon": task.get("dp_epsilon"),
        "dp_delta": task.get("dp_delta"),
        "rounds_total": task.get("rounds_total"),
        "rounds_done": task.get("rounds_done"),
        "psi_cohort_size": task.get("psi_cohort_size"),
        "model_arch": task.get("model_arch"),
        "rounds": rounds,
    }
    from flask import Response
    return Response(
        _json.dumps(export, indent=2),
        mimetype="application/json",
        headers={"Content-Disposition": f"attachment; filename=vfl_task_{task_id[:8]}.json"},
    )
