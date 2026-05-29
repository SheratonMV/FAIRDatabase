"""
helpers.py — thin bridge between the Flask routes and GenericPBKModel.

Keeps the routes file free of model-specific imports.
"""
from __future__ import annotations

import sys
import os

# GenericPBKModel/ lives three directories above this file inside the fork:
#   Fork to FAIRDatabase/backend/src/generic_model/helpers.py
#   → ../../../  = Fork to FAIRDatabase/
_FORK_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
if _FORK_ROOT not in sys.path:
    sys.path.insert(0, _FORK_ROOT)

from GenericPBKModel import execute, SCENARIOS, COMPOUNDS  # noqa: E402


def run_scenario(user_params: dict) -> dict:
    """Validate inputs and delegate to GenericPBKModel.execute()."""
    valid_scenarios = {s["label"] for s in SCENARIOS}
    valid_compounds = {c["label"] for c in COMPOUNDS}

    scenario = user_params.get("scenario", "no_bf")
    compound = str(user_params.get("compound", "PFOA")).upper()

    if scenario not in valid_scenarios:
        raise ValueError(
            f"Unknown scenario '{scenario}'. "
            f"Valid options: {sorted(valid_scenarios)}"
        )
    if compound not in valid_compounds:
        raise ValueError(
            f"Unknown compound '{compound}'. "
            f"Valid options: {sorted(valid_compounds)}"
        )

    ratio_gfr = user_params.get("Ratio_GFR")
    if ratio_gfr is not None and float(ratio_gfr) <= 0:
        raise ValueError("Ratio_GFR must be positive.")

    return execute(user_params)


def available_scenarios() -> list[dict]:
    return [{"label": s["label"], "description": s["description"]} for s in SCENARIOS]


def available_compounds() -> list[dict]:
    return [{"label": c["label"], "description": c["description"]} for c in COMPOUNDS]
