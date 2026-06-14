"""
runner.py — FAIRDatabase adapter for the Generic PFAS PBPK model.

Wraps the Generic PFAS PBPK (GW0 → 12 yr, pregnancy + child) and exposes:

    execute(user_params: dict) -> dict       ← FAIRDatabase interface
    simulate(compound, scenario, ...) -> df  ← direct scientific interface

Compounds: PFOA, PFOS
Scenarios: no_bf, bf_6mo, bf_1yr, bf_2yr

Dependencies (add to FAIRDatabase backend/requirements.txt):
    python-libsbml
    scipy
    numpy
    pandas
"""
from __future__ import annotations

import math
import os
from typing import Any

import libsbml
import numpy as np
import pandas as pd
from scipy.integrate import solve_ivp

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────
H_PER_YEAR  = 8_766.0                          # hours per year
T_DELIVERY  = 6_720.0                          # hours (GW40 = 280 d)
T_MAX_CHILD = 12 * H_PER_YEAR                  # 12-yr child endpoint

SBML_PATH = os.path.join(os.path.dirname(__file__), "GenericPBKFAIR.xml")

# ─────────────────────────────────────────────────────────────────────────────
# Compound base parameters
# ─────────────────────────────────────────────────────────────────────────────
# kelim_child = ln(2) / (HalfLife_yr * H_PER_YEAR) — Ratier 2024: PFOA 2.5 yr, PFOS 4.1 yr
# milk_fplas_frac derived analytically from steady-state mass balance (Ratier 2024 parameters):
#   PFOA: FreeF=0.02, PL=1.03, PK=1.17, Pbr=0.17, PRF=0.04 → 1/(1+121.7) ≈ 0.00815
#   PFOS: FreeF=0.025, PL=2.67, PK=1.26, Pbr=0.26, PRF=0.04 → 1/(1+169.0) ≈ 0.00588
# These are now PFOA_milk_fplas_frac / PFOS_milk_fplas_frac constants in the SBML,
# with milk_fplas_frac computed by a compound-selector assignment rule (mirrors Pmar),
# so no runtime override is needed here.
#
# CVINIT defaults correspond to post-phase-out (2015+) European general-population
# geometric means: PFOA ~0.34 µg/L, PFOS ~3.14 µg/L (HBM4EU, EFSA 2020 background data).
# These are lower than pre-2010 values used in Verner 2015 (PFOA ~2.53 µg/L).
from plugins.pbpk.params import (
    CVINIT as _CVINIT, MILK_PLASMA_RATIO as _MPR, GENERIC_PC as _GPC,
)
PFOA_PARAMS: dict[str, float] = {
    "PFOA": 1.0, "PFOS": 0.0, "CVINIT": _CVINIT["PFOA"],
    "kelim_child": math.log(2) / (2.5 * H_PER_YEAR),
}
PFOS_PARAMS: dict[str, float] = {
    "PFOA": 0.0, "PFOS": 1.0, "CVINIT": _CVINIT["PFOS"],
    "kelim_child": math.log(2) / (4.1 * H_PER_YEAR),
}

# ─────────────────────────────────────────────────────────────────────────────
# Breastfeeding scenarios
# ─────────────────────────────────────────────────────────────────────────────
# C_milk_input is intentionally absent from the BF scenarios below; it is
# calculated dynamically in simulate() from CVINIT × compound-specific
# milk:plasma ratio (see MILK_PLASMA_RATIO constants).  A fixed value of
# 0.00028 mg/L was used previously but that implied a milk:plasma ratio of
# ~0.82 against CVINIT=0.00034 mg/L — far above literature values of 0.01–0.05
# (Haug et al. 2011, Mondal et al. 2014).  Users may still override
# C_milk_input explicitly via **params.
_BF_SCENARIOS: dict[str, dict] = {
    "no_bf":  {"T_lact_end": T_DELIVERY,                  "C_milk_input": 0.0},
    "bf_6mo": {"T_lact_end": T_DELIVERY + H_PER_YEAR / 2},
    "bf_1yr": {"T_lact_end": T_DELIVERY + H_PER_YEAR},
    "bf_2yr": {"T_lact_end": T_DELIVERY + 2 * H_PER_YEAR},
}

