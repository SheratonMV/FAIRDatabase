"""
VernerPBKModel/runner.py — FAIRDatabase adapter for the Verner 2015 pregnancy PBPK.

Self-contained Monte Carlo runner (Verner 2015 Table 1 parameter distributions)
using the Ouidir SBML model. Lightweight variant with n_iter=100 default for web use.

Compounds: PFOA, PFOS
Output: monthly maternal plasma at gestational months 1–9, with percentile bands.
"""
from __future__ import annotations

import math
import os
import re
from collections import deque

import libsbml
import numpy as np
from scipy.integrate import solve_ivp
from scipy.stats import truncnorm

_HERE     = os.path.dirname(os.path.abspath(__file__))
SBML_PATH = os.path.join(_HERE, "Ouidir2025FAIR.xml")

T_END    = 6570.0
MONTH_H  = 730.0
T_MONTHS = [MONTH_H * m for m in range(1, 10)]   # months 1–9 in hours

COMPOUNDS = [
    {"label": "PFOA", "description": "PFOA (C8, Verner 2015 / Ouidir 2025)"},
    {"label": "PFOS", "description": "PFOS (C8-S, Verner 2015 / Ouidir 2025)"},
]

EXECUTE_COLS = [
    "month", "time_h", "CA_mean_mgL", "CA_p5_mgL", "CA_p25_mgL",
    "CA_p75_mgL", "CA_p95_mgL", "CA_f_mean_mgL",
]

# ─────────────────────────────────────────────────────────────────────────────
# Unit conversion
# ─────────────────────────────────────────────────────────────────────────────
# PFOS MW: free acid C₈F₁₇SO₃H = 500.13 g/mol (not the potassium salt 538.22 g/mol).
# Biomonitoring data (NHANES, HBM4EU) report PFOS as the free-acid form.
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
        return value * 1_000_000.0 / mw
    raise ValueError(f"Unknown unit '{to_unit}'. Supported: {SUPPORTED_UNITS}")


# Background concentration arithmetic means from Verner 2015 (pre-2010 North
# American / European cohort data): PFOA 2.53 µg/L, PFOS 13.02 µg/L.
# These are ~7–10× higher than the post-phase-out defaults used in the Generic
# and Rovira models (PFOA 0.34 µg/L, PFOS 3.14 µg/L).  The difference reflects
# different exposure eras, not a parameterisation error.
from plugins.pbpk.params import VERNER_MC as _VMC
_PFOA_AM_V, _PFOA_CV_V = 0.00253, 0.446   # mg/L, coefficient of variation
_PFOS_AM_V, _PFOS_CV_V = 0.01302, 0.368

# Verner 2015 birth-weight regression constants
_BW_INTERCEPT = 3376.0   # g
_BW_BETA      = 175.5    # g per GFR_ratio unit

# ─────────────────────────────────────────────────────────────────────────────
# SBML AST → Python expression  (identical to Verner_ouidir/runner.py)
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
        n_pairs    = nc // 2
        has_other  = (nc % 2 == 1)
        default    = ch(nc - 1) if has_other else "0.0"
        result     = default
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
# Verner / Ouidir PBPK model
# ─────────────────────────────────────────────────────────────────────────────

