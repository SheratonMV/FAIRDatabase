"""params.py — Single source of truth for all PBPK parameter ranges and defaults.

Edit this file to change any parameter default, min, max, step, or applicability-domain
boundary. Changes propagate automatically to:
  - Server-side validation (runners + helpers)
  - HTML input attributes (min/max/value/step)
  - JavaScript applicability-domain warnings
  - Sensitivity panel ranges in validation.html

Schema for each parameter entry:
    default   : default value sent to the solver
    min       : hard lower bound (HTML min + server clamp)
    max       : hard upper bound (HTML max + server clamp), None = no upper limit
    step      : HTML input step attribute ("any" for continuous)
    unit      : display unit string
    label     : human-readable label for UI and warnings
    domain_min: lower end of the calibrated applicability domain  (warn outside)
    domain_max: upper end of the calibrated applicability domain  (warn outside)
    description: tooltip / help text shown in the UI
"""
from __future__ import annotations
import math

# ── Shared physiological constants ────────────────────────────────────────────
# Used by multiple models — change here to synchronise.

CVINIT = {
    "PFOA": 0.00034,   # mg/L — initial plasma PFOA (Rovira 2019, HELIX median)
    "PFOS": 0.00314,   # mg/L — initial plasma PFOS
}

MILK_PLASMA_RATIO = {
    "PFOA": 0.020,     # dimensionless  (Verner 2016)
    "PFOS": 0.040,     # dimensionless
}

# ── Ratier 2024 — user-facing parameters ──────────────────────────────────────

RATIER: dict[str, dict] = {
    "HalfLife": {
        "default": 2.5,
        "min": 0.01,
        "max": None,
        "step": "any",
        "unit": "yr",
        "label": "Chemical half-life",
        "domain_min": 2.0,
        "domain_max": 5.0,
        "description": "Effective whole-body elimination half-life (years). "
                        "Calibrated range: 2–5 yr for PFOA in children.",
    },
    "RateInj": {
        "default": 0.451695,
        "min": 0.0,
        "max": None,
        "step": "any",
        "unit": "ng/kg/min",
        "label": "Dietary intake rate",
        "domain_min": 0.1,
        "domain_max": 2.0,
        "description": "Background dietary PFAS intake rate. "
                        "Calibrated range: 0.1–2.0 ng/kg/min.",
    },
    "BirthYear": {
        "default": 2007,
        "min": 1950,
        "max": 2050,
        "step": 1,
        "unit": "year",
        "label": "Birth year",
        "domain_min": 1990,
        "domain_max": 2020,
        "description": "Child's year of birth. Exposure time-trend is calibrated "
                        "for births 1990–2020.",
    },
    "C_milk_input": {
        "default": 0.0,
        "min": 0.0,
        "max": None,
        "step": "any",
        "unit": "ng/mL",
        "label": "Breast milk concentration",
        "domain_min": None,
        "domain_max": None,
        "description": "PFAS concentration in breast milk. 0 = use model estimate.",
    },
    "Frac_Intake_Infant": {
        "default": 3.65,
        "min": 0.1,
        "max": 20.0,
        "step": "any",
        "unit": "—",
        "label": "Infant intake multiplier",
        "domain_min": 1.0,
        "domain_max": 10.0,
        "description": "Age-specific dietary intake scaling factor for infants.",
    },
    "Frac_Intake_Toddler": {
        "default": 3.80,
        "min": 0.1,
        "max": 20.0,
        "step": "any",
        "unit": "—",
        "label": "Toddler intake multiplier",
        "domain_min": 1.0,
        "domain_max": 10.0,
        "description": "Age-specific dietary intake scaling factor for toddlers.",
    },
}

# ── Rovira 2019 — user-facing parameters ──────────────────────────────────────

ROVIRA: dict[str, dict] = {
    "BW0": {
        "default": 70.0,
        "min": 30.0,
        "max": 180.0,
        "step": 0.5,
        "unit": "kg",
        "label": "Pre-pregnancy weight",
        "domain_min": 45.0,
        "domain_max": 120.0,
        "description": "Maternal body weight before pregnancy. "
                        "INMA cohort calibration range: 45–120 kg.",
    },
    "BW_BIRTH": {
        "default": 3.3,
        "min": 1.5,
        "max": 6.0,
        "step": 0.1,
        "unit": "kg",
        "label": "Birth weight",
        "domain_min": 2.0,
        "domain_max": 5.0,
        "description": "Neonatal body weight at delivery.",
    },
    "CVINIT": {
        "default": None,          # None → use compound-specific CVINIT dict
        "min": 1e-6,
        "max": None,
        "step": "any",
        "unit": "mg/L",
        "label": "Initial plasma concentration",
        "domain_min": None,
        "domain_max": None,
        "description": "Initial maternal plasma PFAS concentration. "
                        "Leave blank to use Rovira 2019 compound defaults.",
    },
}

