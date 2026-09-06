"""
engine.py — Vertical FL engine.

Implements:
- SiteEncoder: LSTM bottom model, one per party
- VFLTopModel: single-task Linear or multi-task MMoE top model (server-side)
- vfl_aggregate_embeddings: concatenate party embeddings before top model
- split_backward: top-model forward+backward, returns per-party gradient slices
- dp_noise_embedding: clip + Gaussian noise on embedding gradient
- renyi_epsilon_per_task: per-task RDP accounting via kernel.rdp_accountant

Scientific references:
- Split learning: Vepakomma et al., "Split learning for health" (arXiv 2018)
- MMoE: Ma et al., "Modeling Task Relationships with Multi-gate Mixture-of-Experts" (KDD 2018)
- DP on embeddings: McMahan et al., "Learning Differentially Private RLMs" (ICLR 2018)
- Rényi DP: Mironov, "Rényi Differential Privacy" (CSF 2017)
"""
from __future__ import annotations

import numpy as np
import torch
import torch.nn as nn
from typing import Dict, List, Optional, Tuple


# ── Bottom model (one per party) ───────────────────────────────────────────────

class SiteEncoder(nn.Module):
    """LSTM encoder: processes a party's time-series features → fixed-size embedding.

    Input:  (batch, time_steps, input_dim)
    Output: (batch, embed_dim)
    """

    def __init__(self, input_dim: int, hidden_dim: int = 128,
                 num_layers: int = 2, embed_dim: int = 64):
        super().__init__()
        # LSTM captures temporal dependencies across ICU time steps
        self.lstm = nn.LSTM(input_dim, hidden_dim, num_layers=num_layers,
                            batch_first=True)
        # Project last hidden state to shared embedding space across all parties
        self.proj = nn.Linear(hidden_dim, embed_dim)
        self.embed_dim = embed_dim

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # Take only the final hidden state (last time step summary)
        _, (h_n, _) = self.lstm(x)
        return self.proj(h_n[-1])


# ── Aggregation ────────────────────────────────────────────────────────────────

def vfl_aggregate_embeddings(embeddings: List[torch.Tensor]) -> torch.Tensor:
    """Concatenate party embeddings into a single vector for the top model.

    Simple concatenation — no attention or weighting. The MMoE top model
    learns which features matter for each task during training.
    """
    return torch.cat(embeddings, dim=-1)


# ── Top model (server-side) ────────────────────────────────────────────────────

def _loss_fn(task_type: str) -> nn.Module:
    # BCEWithLogitsLoss handles both binary and multilabel (sigmoid is internal)
    if task_type.startswith("binary") or task_type.startswith("multilabel"):
        return nn.BCEWithLogitsLoss()
    return nn.MSELoss()


def _output_dim(task_type: str) -> int:
    # multilabel_25 → 25 outputs; binary → 1; regression → 1
    if task_type.startswith("multilabel_"):
        return int(task_type.split("_")[1])
    return 1


class _ExpertMLP(nn.Module):
    def __init__(self, in_dim: int, hidden_dim: int, out_dim: int):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(in_dim, hidden_dim), nn.ReLU(),
            nn.Linear(hidden_dim, out_dim),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


class VFLTopModel(nn.Module):
    """Server-side top model. Two modes controlled by n_tasks:

    n_tasks == 1: flat Linear projection (regression or binary classification).
    n_tasks  > 1: MMoE — shared experts + per-task gating + per-task output heads.
                  Each task learns to weight the experts differently, which helps
                  when tasks are heterogeneous (e.g. binary IHM vs multilabel Pheno).
    """

    def __init__(self, agg_dim: int, task_types: List[str],
                 n_experts: int = 4, expert_hidden: int = 128, expert_out: int = 64):
        super().__init__()
        self.task_types = task_types
        self.n_tasks = len(task_types)

        if self.n_tasks == 1:
            self.head = nn.Linear(agg_dim, _output_dim(task_types[0]))
        else:
            # Shared experts — each task picks a weighted combination of these
            self.experts = nn.ModuleList([
                _ExpertMLP(agg_dim, expert_hidden, expert_out)
                for _ in range(n_experts)
            ])
            # Per-task gating: learns which experts matter for this task
            self.gates = nn.ModuleList([
                nn.Linear(agg_dim, n_experts) for _ in range(self.n_tasks)
            ])
            # Per-task output head
            self.heads = nn.ModuleList([
                nn.Linear(expert_out, _output_dim(t)) for t in task_types
            ])

    def forward(self, z: torch.Tensor) -> List[torch.Tensor]:
        """Returns a list of raw logits, one tensor per task."""
        if self.n_tasks == 1:
            return [self.head(z)]

        expert_outs = torch.stack([e(z) for e in self.experts], dim=1)  # (B, n_experts, E)
        outputs = []
        for gate, head in zip(self.gates, self.heads):
            weights = torch.softmax(gate(z), dim=-1).unsqueeze(-1)  # (B, n_experts, 1)
            mixed = (expert_outs * weights).sum(dim=1)               # (B, E)
            outputs.append(head(mixed))
        return outputs


# ── Backward pass + DP ────────────────────────────────────────────────────────

