"""
helpers.py — thin bridge between Flask routes and VernerPBKModel.
"""
from __future__ import annotations

import sys
import os

# VernerPBKModel/ lives three directories above this file:
#   Fork to FAIRDatabase/backend/src/verner_model/helpers.py
#   → ../../../  = Fork to FAIRDatabase/
_FORK_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
if _FORK_ROOT not in sys.path:
    sys.path.insert(0, _FORK_ROOT)

from VernerPBKModel import execute, COMPOUNDS  # noqa: E402


def run_scenario(user_params: dict) -> dict:
    """Validate inputs and delegate to VernerPBKModel.execute()."""
    valid_compounds = {c["label"] for c in COMPOUNDS}
    compound = str(user_params.get("compound", "PFOA")).upper()
    if compound not in valid_compounds:
        raise ValueError(
            f"Unknown compound '{compound}'. "
            f"Valid options: {sorted(valid_compounds)}"
        )

    n_iter = user_params.get("n_iter")
    if n_iter is not None:
        n_iter = int(n_iter)
        if not (1 <= n_iter <= 1000):
            raise ValueError("n_iter must be between 1 and 1000.")
        user_params = dict(user_params, n_iter=n_iter)

    seed = user_params.get("seed")
    if seed is not None:
        user_params = dict(user_params, seed=int(seed))

    return execute(user_params)


def available_compounds() -> list[dict]:
    return [{"label": c["label"], "description": c["description"]} for c in COMPOUNDS]
