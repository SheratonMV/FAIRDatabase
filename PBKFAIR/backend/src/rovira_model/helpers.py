"""
helpers.py — thin bridge between Flask routes and RoviraPBKModel.
"""
from __future__ import annotations

import sys
import os

# RoviraPBKModel/ lives three directories above this file:
#   Fork to FAIRDatabase/backend/src/rovira_model/helpers.py
#   → ../../../  = Fork to FAIRDatabase/
_FORK_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
if _FORK_ROOT not in sys.path:
    sys.path.insert(0, _FORK_ROOT)

from RoviraPBKModel import execute, COMPOUNDS  # noqa: E402


def run_scenario(user_params: dict) -> dict:
    """Validate inputs and delegate to RoviraPBKModel.execute()."""
    valid_compounds = {c["label"] for c in COMPOUNDS}
    compound = str(user_params.get("compound", "PFOA")).upper()
    if compound not in valid_compounds:
        raise ValueError(
            f"Unknown compound '{compound}'. "
            f"Valid options: {sorted(valid_compounds)}"
        )

    cvinit = user_params.get("CVINIT")
    if cvinit is not None and float(cvinit) <= 0:
        raise ValueError("CVINIT must be positive.")

    bw0 = user_params.get("BW0")
    if bw0 is not None and float(bw0) <= 0:
        raise ValueError("BW0 must be positive.")

    return execute(user_params)


def available_compounds() -> list[dict]:
    return [{"label": c["label"], "description": c["description"]} for c in COMPOUNDS]