# Milk:plasma partition ratios used to derive C_milk_input from maternal CVINIT.
# Sources: Haug et al. (2011) Environ Int; Mondal et al. (2014) Environ Health Perspect.
# PFOA: 0.020 (range 0.01–0.05); PFOS: 0.040 (range 0.02–0.08).
PFOA_MILK_PLASMA_RATIO: float = _MPR["PFOA"]
PFOS_MILK_PLASMA_RATIO: float = _MPR["PFOS"]

SCENARIOS: list[dict] = [
    {"label": "no_bf",  "description": "No breastfeeding"},
    {"label": "bf_6mo", "description": "Breastfed 6 months"},
    {"label": "bf_1yr", "description": "Breastfed 1 year"},
    {"label": "bf_2yr", "description": "Breastfed 2 years"},
]

COMPOUNDS: list[dict] = [
    {"label": "PFOA", "description": "Perfluorooctanoic acid (PFOA)"},
    {"label": "PFOS", "description": "Perfluorooctane sulfonic acid (PFOS)"},
]

# Standard output columns returned by simulate()
EXECUTE_COLS = [
    "time_h", "is_preg", "age_child_yr", "BW_kg",
    "CA_maternal_mgL", "CA_fetal_mgL",
    "A_urine_mg", "A_milk_mg", "A_met_L_mg", "A_feces_mg",
]

# ─────────────────────────────────────────────────────────────────────────────
# Unit conversion
# ─────────────────────────────────────────────────────────────────────────────
# Molecular weights (g/mol)
# PFOA: free acid C₈F₁₅O₂H = 414.07 g/mol ✓
# PFOS: free acid C₈F₁₇SO₃H = 500.13 g/mol.
#   Using the potassium-salt MW (538.22) would underestimate molar concentration
#   by ~7.6 %; EU/US biomonitoring programs report PFOS as the free-acid form.
_MW: dict[str, float] = {"PFOA": 414.07, "PFOS": 500.13}

SUPPORTED_UNITS = ("mg_L", "ug_L", "ng_mL", "nmol_L")


def convert_concentration(value, to_unit: str, compound: str | None = None):
    """Convert concentration from native mg/L to another unit.

    Parameters
    ----------
    value : float or array-like
        Concentration in mg/L.
    to_unit : str
        One of 'mg_L', 'ug_L' (= ng/mL), 'ng_mL', 'nmol_L'.
    compound : str, optional
        'PFOA' or 'PFOS' — required for 'nmol_L'.

    Returns
    -------
    Same type as *value* (float or numpy array).
    """
    if to_unit == "mg_L":
        return value
    if to_unit in ("ug_L", "ng_mL"):
        return value * 1_000.0
    if to_unit == "nmol_L":
        if compound is None:
            raise ValueError("compound='PFOA' or 'PFOS' is required for nmol_L conversion.")
        mw = _MW.get(compound.upper())
        if mw is None:
            raise ValueError(f"Unknown compound '{compound}'. Known: {list(_MW)}")
        # 1 mg/L = 1e6 / MW nmol/L  (MW in g/mol)
        return value * 1_000_000.0 / mw
    raise ValueError(f"Unknown unit '{to_unit}'. Supported: {SUPPORTED_UNITS}")


# ─────────────────────────────────────────────────────────────────────────────
# SBML formula helpers
# ─────────────────────────────────────────────────────────────────────────────

def _piecewise(*args):
    """SBML L3 piecewise(val1, cond1, val2, cond2, ..., default)."""
    n = len(args)
    for i in range(0, n - 1, 2):
        if args[i + 1]:
            return args[i]
    if n % 2 == 1:
        return args[-1]
    return 0.0


def _preprocess_formula(formula: str) -> str:
    formula = formula.replace("&&", " and ").replace("||", " or ")
    formula = formula.replace("^", "**")
    return formula


# ─────────────────────────────────────────────────────────────────────────────
# GenericModel — SBML loader + scipy LSODA integrator
# ─────────────────────────────────────────────────────────────────────────────

