"""VFL integration tests.

test_engine_training_loop  — pure engine, no DB, runs immediately.
test_simulate_*            — require live DB, marked skip.
"""
import numpy as np
import pytest
import torch

from plugins.vertical_fl.engine import (
    SiteEncoder,
    VFLTopModel,
    calibrate_task_sigma,
    dirichlet_feature_partition,
    renyi_epsilon_per_task,
    split_backward,
    vfl_aggregate_embeddings,
)


def _make_synthetic(n_samples=120, n_features=14, seed=0):
    rng = np.random.default_rng(seed)
    X = rng.standard_normal((n_samples, 1, n_features)).astype(np.float32)
    y = rng.integers(0, 2, (n_samples, 1)).astype(np.float32)
    return X, y


def test_engine_training_loop():
    """Three parties, binary task, 5 rounds. Loss must decrease overall."""
    torch.manual_seed(0)
    np.random.seed(0)

    n_parties, embed_dim, rounds = 3, 64, 5
    task_types = ["binary"]
    # Low sigma: isolates training-loop mechanics from DP noise, which is
    # covered by test_dp_noise_adds_variance/test_renyi_epsilon_*.
    sigma_list = [0.05]
    clip_norm = 1.0

    X, y = _make_synthetic()
    # Split 14 features across 3 parties: 5 / 5 / 4
    X_parts = dirichlet_feature_partition(X.squeeze(1), n_parties=n_parties)
    X_parts = [p[:, np.newaxis, :] for p in X_parts]

    encoders = [SiteEncoder(input_dim=X_parts[i].shape[2], embed_dim=embed_dim)
                for i in range(n_parties)]
    top_model = VFLTopModel(agg_dim=n_parties * embed_dim, task_types=task_types)
    opts = [torch.optim.Adam(enc.parameters(), lr=1e-3) for enc in encoders]

    losses = []
    for _ in range(rounds):
        z_parts = [enc(torch.tensor(X_parts[i])) for i, enc in enumerate(encoders)]
        z_np = vfl_aggregate_embeddings(z_parts).detach().numpy()

        grad_slices, round_losses = split_backward(
            top_model, z_np, [y],
            sigma_per_task=sigma_list,
            clip_norm=clip_norm,
            party_embed_dims=[embed_dim] * n_parties,
        )
        losses.append(round_losses[0])

        for i, (enc, opt, g) in enumerate(zip(encoders, opts, grad_slices)):
            opt.zero_grad()
            z = enc(torch.tensor(X_parts[i]))
            z.backward(torch.tensor(g))
            opt.step()

    # Loss should be lower in the last round than the first
    assert losses[-1] < losses[0], (
        f"Loss did not decrease: first={losses[0]:.4f} last={losses[-1]:.4f}"
    )


def test_engine_multitask_training_loop():
    """Three parties, 4 heterogeneous tasks (IHM/Decomp/Regression/Pheno).
    Verifies MMoE handles mixed loss types without error and loss moves."""
    n_parties, embed_dim, rounds = 3, 64, 3
    task_types = ["binary", "binary", "regression", "multilabel_25"]
    sigma_list = [0.8, 1.0, 1.0, 1.2]

    rng = np.random.default_rng(1)
    n = 80
    X = rng.standard_normal((n, 1, 14)).astype(np.float32)
    labels = [
        rng.integers(0, 2, (n, 1)).astype(np.float32),
        rng.integers(0, 2, (n, 1)).astype(np.float32),
        rng.standard_normal((n, 1)).astype(np.float32),
        rng.integers(0, 2, (n, 25)).astype(np.float32),
    ]

    X_parts = dirichlet_feature_partition(X.squeeze(1), n_parties=n_parties)
    X_parts = [p[:, np.newaxis, :] for p in X_parts]

    encoders = [SiteEncoder(input_dim=X_parts[i].shape[2], embed_dim=embed_dim)
                for i in range(n_parties)]
    top_model = VFLTopModel(agg_dim=n_parties * embed_dim, task_types=task_types,
                            n_experts=4)
    opts = [torch.optim.Adam(enc.parameters(), lr=1e-3) for enc in encoders]

    first_losses, last_losses = None, None
    for rnd in range(rounds):
        z_parts = [enc(torch.tensor(X_parts[i])) for i, enc in enumerate(encoders)]
        z_np = vfl_aggregate_embeddings(z_parts).detach().numpy()

        grad_slices, round_losses = split_backward(
            top_model, z_np, labels,
            sigma_per_task=sigma_list,
            clip_norm=1.0,
            party_embed_dims=[embed_dim] * n_parties,
        )
        if rnd == 0:
            first_losses = round_losses[:]
        last_losses = round_losses[:]

        for i, (enc, opt, g) in enumerate(zip(encoders, opts, grad_slices)):
            opt.zero_grad()
            z = enc(torch.tensor(X_parts[i]))
            z.backward(torch.tensor(g))
            opt.step()

    assert len(last_losses) == 4
    # At least one task's loss should have improved
    improved = sum(l < f for l, f in zip(last_losses, first_losses))
    assert improved >= 1, f"No task improved: first={first_losses} last={last_losses}"


