"""
runner.py — FAIRDatabase adapter for the lifetime PBPK model.

Wraps simulate_scipy.PBPKModel and exposes a single `execute(params)` function
that the Flask blueprint can call. The heavy PBPKModel class (libsbml + scipy)
lives here unchanged from PBKFAIR; only the public interface is added below.

Dependencies (add to FAIRDatabase backend/requirements.txt):
    python-libsbml
    scipy
    numpy
    pandas
"""
from __future__ import annotations

import math
import os
import sys
from collections import deque
from typing import Any

import libsbml
import numpy as np
import pandas as pd
from scipy.integrate import solve_ivp

# ─────────────────────────────────────────────────────────────────────────────
# SBML path — relative to this file so it works wherever the package is placed.
# ─────────────────────────────────────────────────────────────────────────────
SBML_PATH = os.path.join(os.path.dirname(__file__), "lifetime_pbpk.xml")

# ─────────────────────────────────────────────────────────────────────────────
# Simulation defaults (match McSIM_input_breastfeeding_simulations.in)
# ─────────────────────────────────────────────────────────────────────────────
T_START = 0
T_END   = 3_561_120   # minutes ≈ 6.77 years
N_STEPS = 3562

DEFAULT_PARAMS: dict[str, float] = {
    "Abs":            1.0,
    "Free_no_pgcy":   0.02,
    "HalfLife":       2.5,
    "PC_blood_over_air": 1e99,
    "PC_ow":          0.0,
    "PC_0":  0.23, "PC_1":  0.58, "PC_2":  0.58, "PC_3":  0.08, "PC_4":  0.10,
    "PC_5":  0.58, "PC_6":  0.58, "PC_7":  0.10, "PC_8":  0.58, "PC_9":  0.22,
    "PC_10": 0.10, "PC_11": 0.58, "PC_12": 0.38, "PC_13": 0.58, "PC_14": 0.58,
    "PC_15": 0.63, "PC_16": 0.58, "PC_17": 0.58, "PC_18": 0.52, "PC_22": 1.0,
    "PC_26": 1.0,  "PC_27": 1.0,  "PC_29": 0.02,
    "PC_foetus_0":  0.23, "PC_foetus_1":  0.58, "PC_foetus_2":  0.58,
    "PC_foetus_3":  0.08, "PC_foetus_4":  0.10, "PC_foetus_5":  0.58,
    "PC_foetus_6":  0.58, "PC_foetus_7":  0.10, "PC_foetus_8":  0.58,
    "PC_foetus_9":  0.22, "PC_foetus_10": 0.10, "PC_foetus_11": 0.58,
    "PC_foetus_12": 0.38, "PC_foetus_13": 0.58, "PC_foetus_14": 0.58,
    "PC_foetus_15": 0.63, "PC_foetus_16": 0.58, "PC_foetus_17": 0.58,
    "PC_foetus_18": 0.52, "PC_foetus_22": 1.0,
    "K_PerMin": 0.0, "K_LPerMin": 0.0, "Km": 1.0, "Vmax_mp": 0.0,
    "Ka_stomach": 0.0, "Ka_gut": 0.0,
    "Ke_bile": 0.0, "Ke_renal_input": 0.0, "F_gut2faeces_input": 0.0,
    "Kd_pla2amniot": 0.0, "Kd_uter2pla_frac": 0.0,
    "Ka_amniot": 0.0, "Ke_gut_foetus": 0.0, "Ke_bile_foetus": 0.0,
    "mainCYP": 0.0, "Intake_var": 1.0,
    "Frac_Intake_Infant": 3.65, "Frac_Intake_Toddler": 3.80,
    "Frac_Intake_Children": 2.75, "Frac_Intake_Ado": 1.41,
    "DecreaseIntake_1": 0.20, "DecreaseIntake_2": 0.04,
    "BirthYear": 2007.0, "RateInj": 0.451695,
    "Gestation_StartAge_inYear": 0.0, "Gestation_Duration_inWeek": 0.0,
    "LactationTotal_Duration_inWeek": 0.0, "LactationPartial_Duration_inWeek": 0.0,
    "C_milk_input": 0.0, "C_inh": 0.0, "Q_ing_rate": 0.0,
}

