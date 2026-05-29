"""
helpers.py — thin bridge between the Flask routes and RatierPBKModel.

Keeps the routes file free of model-specific imports.
"""
from __future__ import annotations

import sys
import os

# Allow `from RatierPBKModel import execute` regardless of where FAIRDatabase
# is installed.  Assumes RatierPBKModel/ lives at the repo root (same level as
# backend/ and frontend/).
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../../"))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from RatierPBKModel import execute, SCENARIOS, DEFAULT_PARAMS  # noqa: E402


def run_scenario(user_params: dict) -> dict:
    """
    Validate basic inputs and delegate to runner.execute().

    Raises ValueError with a user-facing message on bad input.
    """
    valid_labels = {s["label"] for s in SCENARIOS}
    label = user_params.get("scenario", "no_bf")
    if label not in valid_labels:
        raise ValueError(
            f"Unknown scenario '{label}'. "
            f"Valid options: {sorted(valid_labels)}"
        )

    half_life = user_params.get("HalfLife")
    if half_life is not None and float(half_life) <= 0:
        raise ValueError("HalfLife must be positive.")

    return execute(user_params)


def available_scenarios() -> list[dict]:
    """Return scenario metadata for the UI dropdown."""
    return [
        {"label": s["label"], "description": s["description"]}
        for s in SCENARIOS
    ]