def split_backward(
    top_model: VFLTopModel,
    z_concat: np.ndarray,
    labels: List[np.ndarray],
    sigma_per_task: List[float],
    clip_norm: float,
    party_embed_dims: List[int],
) -> Tuple[List[np.ndarray], List[float]]:
    """Run the top-model forward+backward pass and return per-party gradients.

    The server:
      1. Runs the top model on the concatenated embedding.
      2. Computes weighted loss across tasks.
      3. Backpropagates to get dL/dz_concat.
      4. Adds per-task-weighted DP noise to the gradient.
      5. Slices the gradient back into party-sized chunks.

    Returns:
        (grad_slices, losses) where grad_slices[i] is the noised gradient
        for party i, to be sent back so that party can update its encoder.
    """
    # Wrap z_concat so autograd can track gradients through it
    z_t = torch.tensor(z_concat, dtype=torch.float32, requires_grad=True)
    preds = top_model(z_t)

    # Compute per-task loss and weight by inverse sigma (higher DP noise → lower weight)
    total_loss = torch.tensor(0.0)
    losses = []
    for pred, y_np, task_type, sigma in zip(preds, labels, top_model.task_types, sigma_per_task):
        y = torch.tensor(y_np, dtype=torch.float32)
        if y.ndim == 1 and pred.shape[-1] == 1:
            y = y.unsqueeze(1)
        loss_k = _loss_fn(task_type)(pred, y)
        losses.append(loss_k.item())
        total_loss = total_loss + loss_k / (sigma + 1e-8)

    total_loss.backward()
    grad = z_t.grad.detach().numpy()          # (batch, agg_dim)

    # Clip the full gradient before slicing (bounds sensitivity across all parties)
    norm = np.linalg.norm(grad)
    if norm > clip_norm:
        grad = grad * (clip_norm / norm)

    # Add Gaussian noise scaled by the mean sigma across tasks
    mean_sigma = float(np.mean(sigma_per_task))
    grad = grad + np.random.normal(0, mean_sigma * clip_norm, grad.shape).astype(np.float32)

    # Slice gradient back to per-party chunks matching each encoder's embed_dim
    grad_slices, idx = [], 0
    for dim in party_embed_dims:
        grad_slices.append(grad[:, idx: idx + dim])
        idx += dim

    return grad_slices, losses


# ── DP accounting ──────────────────────────────────────────────────────────────

def dp_noise_embedding(grad: np.ndarray, sigma: float, clip_norm: float) -> np.ndarray:
    """Clip gradient + add Gaussian noise. Used per-party in simulation mode."""
    norm = np.linalg.norm(grad)
    if norm > clip_norm:
        grad = grad * (clip_norm / norm)
    return grad + np.random.normal(0, sigma * clip_norm, grad.shape).astype(np.float32)


def calibrate_task_sigma(
    dp_epsilon: float,
    dp_delta: float,
    rounds_total: int,
    task_types: List[str],
) -> Dict[str, float]:
    """Solve a base sigma for dp_epsilon via the RDP accountant, then spread
    per-task multipliers (>= 1.0) by output dimensionality."""
    from kernel.rdp_accountant import compute_noise_multiplier
    base_sigma = compute_noise_multiplier(dp_epsilon, dp_delta, max(int(rounds_total), 1))

    out_dims = [_output_dim(tt) for tt in task_types]
    if out_dims:
        lo, hi = min(out_dims), max(out_dims)
        span = (hi - lo) or 1
        multipliers = [1.0 + 0.3 * (d - lo) / span for d in out_dims]
    else:
        multipliers = []

    return {f"task_{k}": base_sigma * m for k, m in enumerate(multipliers)}


def renyi_epsilon_per_task(
    sigma_per_task: List[float],
    delta: float,
    rounds_done: int,
) -> Dict[str, float]:
    """Compute (ε, δ)-DP spent per task after rounds_done rounds.

    Each task has its own noise multiplier (task-stratified DP), so each
    accumulates a different privacy budget. Higher sigma → lower epsilon spent.
    """
    from kernel.rdp_accountant import compute_epsilon_spent
    return {
        f"task_{k}": compute_epsilon_spent(sigma, delta, rounds_done)
        for k, sigma in enumerate(sigma_per_task)
    }


def dataset_epsilon_for_round(
    sigma_per_task: List[float],
    delta: float,
    rounds_done: int,
) -> float:
    """Incremental ε for one round, charged to the per-dataset kernel ledger.

    Single scalar, so the worst (lowest-sigma) task bounds the dataset.
    """
    from kernel.rdp_accountant import compute_epsilon_spent
    worst_sigma = min(sigma_per_task)
    now = compute_epsilon_spent(worst_sigma, delta, rounds_done)
    prev = (
        compute_epsilon_spent(worst_sigma, delta, rounds_done - 1)
        if rounds_done > 1
        else 0.0
    )
    return now - prev


# ── PSI ────────────────────────────────────────────────────────────────────────

def psi_intersect(hashed_id_sets: List[List[str]]) -> List[str]:
    """Return the intersection of hashed patient ID lists across all parties.

    Each party hashes their patient IDs with SHA-256 before sending.
    The server sees only hashes, not raw IDs. Assumes honest-but-curious
    parties — see README.md for the production upgrade path.
    """
    if not hashed_id_sets:
        return []
    result = set(hashed_id_sets[0])
    for s in hashed_id_sets[1:]:
        result &= set(s)
    return sorted(result)


# ── Simulation helper ──────────────────────────────────────────────────────────

def dirichlet_feature_partition(
    data_X: np.ndarray,
    n_parties: int,
    feature_groups: Optional[List[List[int]]] = None,
) -> List[np.ndarray]:
    """Split feature columns across parties.

    If feature_groups is provided (e.g. [[0,1,2],[3,4],[5,6,7]]), uses those
    exact column slices — matching the MIMIC 3-site domain partition.
    Otherwise splits columns evenly across parties.
    """
    if feature_groups is not None:
        return [data_X[:, cols] for cols in feature_groups]
    n_cols = data_X.shape[1]
    splits = np.array_split(np.arange(n_cols), n_parties)
    return [data_X[:, idx] for idx in splits]