DEFAULT_INITIAL_Q: dict[str, float] = {
    "Q_0":  4.85008, "Q_1":  0.05425, "Q_2":  0.43787, "Q_3":  0.56456,
    "Q_4":  0.0,     "Q_5":  0.10233, "Q_6":  0.28154, "Q_7":  0.72797,
    "Q_8":  0.02725, "Q_9":  0.01548, "Q_10": 0.21449, "Q_11": 0.06725,
    "Q_12": 0.00762, "Q_13": 0.02038, "Q_14": 0.17652, "Q_15": 0.25189,
    "Q_16": 0.53153, "Q_17": 0.06937, "Q_18": 0.83328,
    "Q_19": 0.0,     "Q_20": 0.0,
    "Q_art": 0.3309, "Q_ven": 0.99083,
}

# Pre-defined scenario labels and their breastfeeding durations (minutes).
SCENARIOS: list[dict] = [
    {"label": "no_bf",  "description": "No breastfeeding",   "StopBreastmilk_total": 0,          "LactationTotal_Duration_inWeek": 0},
    {"label": "bf_6mo", "description": "Breastfed 6 months", "StopBreastmilk_total": 262_800,    "LactationTotal_Duration_inWeek": 26},
    {"label": "bf_1yr", "description": "Breastfed 1 year",   "StopBreastmilk_total": 525_600,    "LactationTotal_Duration_inWeek": 52},
    {"label": "bf_3yr", "description": "Breastfed 3 years",  "StopBreastmilk_total": 1_576_800,  "LactationTotal_Duration_inWeek": 156},
]

OUTPUT_VARS = [
    "time", "Age", "BDW", "BodyWeight",
    "C_ven", "C_art", "C_milk", "C_milk_evol",
    "Q_ven", "Q_art",
    "Q_urine", "Q_feces", "Q_lact", "Q_met_liver", "Q_elim_plasma",
    "Free", "Hct", "RateInj_Lact", "PercentVar_intake",
]

# ─────────────────────────────────────────────────────────────────────────────
# SBML AST → Python expression string  (unchanged from simulate_scipy.py)
# ─────────────────────────────────────────────────────────────────────────────

_REL_OPS = {
    libsbml.AST_RELATIONAL_EQ:  "==",
    libsbml.AST_RELATIONAL_NEQ: "!=",
    libsbml.AST_RELATIONAL_LT:  "<",
    libsbml.AST_RELATIONAL_LEQ: "<=",
    libsbml.AST_RELATIONAL_GT:  ">",
    libsbml.AST_RELATIONAL_GEQ: ">=",
}