class GenericModel:
    """Parses generic_pfas_pbpk.xml and integrates with scipy LSODA."""

    def __init__(self, sbml_path: str = SBML_PATH):
        reader = libsbml.SBMLReader()
        doc    = reader.readSBMLFromFile(sbml_path)
        errs   = [doc.getError(i).getMessage()
                  for i in range(doc.getNumErrors())
                  if doc.getError(i).getSeverity() >= libsbml.LIBSBML_SEV_ERROR]
        if errs:
            raise RuntimeError(f"SBML parse error: {errs[0]}")
        self._model  = doc.getModel()
        self._params, self._assign_rules, self._rate_rules, self._species = self._parse()

    def _parse(self):
        m = self._model
        params = {m.getParameter(i).getId(): m.getParameter(i).getValue()
                  for i in range(m.getNumParameters())}
        species = [m.getSpecies(i).getId() for i in range(m.getNumSpecies())]
        assign_rules, rate_rules = {}, {}
        for i in range(m.getNumRules()):
            r = m.getRule(i)
            formula = _preprocess_formula(libsbml.formulaToL3String(r.getMath()))
            if r.getTypeCode() == libsbml.SBML_ASSIGNMENT_RULE:
                assign_rules[r.getVariable()] = formula
            elif r.getTypeCode() == libsbml.SBML_RATE_RULE:
                rate_rules[r.getVariable()] = formula
        return params, assign_rules, rate_rules, species

    def make_params(self, base: dict, overrides: dict) -> dict:
        p = dict(self._params)
        p.update(base)
        p.update(overrides)
        return p

    def make_y0(self, init: dict) -> np.ndarray:
        y0 = np.zeros(len(self._species))
        for i, sid in enumerate(self._species):
            y0[i] = init.get(sid, 0.0)
        return y0

    def simulate(self, params: dict, y0: np.ndarray, t_eval: np.ndarray) -> pd.DataFrame:
        assign_rules = self._assign_rules
        rate_rules   = self._rate_rules
        species      = self._species
        _math_ns = {
            "exp": math.exp, "log": math.log, "sqrt": math.sqrt,
            "abs": abs, "max": max, "min": min,
            "piecewise": _piecewise,
            "__builtins__": {},
        }

        def _eval_assigns(state: dict, t: float) -> dict:
            ns = dict(params)
            ns.update(state)
            ns["time"] = t
            ns.update(_math_ns)
            for _ in range(2):
                for var, formula in assign_rules.items():
                    try:
                        ns[var] = eval(formula, ns)   # noqa: S307
                    except Exception:
                        ns[var] = 0.0
            return ns

        def ode_rhs(t, y):
            state = dict(zip(species, y))
            ns    = _eval_assigns(state, t)
            dydt  = np.zeros(len(species))
            for i, sid in enumerate(species):
                if sid in rate_rules:
                    try:
                        dydt[i] = eval(rate_rules[sid], ns)   # noqa: S307
                    except Exception:
                        dydt[i] = 0.0
            return dydt

        res = solve_ivp(ode_rhs, (t_eval[0], t_eval[-1]), y0,
                        method="LSODA", t_eval=t_eval,
                        rtol=1e-6, atol=1e-9, dense_output=False)
        if not res.success:
            raise RuntimeError(f"ODE solver failed: {res.message}")

        rows = [{"time": res.t[i], **dict(zip(species, res.y[:, i]))}
                for i in range(len(res.t))]
        df = pd.DataFrame(rows)

        _extra = ["CA", "CA_f", "VFet", "BW", "BDW_child",
                  "is_preg", "is_lact", "age_child_yr", "Qplac"]
        for col in _extra:
            vals = []
            for i in range(len(res.t)):
                state = dict(zip(species, res.y[:, i]))
                ns = _eval_assigns(state, res.t[i])
                vals.append(ns.get(col, 0.0))
            df[col] = vals

        return df


# Module-level singleton — avoids re-parsing SBML on every Flask request.
_model: GenericModel | None = None


def _get_model() -> GenericModel:
    global _model
    if _model is None:
        _model = GenericModel(SBML_PATH)
    return _model


# ─────────────────────────────────────────────────────────────────────────────
# Internal: standardise raw simulation output to canonical 10-column DataFrame
# ─────────────────────────────────────────────────────────────────────────────

def _standardize(df: pd.DataFrame) -> pd.DataFrame:
    out = df.rename(columns={
        "time":    "time_h",
        "BW":      "BW_kg",
        "CA":      "CA_maternal_mgL",
        "CA_f":    "CA_fetal_mgL",
        "A_urine": "A_urine_mg",
        "A_milk":  "A_milk_mg",
        "A_met_L": "A_met_L_mg",
        "A_feces": "A_feces_mg",
    })
    for c in EXECUTE_COLS:
        if c not in out.columns:
            out[c] = 0.0
    return out[EXECUTE_COLS]