class VERNERModel:
    """Loads ouidir_human_pbpk.xml, compiles SBML rules, integrates with LSODA."""

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
        m = self.model
        self.const_params:        dict[str, float] = {}
        self._nonconst_defaults:  dict[str, float] = {}
        for i in range(m.getNumParameters()):
            p = m.getParameter(i)
            if p.getConstant():
                self.const_params[p.getId()] = p.getValue()
            else:
                self._nonconst_defaults[p.getId()] = p.getValue()

        self.species_ids:  list[str] = []
        self.species_init: dict[str, float] = {}
        for i in range(m.getNumSpecies()):
            s = m.getSpecies(i)
            sid = s.getId()
            self.species_ids.append(sid)
            self.species_init[sid] = s.getInitialAmount()

        self.initial_assignments: dict[str, str] = {}
        for i in range(m.getNumInitialAssignments()):
            ia = m.getInitialAssignment(i)
            self.initial_assignments[ia.getSymbol()] = _ast_to_py(ia.getMath())

        assign_exprs:  dict[str, str] = {}
        assign_order:  list[str]      = []
        self.rate_rules: dict[str, str] = {}
        for i in range(m.getNumRules()):
            rule = m.getRule(i)
            var  = rule.getVariable()
            expr = _ast_to_py(rule.getMath())
            if rule.isAssignment():
                assign_exprs[var] = expr
                assign_order.append(var)
            elif rule.isRate():
                self.rate_rules[var] = expr

        _ID          = re.compile(r'\b([A-Za-z_][A-Za-z0-9_]*)\b')
        av           = set(assign_order)
        deps         = {v: {tok for tok in _ID.findall(assign_exprs[v])
                            if tok in av and tok != v} for v in av}
        in_d         = {v: 0 for v in av}
        rev: dict[str, list[str]] = {v: [] for v in av}
        for v, ds in deps.items():
            for d in ds:
                in_d[v] += 1
                rev[d].append(v)
        q    = deque(v for v in av if in_d[v] == 0)
        topo: list[str] = []
        while q:
            v = q.popleft()
            topo.append(v)
            for u in rev[v]:
                in_d[u] -= 1
                if in_d[u] == 0:
                    q.append(u)
        self.assign_rules    = [(v, assign_exprs[v]) for v in (topo if len(topo) == len(av) else assign_order)]
        self._assign_var_set = av

    def _gen_prelude(self, indent: str) -> list[str]:
        I = indent
        lines: list[str] = []
        for idx, sid in enumerate(self.species_ids):
            lines.append(f"{I}{sid} = y[{idx}]")
        for pid in sorted(self.const_params):
            lines.append(f"{I}{pid} = _p.get('{pid}', {repr(self.const_params[pid])})")
        for pid, val in self._nonconst_defaults.items():
            if pid not in self._assign_var_set:
                lines.append(f"{I}{pid} = _p.get('{pid}', {repr(val)})")
        for var, expr in self.assign_rules:
            lines.append(f"{I}{var} = {expr}")
        return lines

    def _compile(self):
        I = "    "
        rhs = ["def _rhs(t, y, _p):"] + self._gen_prelude(I)
        dn: list[str] = []
        for sid in self.species_ids:
            dn.append(f"_d_{sid}")
            rhs.append(f"{I}_d_{sid} = {self.rate_rules.get(sid, '0.0')}")
        rhs.append(f"{I}return [{', '.join(dn)}]")

        state = ["def _state(t, y, _p):"] + self._gen_prelude(I)
        vs    = ["t"] + list(self.species_ids) + [v for v, _ in self.assign_rules]
        seen: set[str] = set()
        uv: list[str] = []
        for v in vs:
            if v not in seen:
                uv.append(v)
                seen.add(v)
        state.append(f"{I}return {{{', '.join(repr(v)+': '+v for v in uv)}}}")

        g = {"math": math, "__builtins__": __builtins__}
        exec(compile("\n".join(rhs),   "<verner_rhs>",   "exec"), g)
        exec(compile("\n".join(state), "<verner_state>", "exec"), g)
        self._rhs_fn   = g["_rhs"]
        self._state_fn = g["_state"]

    def _compute_y0(self, params: dict) -> np.ndarray:
        y_zeros = np.zeros(len(self.species_ids))
        state   = self._state_fn(0.0, y_zeros, params)
        eval_ns: dict = {}
        eval_ns.update(self.const_params)
        eval_ns.update(self._nonconst_defaults)
        eval_ns.update(params)
        eval_ns.update(state)
        y0 = np.zeros(len(self.species_ids))
        for i, sid in enumerate(self.species_ids):
            if sid in self.initial_assignments:
                try:
                    y0[i] = eval(self.initial_assignments[sid], {"math": math}, eval_ns)
                except Exception:
                    y0[i] = 0.0
            else:
                y0[i] = self.species_init.get(sid, 0.0)
        return y0

    def simulate(self, params: dict, t_record: list[float]) -> dict[float, dict] | None:
        t_eval = np.array(sorted(set(t_record)))
        y0     = self._compute_y0(params)
        try:
            result = solve_ivp(
                fun          = lambda t, y: self._rhs_fn(t, y, params),
                t_span       = (t_eval[0], t_eval[-1]),
                y0           = y0,
                method       = "LSODA",
                t_eval       = t_eval,
                rtol         = 1e-6,
                atol         = 1e-9,
                dense_output = False,
                max_step     = 24.0,
            )
        except Exception:
            return None
        if not result.success:
            return None
        return {float(ti): self._state_fn(ti, result.y[:, i], params)
                for i, ti in enumerate(result.t)}