def _ast_to_py(node: libsbml.ASTNode) -> str:
    t  = node.getType()
    nc = node.getNumChildren()

    def ch(i: int) -> str:
        return _ast_to_py(node.getChild(i))

    if t == libsbml.AST_INTEGER:
        return str(node.getInteger())
    if t in (libsbml.AST_REAL, libsbml.AST_REAL_E):
        return repr(node.getReal())
    if t == libsbml.AST_NAME:
        return node.getName()
    if t == libsbml.AST_NAME_TIME:
        return "t"
    if t == libsbml.AST_PLUS:
        if nc == 1:
            return f"+({ch(0)})"
        return " + ".join(f"({ch(i)})" for i in range(nc))
    if t == libsbml.AST_MINUS:
        if nc == 1:
            return f"-({ch(0)})"
        return f"({ch(0)}) - ({ch(1)})"
    if t == libsbml.AST_TIMES:
        return " * ".join(f"({ch(i)})" for i in range(nc))
    if t == libsbml.AST_DIVIDE:
        return f"({ch(0)}) / ({ch(1)})"
    if t in (libsbml.AST_POWER, libsbml.AST_FUNCTION_POWER):
        return f"({ch(0)}) ** ({ch(1)})"
    if t == libsbml.AST_FUNCTION_EXP:
        return f"math.exp({ch(0)})"
    if t == libsbml.AST_FUNCTION_LN:
        return f"math.log({ch(0)})"
    if t == libsbml.AST_FUNCTION_LOG:
        if nc == 2:
            return f"math.log({ch(1)}, {ch(0)})"
        return f"math.log10({ch(0)})"
    if t == libsbml.AST_FUNCTION_ABS:
        return f"abs({ch(0)})"
    if t == libsbml.AST_FUNCTION_MAX:
        return f"max({', '.join(ch(i) for i in range(nc))})"
    if t == libsbml.AST_FUNCTION_MIN:
        return f"min({', '.join(ch(i) for i in range(nc))})"
    if t == libsbml.AST_FUNCTION_ROOT:
        if nc == 2:
            deg = node.getChild(0).getInteger()
            if deg == 2:
                return f"math.sqrt({ch(1)})"
            return f"({ch(1)}) ** (1.0 / ({ch(0)}))"
        return f"math.sqrt({ch(0)})"
    if t in _REL_OPS:
        return f"(({ch(0)}) {_REL_OPS[t]} ({ch(1)}))"
    if t == libsbml.AST_LOGICAL_AND:
        return "(" + " and ".join(f"({ch(i)})" for i in range(nc)) + ")"
    if t == libsbml.AST_LOGICAL_OR:
        return "(" + " or ".join(f"({ch(i)})" for i in range(nc)) + ")"
    if t == libsbml.AST_LOGICAL_NOT:
        return f"(not ({ch(0)}))"
    if t == libsbml.AST_FUNCTION_PIECEWISE:
        n_pairs = nc // 2
        has_otherwise = (nc % 2 == 1)
        default = ch(nc - 1) if has_otherwise else "0.0"
        result = default
        for i in range(n_pairs - 1, -1, -1):
            val  = ch(2 * i)
            cond = ch(2 * i + 1)
            result = f"(({val}) if ({cond}) else ({result}))"
        return result
    name = node.getName()
    if name:
        raise ValueError(f"Unhandled SBML function: {name!r} (AST type {t})")
    raise ValueError(f"Unhandled AST node type {t}")


# ─────────────────────────────────────────────────────────────────────────────
# PBPKModel — SBML loader + scipy integrator  (from simulate_scipy.py)
# ─────────────────────────────────────────────────────────────────────────────