def test_renyi_epsilon_increases_with_rounds():
    """More rounds → more privacy budget consumed."""
    eps_1 = renyi_epsilon_per_task([1.0], delta=1e-5, rounds_done=1)
    eps_5 = renyi_epsilon_per_task([1.0], delta=1e-5, rounds_done=5)
    assert eps_5["task_0"] > eps_1["task_0"]


def test_renyi_epsilon_lower_for_higher_sigma():
    """Higher noise multiplier → lower epsilon (stronger privacy)."""
    eps_low  = renyi_epsilon_per_task([0.5], delta=1e-5, rounds_done=5)
    eps_high = renyi_epsilon_per_task([2.0], delta=1e-5, rounds_done=5)
    assert eps_high["task_0"] < eps_low["task_0"]


def test_calibrated_sigma_respects_epsilon_budget():
    """Epsilon actually spent under a calibrated sigma must not exceed the
    requested budget — this is what create_task now derives task_sigma from
    when the caller doesn't supply it explicitly."""
    dp_epsilon, dp_delta, rounds_total = 1.0, 1e-5, 10
    task_types = ["binary", "binary", "regression", "multilabel_25"]

    task_sigma = calibrate_task_sigma(dp_epsilon, dp_delta, rounds_total, task_types)
    spent = renyi_epsilon_per_task(list(task_sigma.values()), dp_delta, rounds_total)

    for eps in spent.values():
        assert eps <= dp_epsilon + 1e-4


def test_calibrated_sigma_scales_with_epsilon_budget():
    """A tighter epsilon budget must produce higher noise than a looser one —
    previously task_sigma defaulted to a flat 1.0 regardless of dp_epsilon."""
    task_types = ["binary"]
    tight = calibrate_task_sigma(0.1, 1e-5, 10, task_types)
    loose = calibrate_task_sigma(10.0, 1e-5, 10, task_types)
    assert tight["task_0"] > loose["task_0"]


def test_calibrated_sigma_orders_by_output_dimensionality():
    """Higher-dimensional task heads get more noise (higher sigma)."""
    task_types = ["binary", "regression", "multilabel_25"]
    task_sigma = calibrate_task_sigma(1.0, 1e-5, 10, task_types)
    assert task_sigma["task_0"] <= task_sigma["task_1"] <= task_sigma["task_2"]


# ── DB-dependent tests (require live services) ────────────────────────────────

@pytest.mark.skip(reason="requires live DB — run with services up")
def test_simulate_endpoint_completes():
    """POST /vfl/tasks (simulation=True) → simulate → status=completed."""
    raise NotImplementedError


@pytest.mark.skip(reason="requires live DB — run with services up")
def test_psi_gates_training():
    """Embedding submission returns 400 until PSI is aligned."""
    raise NotImplementedError


@pytest.mark.skip(reason="requires live DB — run with services up")
def test_export_strips_embeddings():
    """GET /vfl/tasks/<id>/export must not contain raw embeddings."""
    raise NotImplementedError