# ─────────────────────────────────────────────────────────────────────────────
# simulate() — direct scientific API (returns DataFrame)
# ─────────────────────────────────────────────────────────────────────────────

def simulate(
    compound: str = "PFOA",
    scenario: str = "no_bf",
    t_end_h: float = T_DELIVERY + 2 * H_PER_YEAR,
    n_pts: int = 500,
    **params,
) -> pd.DataFrame:
    """Run the Generic PFAS PBPK simulation.

    Parameters
    ----------
    compound : {'PFOA', 'PFOS'}
    scenario : {'no_bf', 'bf_6mo', 'bf_1yr', 'bf_2yr'}
    t_end_h  : float — simulation end time in hours
    n_pts    : int   — number of output time points
    **params : additional parameter overrides (e.g. Ratio_GFR=1.3)

    Returns
    -------
    pd.DataFrame  (n_pts rows × 10 columns, see EXECUTE_COLS)
    """
    if compound.upper() not in ("PFOA", "PFOS"):
        raise ValueError(f"compound must be 'PFOA' or 'PFOS', got {compound!r}")
    if scenario not in _BF_SCENARIOS:
        raise ValueError(f"Unknown scenario {scenario!r}. "
                         f"Choose from {list(_BF_SCENARIOS)}")

    mdl  = _get_model()
    base = PFOA_PARAMS if compound.upper() == "PFOA" else PFOS_PARAMS
    overrides = dict(_BF_SCENARIOS[scenario])

    # Derive C_milk_input from maternal CVINIT unless the scenario fixes it to
    # zero (no_bf) or the caller explicitly overrides it.
    if "C_milk_input" not in overrides and "C_milk_input" not in params:
        ratio = (PFOA_MILK_PLASMA_RATIO if compound.upper() == "PFOA"
                 else PFOS_MILK_PLASMA_RATIO)
        overrides["C_milk_input"] = base["CVINIT"] * ratio

    overrides.update(params)
    full_params = mdl.make_params(base, overrides)

    is_pfoa = full_params.get("PFOA", 1.0) > 0.5
    pfx     = "PFOA" if is_pfoa else "PFOS"
    ca0     = full_params["CVINIT"]
    bw0     = full_params.get("BWINIT", 70.0)
    fvp     = full_params.get("FVplas", 0.043)
    free_v  = full_params.get(f"{pfx}_Free", 0.020 if is_pfoa else 0.025)

    pcs = {
        "PL":   full_params.get(f"{pfx}_PL",   1.03  if is_pfoa else 2.67),
        "Pfat": full_params.get(f"{pfx}_Pfat",  0.47  if is_pfoa else 0.33),
        "Pbr":  full_params.get(f"{pfx}_Pbr",   0.17  if is_pfoa else 0.26),
        "Plg":  full_params.get(f"{pfx}_Plg",   1.27  if is_pfoa else 0.15),
        "PK":   full_params.get(f"{pfx}_PK",    1.17  if is_pfoa else 1.26),
        "Pmar": full_params.get(f"{pfx}_Pmar",  18.73 if is_pfoa else 0.11),
        "PG":   full_params.get(f"{pfx}_PG",    0.04  if is_pfoa else 0.04),
        "Pmam": full_params.get(f"{pfx}_Pmam",  0.04  if is_pfoa else 0.04),
        "Psk":  full_params.get(f"{pfx}_Psk",   0.10  if is_pfoa else 0.10),
        "PR":   full_params.get(f"{pfx}_PR",    0.04  if is_pfoa else 0.04),
    }

    vplas = fvp * bw0
    vl    = full_params.get("FVL",   0.026) * bw0
    vk    = full_params.get("FVK",   0.004) * bw0
    vg    = full_params.get("FVG",   0.016) * bw0
    vbr   = full_params.get("FVbr",  0.021) * bw0
    vlg   = full_params.get("FVlg",  0.014) * bw0
    vmar  = full_params.get("FVmar", 0.014) * bw0
    vsk   = full_params.get("FVsk",  0.039) * bw0
    vmam  = full_params.get("FVmam", 0.006) * bw0
    vfat  = full_params.get("FVfat", 0.214) * bw0
    vfil  = full_params.get("FVfil", 0.00044) * bw0
    vrest = bw0 - vplas - vl - vk - vg - vbr - vlg - vmar - vsk - vmam - vfat - vfil

    y0 = mdl.make_y0({
        "A_plas":   ca0 * vplas * free_v,
        "A_liver":  ca0 * pcs["PL"]   * vl,
        "A_kidney": ca0 * pcs["PK"]   * vk,
        "A_gut":    ca0 * pcs["PG"]   * vg,
        "A_brain":  ca0 * pcs["Pbr"]  * vbr,
        "A_lung":   ca0 * pcs["Plg"]  * vlg,
        "A_mar":    ca0 * pcs["Pmar"] * vmar,
        "A_skin":   ca0 * pcs["Psk"]  * vsk,
        "A_mam":    ca0 * pcs["Pmam"] * vmam,
        "A_fat":    ca0 * pcs["Pfat"] * vfat,
        "A_rest":   ca0 * pcs["PR"]   * max(vrest, 0.0),
    })

    t_eval = np.linspace(0.0, t_end_h, n_pts)
    df     = mdl.simulate(full_params, y0, t_eval)
    return _standardize(df)