_model: VERNERModel | None = None


def _get_model() -> VERNERModel:
    global _model
    if _model is None:
        _model = VERNERModel(SBML_PATH)
    return _model


# ─────────────────────────────────────────────────────────────────────────────
# Truncated-normal sampler
# ─────────────────────────────────────────────────────────────────────────────

def _tnorm(rng: np.random.Generator, mean: float, sd: float,
           lo: float, hi: float) -> float:
    a = (lo - mean) / sd
    b = (hi - mean) / sd
    return float(truncnorm.rvs(a, b, loc=mean, scale=sd, random_state=rng))


# ─────────────────────────────────────────────────────────────────────────────
# FAIRDatabase execute() API
# ─────────────────────────────────────────────────────────────────────────────

def execute(user_params: dict) -> dict:
    """Run Verner 2015 MC PBPK simulation for one PFAS compound.

    Parameters (in user_params)
    ---------------------------
    compound : str   — 'PFOA' or 'PFOS'  (default 'PFOA')
    n_iter   : int   — Monte Carlo iterations (default 100)
    seed     : int   — RNG seed (default 42)

    Returns
    -------
    dict with keys: compound, n_iter, n_rows, t_end_h,
        timeseries (9 rows, months 1–9) each containing:
        month, time_h, CA_mean_mgL, CA_p5_mgL, CA_p25_mgL,
        CA_p75_mgL, CA_p95_mgL, CA_f_mean_mgL
    """
    compound = str(user_params.get("compound", "PFOA")).upper()
    if compound not in ("PFOA", "PFOS"):
        raise ValueError(f"compound must be 'PFOA' or 'PFOS', got {compound!r}")
    n_iter = int(user_params.get("n_iter", 100))
    if n_iter < 1:
        raise ValueError("n_iter must be >= 1")
    seed = int(user_params.get("seed", 42))

    is_pfos = (compound == "PFOS")
    am = _PFOS_AM_V if is_pfos else _PFOA_AM_V
    cv = _PFOS_CV_V if is_pfos else _PFOA_CV_V

    mdl = _get_model()
    rng = np.random.default_rng(seed)

    ca_samples:   list[list[float]] = [[] for _ in range(9)]
    ca_f_samples: list[list[float]] = [[] for _ in range(9)]

    for _ in range(n_iter):
        # Sampling bounds from params.py::VERNER_MC — edit there to change ranges.
        def _v(k): return _VMC[k]
        BWINIT    = _tnorm(rng, *_v("BWINIT"))
        VLC       = _tnorm(rng, *_v("VLC"))
        RATIO_GFR = _tnorm(rng, *_v("RATIO_GFR"))
        RESIDUAL  = _tnorm(rng, *_v("RESIDUAL"))
        BW_g      = _BW_INTERCEPT + _BW_BETA * RATIO_GFR + RESIDUAL

        PFOS_PL    = _tnorm(rng, *_v("PFOS_PL"))
        PFOA_PL    = _tnorm(rng, *_v("PFOA_PL"))
        PFOS_PR    = _tnorm(rng, *_v("PFOS_PR"))
        PFOA_PR    = _tnorm(rng, *_v("PFOA_PR"))
        PFOS_Free  = _tnorm(rng, *_v("PFOS_Free"))
        PFOA_Free  = _tnorm(rng, *_v("PFOA_Free"))
        PFOS_FreeF = _tnorm(rng, *_v("PFOS_FreeF"))
        PFOA_FreeF = _tnorm(rng, *_v("PFOA_FreeF"))
        PFOS_TMC   = _tnorm(rng, *_v("PFOS_TMC"))
        PFOA_TMC   = _tnorm(rng, *_v("PFOA_TMC"))
        PFOS_KT    = _tnorm(rng, *_v("PFOS_KT"))
        PFOA_KT    = _tnorm(rng, *_v("PFOA_KT"))

        CVINIT = _tnorm(rng, am, am * cv, _VMC["CVINIT"][2], _VMC["CVINIT"][3])

        params = mdl.const_params.copy()
        params.update(mdl._nonconst_defaults)
        params.update({
            "BWINIT":      BWINIT,
            "VLC":         VLC,
            "Ratio_GFR":   RATIO_GFR,
            "Birthweight": BW_g / 1000.0,   # kg
            "PFOS":        1.0 if is_pfos else 0.0,
            "PFOA":        0.0 if is_pfos else 1.0,
            "CVINIT":      CVINIT,
            "PFOS_PL":     PFOS_PL,   "PFOA_PL":    PFOA_PL,
            "PFOS_PR":     PFOS_PR,   "PFOA_PR":    PFOA_PR,
            "PFOS_Free":   PFOS_Free, "PFOA_Free":  PFOA_Free,
            "PFOS_FreeF":  PFOS_FreeF,"PFOA_FreeF": PFOA_FreeF,
            "PFOS_TMC":    PFOS_TMC,  "PFOA_TMC":   PFOA_TMC,
            "PFOS_KT":     PFOS_KT,   "PFOA_KT":    PFOA_KT,
        })

        snaps = mdl.simulate(params, T_MONTHS)
        if snaps is None:
            continue

        for m_idx, t_h in enumerate(T_MONTHS):
            state = snaps.get(t_h, {})
            ca_val   = state.get("CA",   float("nan"))
            ca_f_val = state.get("CA_f", float("nan"))
            if not math.isnan(ca_val):
                ca_samples[m_idx].append(ca_val)
            if not math.isnan(ca_f_val):
                ca_f_samples[m_idx].append(ca_f_val)

    timeseries: list[dict] = []
    for m_idx, (t_h, month) in enumerate(zip(T_MONTHS, range(1, 10))):
        ca_arr   = np.array(ca_samples[m_idx])
        ca_f_arr = np.array(ca_f_samples[m_idx])
        n_ok = len(ca_arr)
        timeseries.append({
            "month":         month,
            "time_h":        t_h,
            "CA_mean_mgL":   float(np.mean(ca_arr))              if n_ok else None,
            "CA_p5_mgL":     float(np.percentile(ca_arr,  5))    if n_ok else None,
            "CA_p25_mgL":    float(np.percentile(ca_arr, 25))    if n_ok else None,
            "CA_p75_mgL":    float(np.percentile(ca_arr, 75))    if n_ok else None,
            "CA_p95_mgL":    float(np.percentile(ca_arr, 95))    if n_ok else None,
            "CA_f_mean_mgL": float(np.mean(ca_f_arr))            if len(ca_f_arr) else None,
        })

    return {
        "compound":   compound,
        "n_iter":     n_iter,
        "n_rows":     len(timeseries),
        "t_end_h":    T_END,
        "timeseries": timeseries,
    }