# ── Verner 2015 / Ouidir 2025 — Monte Carlo sampling bounds ──────────────────
# Each entry: (mean, sd, lo, hi) used in truncated-normal sampling.
# Bounds are from Verner 2015 Table 1 (mean ± 2 SD truncation).

VERNER_MC: dict[str, tuple] = {
    #  param        mean      sd       lo       hi
    "BWINIT":    (70.3,    14.3,    37.0,   134.0),
    "VLC":       (0.026,   0.004,   0.018,   0.034),
    "RATIO_GFR": (1.0,     0.246,   0.508,   1.492),
    "RESIDUAL":  (0.0,   441.0,  -882.0,   882.0),
    "PFOS_PL":   (3.720,   0.558,   2.604,   4.836),
    "PFOA_PL":   (2.200,   0.330,   1.540,   2.860),
    "PFOS_PR":   (0.200,   0.030,   0.140,   0.260),
    "PFOA_PR":   (0.120,   0.018,   0.084,   0.156),
    "PFOS_Free": (0.025,   0.004,   0.017,   0.033),
    "PFOA_Free": (0.020,   0.003,   0.014,   0.026),
    "PFOS_FreeF":(0.025,   0.004,   0.017,   0.033),
    "PFOA_FreeF":(0.020,   0.003,   0.014,   0.026),
    "PFOS_TMC":  (3.500,   0.525,   2.450,   4.550),
    "PFOA_TMC":  (10.00,   1.500,   7.000,  13.000),
    "PFOS_KT":   (0.023,   0.003,   0.017,   0.029),
    "PFOA_KT":   (0.055,   0.008,   0.039,   0.071),
    "CVINIT":    (None,    None,    1e-5,    1.0),   # mean/sd set per compound at runtime
}

VERNER_UI: dict[str, dict] = {
    "n_iter": {
        "default": 100,
        "min": 10,
        "max": 1000,
        "step": 10,
        "unit": "—",
        "label": "Monte Carlo iterations",
        "domain_min": None,
        "domain_max": None,
        "description": "Number of parameter draws. ≥500 for stable percentile bands; "
                        "≤200 for quick preview.",
    },
    "seed": {
        "default": 42,
        "min": 0,
        "max": None,
        "step": 1,
        "unit": "—",
        "label": "RNG seed",
        "domain_min": None,
        "domain_max": None,
        "description": "Random seed for reproducibility. Any non-negative integer.",
    },
}

# ── Generic — user-facing parameters ──────────────────────────────────────────

GENERIC: dict[str, dict] = {
    "Ratio_GFR": {
        "default": 1.0,
        "min": 0.01,
        "max": None,
        "step": "any",
        "unit": "—",
        "label": "GFR scaling factor",
        "domain_min": 0.5,
        "domain_max": 2.0,
        "description": "Scales the baseline glomerular filtration rate. "
                        "1.0 = population median; 0.5–2.0 calibrated range.",
    },
}

# ── Generic — tissue partition coefficients (PFOA / PFOS) ────────────────────

GENERIC_PC: dict[str, dict[str, float]] = {
    "PFOA": {
        "PL": 1.03, "Pfat": 0.47, "Pbr": 0.17, "Plg": 1.27,
        "PK": 1.17, "Pmar": 18.73, "PG": 0.04, "Pmam": 0.04,
        "Psk": 0.10, "PR": 0.04,
    },
    "PFOS": {
        "PL": 2.67, "Pfat": 0.33, "Pbr": 0.26, "Plg": 0.15,
        "PK": 1.26, "Pmar": 0.11, "PG": 0.04, "Pmam": 0.04,
        "Psk": 0.10, "PR": 0.04,
    },
}

# ── Helper — render HTML input attributes from a param spec ──────────────────

def input_attrs(spec: dict) -> str:
    """Return HTML attribute string for a numeric <input> from a param spec."""
    parts = []
    if spec.get("default") is not None:
        parts.append(f'value="{spec["default"]}"')
    if spec.get("min") is not None:
        parts.append(f'min="{spec["min"]}"')
    if spec.get("max") is not None:
        parts.append(f'max="{spec["max"]}"')
    step = spec.get("step", "any")
    parts.append(f'step="{step}"')
    return " ".join(parts)


def domain_js(study: str) -> str:
    """Return the JS DOMAIN object literal for applicability-domain warnings."""
    import json
    mapping = {"ratier": RATIER, "generic": GENERIC, "rovira": ROVIRA}
    specs = mapping.get(study, {})
    domain = {
        k: {"min": v["domain_min"], "max": v["domain_max"], "label": v["label"]}
        for k, v in specs.items()
        if v.get("domain_min") is not None or v.get("domain_max") is not None
    }
    return json.dumps(domain)
