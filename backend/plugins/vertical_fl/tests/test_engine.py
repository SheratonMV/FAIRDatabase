"""Engine unit tests — no DB, no Flask required."""
import numpy as np
import pytest
import torch

from plugins.vertical_fl.engine import (
    SiteEncoder,
    VFLTopModel,
    dirichlet_feature_partition,
    dp_noise_embedding,
    psi_intersect,
    split_backward,
    vfl_aggregate_embeddings,
)

BATCH, STEPS, EMBED = 8, 10, 64


# ── Day 2 ──────────────────────────────────────────────────────────────────────

def test_site_encoder_output_shape():
    # Bottom model must produce (batch, embed_dim) regardless of input feature count
    enc = SiteEncoder(input_dim=7, embed_dim=EMBED)
    x = torch.randn(BATCH, STEPS, 7)
    out = enc(x)
    assert out.shape == (BATCH, EMBED)


def test_vfl_aggregate_shape():
    # Three parties with embed_dim=64 → concatenated vector of 192
    embeddings = [torch.randn(BATCH, EMBED) for _ in range(3)]
    agg = vfl_aggregate_embeddings(embeddings)
    assert agg.shape == (BATCH, EMBED * 3)


def test_psi_intersect_correct():
    # Only IDs present in ALL three sets should survive
    a = ["h1", "h2", "h3"]
    b = ["h2", "h3", "h4"]
    c = ["h3", "h5"]
    assert psi_intersect([a, b, c]) == ["h3"]


def test_psi_intersect_empty_input():
    assert psi_intersect([]) == []


def test_dirichlet_feature_partition_explicit_groups():
    # Explicit groups must slice exactly the specified columns
    X = np.random.randn(20, 10)
    groups = [[0, 1, 2], [3, 4, 5, 6], [7, 8, 9]]
    parts = dirichlet_feature_partition(X, n_parties=3, feature_groups=groups)
    assert parts[0].shape == (20, 3)
    assert parts[1].shape == (20, 4)
    assert parts[2].shape == (20, 3)


def test_dirichlet_feature_partition_even_split():
    X = np.random.randn(20, 9)
    parts = dirichlet_feature_partition(X, n_parties=3)
    assert sum(p.shape[1] for p in parts) == 9


# ── Day 3 ──────────────────────────────────────────────────────────────────────

def test_top_model_single_task_forward():
    # n_tasks=1 → single output tensor of shape (batch, 1)
    model = VFLTopModel(agg_dim=192, task_types=["binary"])
    z = torch.randn(BATCH, 192)
    out = model(z)
    assert len(out) == 1
    assert out[0].shape == (BATCH, 1)


def test_top_model_mmoe_forward():
    # n_tasks=4 → four output tensors, last one has 25 outputs (multilabel)
    task_types = ["binary", "binary", "regression", "multilabel_25"]
    model = VFLTopModel(agg_dim=192, task_types=task_types, n_experts=4)
    z = torch.randn(BATCH, 192)
    out = model(z)
    assert len(out) == 4
    assert out[0].shape == (BATCH, 1)
    assert out[3].shape == (BATCH, 25)


def test_split_backward_gradient_shapes():
    # Gradient slices must match each party's embed_dim
    task_types = ["binary", "binary"]
    model = VFLTopModel(agg_dim=192, task_types=task_types, n_experts=2)
    z = np.random.randn(BATCH, 192).astype(np.float32)
    labels = [np.random.randint(0, 2, (BATCH, 1)).astype(np.float32)] * 2
    sigma_per_task = [1.0, 1.2]
    grads, losses = split_backward(
        model, z, labels, sigma_per_task, clip_norm=1.0,
        party_embed_dims=[64, 64, 64],
    )
    assert len(grads) == 3
    assert all(g.shape == (BATCH, 64) for g in grads)
    assert len(losses) == 2


def test_dp_noise_adds_variance():
    # Noise variance should be ≈ (sigma * clip_norm)^2 over many samples
    rng = np.random.default_rng(42)
    grad = np.zeros((10000, 1), dtype=np.float32)
    sigma, clip_norm = 1.0, 1.0
    noised = dp_noise_embedding(grad, sigma, clip_norm)
    assert abs(float(np.var(noised)) - (sigma * clip_norm) ** 2) < 0.05