class PBPKModel:
    """
    Parses lifetime_pbpk.xml, translates all SBML rules to Python code,
    and integrates with scipy LSODA. Identical to simulate_scipy.PBPKModel.
    """

    def __init__(self, sbml_path: str = SBML_PATH):
        reader = libsbml.SBMLReader()
        doc    = reader.readSBMLFromFile(sbml_path)
        for i in range(doc.getNumErrors()):
            e = doc.getError(i)
            if e.getSeverity() >= libsbml.LIBSBML_SEV_ERROR:
                raise RuntimeError(f"SBML parse error: {e.getMessage()}")
        self.model = doc.getModel()
        self._parse()
        self._compile()

    def _parse(self):
        import re
        m = self.model

        self.const_params: dict[str, float] = {}
        for i in range(m.getNumParameters()):
            p = m.getParameter(i)
            if p.getConstant():
                self.const_params[p.getId()] = p.getValue()

        self._nonconst_defaults: dict[str, float] = {}
        for i in range(m.getNumParameters()):
            p = m.getParameter(i)
            if not p.getConstant():
                self._nonconst_defaults[p.getId()] = p.getValue()

        self.species_ids: list[str] = []
        self.species_init: dict[str, float] = {}
        for i in range(m.getNumSpecies()):
            s = m.getSpecies(i)
            sid = s.getId()
            self.species_ids.append(sid)
            self.species_init[sid] = s.getInitialAmount()

        assign_exprs: dict[str, str] = {}
        assign_docorder: list[str]   = []
        self.rate_rules: dict[str, str] = {}

        for i in range(m.getNumRules()):
            rule = m.getRule(i)
            var  = rule.getVariable()
            expr = _ast_to_py(rule.getMath())
            if rule.isAssignment():
                assign_exprs[var] = expr
                assign_docorder.append(var)
            elif rule.isRate():
                self.rate_rules[var] = expr

        _ID = re.compile(r'\b([A-Za-z_][A-Za-z0-9_]*)\b')
        assign_var_set = set(assign_docorder)
        deps: dict[str, set[str]] = {}
        for v in assign_var_set:
            refs = {tok for tok in _ID.findall(assign_exprs[v])
                    if tok in assign_var_set and tok != v}
            deps[v] = refs

        in_degree: dict[str, int] = {v: 0 for v in assign_var_set}
        rev: dict[str, list[str]] = {v: [] for v in assign_var_set}
        for v, d_set in deps.items():
            for d in d_set:
                in_degree[v] += 1
                rev[d].append(v)

        queue = deque(v for v in assign_var_set if in_degree[v] == 0)
        topo: list[str] = []
        while queue:
            v = queue.popleft()
            topo.append(v)
            for u in rev[v]:
                in_degree[u] -= 1
                if in_degree[u] == 0:
                    queue.append(u)

        if len(topo) != len(assign_var_set):
            topo = assign_docorder

        self.assign_rules: list[tuple[str, str]] = [(v, assign_exprs[v]) for v in topo]
        self._assign_var_set = assign_var_set

    def _gen_prelude(self, indent: str) -> list[str]:
        I = indent
        lines: list[str] = []
        for idx, sid in enumerate(self.species_ids):
            lines.append(f"{I}{sid} = y[{idx}]")
        lines.append(f"{I}# params")
        for pid in sorted(self.const_params):
            lines.append(f"{I}{pid} = _p.get('{pid}', {repr(self.const_params[pid])})")
        assigned_vars = self._assign_var_set
        for pid, val in self._nonconst_defaults.items():
            if pid not in assigned_vars:
                lines.append(f"{I}{pid} = {repr(val)}")
        lines.append(f"{I}# assignment rules")
        for var, expr in self.assign_rules:
            lines.append(f"{I}{var} = {expr}")
        return lines

    def _compile(self):
        I = "    "
        rhs_lines = ["def _rhs(t, y, _p):"]
        rhs_lines += self._gen_prelude(I)
        rhs_lines.append(f"{I}# derivatives")
        deriv_names: list[str] = []
        for sid in self.species_ids:
            dname = f"_d_{sid}"
            expr  = self.rate_rules.get(sid, "0.0")
            rhs_lines.append(f"{I}{dname} = {expr}")
            deriv_names.append(dname)
        rhs_lines.append(f"{I}return [{', '.join(deriv_names)}]")

        state_lines = ["def _state(t, y, _p):"]
        state_lines += self._gen_prelude(I)
        all_vars = (["t"] + list(self.species_ids)
                    + [v for v, _ in self.assign_rules])
        seen: set[str] = set()
        unique_vars: list[str] = []
        for v in all_vars:
            if v not in seen:
                unique_vars.append(v)
                seen.add(v)
        dict_entries = ", ".join(f"'{v}': {v}" for v in unique_vars)
        state_lines.append(f"{I}return {{{dict_entries}}}")

        globs = {"math": math, "__builtins__": __builtins__}
        exec(compile("\n".join(rhs_lines),   "<pbpk_rhs>",   "exec"), globs)
        exec(compile("\n".join(state_lines), "<pbpk_state>", "exec"), globs)
        self._rhs_fn   = globs["_rhs"]
        self._state_fn = globs["_state"]

    def make_params(self, *overrides: dict) -> dict:
        p = dict(self.const_params)
        for d in overrides:
            p.update(d)
        return p

    def make_y0(self, override: dict | None = None) -> np.ndarray:
        y0 = np.array([self.species_init[sid] for sid in self.species_ids], dtype=float)
        if override:
            for sid, val in override.items():
                if sid in self.species_ids:
                    y0[self.species_ids.index(sid)] = val
        return y0

    def simulate(self, params: dict, y0: np.ndarray,
                 t_eval: np.ndarray) -> pd.DataFrame:
        result = solve_ivp(
            fun      = lambda t, y: self._rhs_fn(t, y, params),
            t_span   = (t_eval[0], t_eval[-1]),
            y0       = y0,
            method   = "LSODA",
            t_eval   = t_eval,
            rtol     = 1e-6,
            atol     = 1e-9,
            dense_output = False,
        )
        if not result.success:
            raise RuntimeError(f"ODE solver failed: {result.message}")

        rows: list[dict] = []
        for i, ti in enumerate(result.t):
            yi = result.y[:, i]
            rows.append(self._state_fn(ti, yi, params))

        df = pd.DataFrame(rows)
        df.rename(columns={"t": "time"}, inplace=True)
        return df