# ─────────────────────────────────────────────────────────────────────────────
# execute() — FAIRDatabase interface (returns JSON-serialisable dict)
# ─────────────────────────────────────────────────────────────────────────────

def execute(user_params: dict[str, Any]) -> dict:
    """
    Run one Generic PFAS PBPK simulation and return a summary dict.

    Accepted keys in user_params:
        compound  (str)   — 'PFOA' or 'PFOS' (default 'PFOA')
        scenario  (str)   — no_bf | bf_6mo | bf_1yr | bf_2yr (default 'no_bf')
        t_end_h   (float) — simulation end time in hours
                            (default: delivery + 2 yr ≈ 24252 h)
        n_pts     (int)   — output resolution (default 500)
        Ratio_GFR (float) — optional GFR scaling factor

    Returns a dict:
        compound              — compound used
        scenario              — scenario used
        n_rows                — number of time points
        t_end_h               — last simulated time (hours)
        peak_CA_maternal_mgL  — peak maternal venous PFAS (mg/L)
        peak_age_yr           — child age at maternal peak (years after birth)
        peak_CA_fetal_mgL     — peak fetal arterial PFAS (mg/L)
        final_CA_maternal_mgL — maternal concentration at end
        final_age_yr          — child age at simulation end
        timeseries            — list of dicts (≤500 rows)
    """
    compound = str(user_params.get("compound", "PFOA")).upper()
    scenario = str(user_params.get("scenario", "no_bf"))
    t_end_h  = float(user_params.get("t_end_h", T_DELIVERY + 2 * H_PER_YEAR))
    n_pts    = int(user_params.get("n_pts", 500))

    extra: dict[str, float] = {}
    for k in ("Ratio_GFR", "CVINIT"):
        if k in user_params:
            extra[k] = float(user_params[k])

    df = simulate(compound=compound, scenario=scenario,
                  t_end_h=t_end_h, n_pts=n_pts, **extra)

    mat_col = "CA_maternal_mgL"
    fet_col = "CA_fetal_mgL"
    age_col = "age_child_yr"

    idx_peak_mat = int(df[mat_col].idxmax())
    peak_CA_mat  = float(df[mat_col].iloc[idx_peak_mat])
    peak_age     = float(df[age_col].iloc[idx_peak_mat])
    peak_CA_fet  = float(df[fet_col].max())
    final_CA_mat = float(df[mat_col].iloc[-1])
    final_age    = float(df[age_col].iloc[-1])

    step = max(1, len(df) // 500)
    ts   = df.iloc[::step].to_dict(orient="records")

    return {
        "compound":              compound,
        "scenario":              scenario,
        "n_rows":                len(df),
        "t_end_h":               float(df["time_h"].iloc[-1]),
        "peak_CA_maternal_mgL":  peak_CA_mat,
        "peak_age_yr":           peak_age,
        "peak_CA_fetal_mgL":     peak_CA_fet,
        "final_CA_maternal_mgL": final_CA_mat,
        "final_age_yr":          final_age,
        "timeseries":            ts,
    }