# Module-level singleton so Flask doesn't reload the model on every request.
_model: PBPKModel | None = None


def _get_model() -> PBPKModel:
    global _model
    if _model is None:
        _model = PBPKModel(SBML_PATH)
    return _model


# ─────────────────────────────────────────────────────────────────────────────
# Public API consumed by the Flask blueprint
# ─────────────────────────────────────────────────────────────────────────────

def execute(user_params: dict[str, Any]) -> dict:
    """
    Run one breastfeeding scenario and return a summary dict.

    Accepted keys in user_params:
        scenario     (str)   — one of: no_bf, bf_6mo, bf_1yr, bf_3yr
                               OR a numeric StopBreastmilk_total (minutes)
        StopBreastmilk_total (float) — override directly
        HalfLife     (float) — chemical half-life in years (default 2.5)
        RateInj      (float) — dietary intake rate ng/kg/min (default 0.451695)
        BirthYear    (float) — birth year (default 2007)
        n_steps      (int)   — output resolution (default 3562)

    Returns a dict:
        scenario       — label used
        n_rows         — number of time points
        t_end_min      — last simulated time (minutes)
        peak_C_ven     — peak venous PFAS concentration (mg/L)
        peak_Age_yr    — age at peak (years)
        final_C_ven    — venous concentration at end of simulation
        final_Age_yr   — age at end of simulation
        timeseries     — list of dicts [{time, Age, C_ven, BDW, ...}, ...]
                         (downsampled to at most 500 points for API responses)
    """
    mdl = _get_model()

    # Resolve scenario label → all scenario parameters
    scenario_label = user_params.get("scenario", "no_bf")
    scenario_entry = next((s for s in SCENARIOS if s["label"] == scenario_label), {})
    scenario_overrides = {k: float(v) for k, v in scenario_entry.items()
                          if k not in ("label", "description")}

    n_steps = int(user_params.get("n_steps", N_STEPS))
    t_eval  = np.linspace(T_START, T_END, n_steps)

    # Build parameter dict: SBML defaults → PFOA defaults → user overrides
    override_keys = {"HalfLife", "RateInj", "BirthYear", "C_milk_input",
                     "Frac_Intake_Infant", "Frac_Intake_Toddler"}
    user_chemical = {k: float(v) for k, v in user_params.items()
                     if k in override_keys}

    params = mdl.make_params(DEFAULT_PARAMS, user_chemical, scenario_overrides)
    y0     = mdl.make_y0(DEFAULT_INITIAL_Q)

    df = mdl.simulate(params, y0, t_eval)

    # Keep only available output columns
    cols = ["time"] + [c for c in OUTPUT_VARS if c in df.columns and c != "time"]
    df_out = df[cols]

    # Summary statistics
    c_ven_col = "C_ven" if "C_ven" in df_out.columns else None
    age_col   = "Age"   if "Age"   in df_out.columns else None

    peak_C_ven = peak_Age_yr = final_C_ven = final_Age_yr = None
    if c_ven_col:
        idx_peak   = df_out[c_ven_col].idxmax()
        peak_C_ven = float(df_out[c_ven_col].iloc[idx_peak])
        final_C_ven = float(df_out[c_ven_col].iloc[-1])
    if age_col:
        peak_Age_yr  = float(df_out[age_col].iloc[idx_peak]) if c_ven_col else None
        final_Age_yr = float(df_out[age_col].iloc[-1])

    # Downsample timeseries for JSON response (keep at most 500 rows)
    step = max(1, len(df_out) // 500)
    ts = df_out.iloc[::step].to_dict(orient="records")

    return {
        "scenario":     scenario_label,
        "n_rows":       len(df_out),
        "t_end_min":    float(df_out["time"].iloc[-1]),
        "peak_C_ven":   peak_C_ven,
        "peak_Age_yr":  peak_Age_yr,
        "final_C_ven":  final_C_ven,
        "final_Age_yr": final_Age_yr,
        "timeseries":   ts,
    }
