"""
RoviraPBKModel/runner.py — FAIRDatabase adapter for the Rovira 2019 pregnancy PBPK.

Wraps the study-specific SBML runner to provide a clean execute(user_params) API.
Deterministic model: GW0 → GW38, two output timepoints (GW12 and GW38/delivery).

Compounds: PFOA, PFOS
No breastfeeding scenarios — the model covers pregnancy only.
"""
from __future__ import annotations
import math, os, re, sys
from collections import deque

import libsbml
import numpy as np
import pandas as pd
from scipy.integrate import solve_ivp

_HERE     = os.path.dirname(os.path.abspath(__file__))
SBML_PATH = os.path.join(_HERE, "Rovira2019FAIR.xml")

T_GW12 = 2016.0   # h (12 weeks × 168 h/wk)
# Rovira 2019 models delivery at GW38 (preterm/average), not GW40 (full term).
# The Generic model uses GW40 (T_DELIVERY=6720 h).  Keep GW38 here to match
# the original study design; document explicitly for users comparing outputs.
T_DEL  = 6384.0   # h (38 weeks × 168 h/wk)
from plugins.pbpk.params import CVINIT as _CVINIT, ROVIRA as _ROVIRA
BW0      = _ROVIRA["BW0"]["default"]
BW_BIRTH = _ROVIRA["BW_BIRTH"]["default"]

# CVINIT defaults: post-phase-out (2015+) European general-population levels.
# PFOA ~0.34 µg/L, PFOS ~3.14 µg/L (HBM4EU / EFSA 2020 background data).
# Note: Verner 2015 uses higher pre-2010 values (PFOA ~2.53 µg/L, PFOS ~13 µg/L).
CVINIT_DEFAULT = {"PFOA": _CVINIT["PFOA"], "PFOS": _CVINIT["PFOS"]}  # mg/L — see params.py

# Half-lives in compound descriptions are adult values (Olsen et al. 2007).
# The Generic/Ratier model uses child-specific values (PFOA 2.5 yr, PFOS 4.1 yr;
# Ratier 2024) which are shorter due to growth dilution.
COMPOUNDS = [
    {"label": "PFOA", "description": "PFOA (C8, adult half-life ~3.8 yr; Olsen 2007)"},
    {"label": "PFOS", "description": "PFOS (C8-S, adult half-life ~5.4 yr; Olsen 2007)"},
]

EXECUTE_COLS = [
    "gestational_wk", "time_h", "CA_maternal_mgL", "CA_fetal_mgL", "transfer_ratio"
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


_REL_OPS = {
    libsbml.AST_RELATIONAL_EQ: "==", libsbml.AST_RELATIONAL_NEQ: "!=",
    libsbml.AST_RELATIONAL_LT: "<",  libsbml.AST_RELATIONAL_LEQ: "<=",
    libsbml.AST_RELATIONAL_GT: ">",  libsbml.AST_RELATIONAL_GEQ: ">=",
}


def _ast_to_py(node: libsbml.ASTNode) -> str:
    t  = node.getType()
    nc = node.getNumChildren()
    ch = lambda i: _ast_to_py(node.getChild(i))
    if t == libsbml.AST_INTEGER:       return str(node.getInteger())
    if t in (libsbml.AST_REAL, libsbml.AST_REAL_E): return repr(node.getReal())
    if t == libsbml.AST_NAME:          return node.getName()
    if t == libsbml.AST_NAME_TIME:     return "t"
    if t == libsbml.AST_PLUS:
        return (" + ".join(f"({ch(i)})" for i in range(nc)) if nc > 1 else f"+({ch(0)})")
    if t == libsbml.AST_MINUS:
        return f"({ch(0)}) - ({ch(1)})" if nc == 2 else f"-({ch(0)})"
    if t == libsbml.AST_TIMES:
        return " * ".join(f"({ch(i)})" for i in range(nc))
    if t == libsbml.AST_DIVIDE:        return f"({ch(0)}) / ({ch(1)})"
    if t in (libsbml.AST_POWER, libsbml.AST_FUNCTION_POWER):
        return f"({ch(0)}) ** ({ch(1)})"
    if t == libsbml.AST_FUNCTION_EXP:  return f"math.exp({ch(0)})"
    if t == libsbml.AST_FUNCTION_LN:   return f"math.log({ch(0)})"
    if t == libsbml.AST_FUNCTION_ABS:  return f"abs({ch(0)})"
    if t == libsbml.AST_FUNCTION_MAX:  return f"max({', '.join(ch(i) for i in range(nc))})"
    if t == libsbml.AST_FUNCTION_MIN:  return f"min({', '.join(ch(i) for i in range(nc))})"
    if t == libsbml.AST_FUNCTION_ROOT:
        deg = node.getChild(0).getInteger() if nc == 2 else 2
        return f"math.sqrt({ch(1)})" if deg == 2 else f"({ch(1)}) ** (1.0 / {deg})"
    if t in _REL_OPS:
        return f"(({ch(0)}) {_REL_OPS[t]} ({ch(1)}))"
    if t == libsbml.AST_LOGICAL_AND:
        return "(" + " and ".join(f"({ch(i)})" for i in range(nc)) + ")"
    if t == libsbml.AST_LOGICAL_OR:
        return "(" + " or ".join(f"({ch(i)})" for i in range(nc)) + ")"
    if t == libsbml.AST_FUNCTION_PIECEWISE:
        n_pairs = nc // 2
        default = ch(nc - 1) if (nc % 2 == 1) else "0.0"
        result  = default
        for i in range(n_pairs - 1, -1, -1):
            result = f"(({ch(2*i)}) if ({ch(2*i+1)}) else ({result}))"
        return result
    name = node.getName()
    if name:
        raise ValueError(f"Unhandled SBML function: {name!r}")
    raise ValueError(f"Unhandled AST type {t}")


class RoviraModel:
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
        self.const_params: dict[str, float] = {}
        self._nonconst_defaults: dict[str, float] = {}
        for i in range(m.getNumParameters()):
            p = m.getParameter(i)
            (self.const_params if p.getConstant()
             else self._nonconst_defaults)[p.getId()] = p.getValue()
        self.species_ids:  list[str] = []
        self.species_init: dict[str, float] = {}
        for i in range(m.getNumSpecies()):
            s = m.getSpecies(i)
            self.species_ids.append(s.getId())
            self.species_init[s.getId()] = s.getInitialAmount()
        assign_exprs: dict[str, str] = {}
        assign_order: list[str] = []
        self.rate_rules: dict[str, str] = {}
        for i in range(m.getNumRules()):
            rule = m.getRule(i)
            var  = rule.getVariable()
            expr = _ast_to_py(rule.getMath())
            if rule.isAssignment():
                assign_exprs[var] = expr; assign_order.append(var)
            elif rule.isRate():
                self.rate_rules[var] = expr
        _ID  = re.compile(r'\b([A-Za-z_][A-Za-z0-9_]*)\b')
        av   = set(assign_order)
        deps = {v: {tok for tok in _ID.findall(assign_exprs[v]) if tok in av and tok != v} for v in av}
        in_d = {v: 0 for v in av}; rev = {v: [] for v in av}
        for v, ds in deps.items():
            for d in ds:
                in_d[v] += 1; rev[d].append(v)
        q = deque(v for v in av if in_d[v] == 0); topo: list[str] = []
        while q:
            v = q.popleft(); topo.append(v)
            for u in rev[v]:
                in_d[u] -= 1
                if in_d[u] == 0: q.append(u)
        self.assign_rules = [(v, assign_exprs[v]) for v in (topo if len(topo) == len(av) else assign_order)]
        self._assign_var_set = av

    def _compile(self):
        I = "    "
        def prelude():
            lines = []
            for idx, sid in enumerate(self.species_ids):
                lines.append(f"{I}{sid} = y[{idx}]")
            for pid in sorted(self.const_params):
                lines.append(f"{I}{pid} = _p.get('{pid}', {self.const_params[pid]!r})")
            for pid, val in self._nonconst_defaults.items():
                if pid not in self._assign_var_set:
                    lines.append(f"{I}{pid} = _p.get('{pid}', {val!r})")
            for var, expr in self.assign_rules:
                lines.append(f"{I}{var} = {expr}")
            return lines
        rhs = ["def _rhs(t, y, _p):"] + prelude()
        dn  = []
        for sid in self.species_ids:
            dn.append(f"_d_{sid}")
            rhs.append(f"{I}_d_{sid} = {self.rate_rules.get(sid, '0.0')}")
        rhs.append(f"{I}return [{', '.join(dn)}]")
        state = ["def _state(t, y, _p):"] + prelude()
        vs = ["t"] + list(self.species_ids) + [v for v, _ in self.assign_rules]
        seen: set[str] = set(); uv: list[str] = []
        for v in vs:
            if v not in seen: uv.append(v); seen.add(v)
        state.append(f"{I}return {{{', '.join(repr(v)+': '+v for v in uv)}}}")
        g = {"math": math, "__builtins__": __builtins__}
        exec(compile("\n".join(rhs),   "<rovira_rhs>",   "exec"), g)
        exec(compile("\n".join(state), "<rovira_state>", "exec"), g)
        self._rhs_fn = g["_rhs"]; self._state_fn = g["_state"]

    def simulate(self, params: dict, t_end: float, t_record: list[float]):
        y0 = np.array([params.get(sid, self.species_init.get(sid, 0.0))
                       for sid in self.species_ids])
        res = solve_ivp(
            fun    = lambda t, y: self._rhs_fn(t, y, params),
            t_span = (0.0, t_end), y0 = y0, method = "LSODA",
            t_eval = np.array(sorted(set(t_record))),
            rtol = 1e-6, atol = 1e-9, max_step = 24.0,
        )
        if not res.success:
            raise RuntimeError(f"ODE failed: {res.message}")
        return {float(ti): self._state_fn(ti, res.y[:, i], params)
                for i, ti in enumerate(res.t)}


_model: "RoviraModel | None" = None


def _get_model() -> "RoviraModel":
    global _model
    if _model is None:
        _model = RoviraModel(SBML_PATH)
    return _model


def _ss_ivdose(p: dict, CVINIT: float) -> float:
    bw  = p["BW0"]
    QC  = p["QCC"] * bw ** 0.75
    QFil = p["FQfil"] * QC
    Tm   = p["TMC"] * bw ** 0.75
    KT   = p["KT"]
    Free = p["Free"]
    Cfil_ss = QFil * Free * CVINIT * KT / (QFil * KT + Tm)
    return QFil * (Free * CVINIT - Cfil_ss)


def _build_y0(params: dict, CVINIT: float) -> dict[str, float]:
    bw = params["BW0"]; fr = params["Free"]
    Vplas0 = params["FVplas"] * bw; Vfil0 = params["FVfil"] * bw
    QFil0  = params["FQfil"] * params["QCC"] * bw ** 0.75
    Cfil_ss = QFil0 * fr * CVINIT * params["KT"] / (QFil0 * params["KT"] + params["TMC"] * bw ** 0.75)
    return {
        "A_plas":  CVINIT * fr             * Vplas0,
        "A_fat":   CVINIT * params["Pfat"] * params["FVfat"] * bw,
        "A_brain": CVINIT * params["Pbr"]  * params["FVbr"]  * bw,
        "A_lung":  CVINIT * params["Plg"]  * params["FVlg"]  * bw,
        "A_gut":   CVINIT * params["PG"]   * params["FVG"]   * bw,
        "A_liver": CVINIT * params["PL"]   * params["FVL"]   * bw,
        "A_kidney":CVINIT * params["PK"]   * params["FVK"]   * bw,
        "A_mar":   CVINIT * params["Pmar"] * params["FVmar"] * bw,
        "A_mam":   CVINIT * params["Pmam"] * params["FVmam"] * bw,
        "A_rest":  CVINIT * params["PR"]   * max(
            bw - (params["FVplas"] + params["FVfat"] + params["FVbr"]
                  + params["FVlg"] + params["FVG"]  + params["FVL"]
                  + params["FVK"]  + params["FVmar"] + params["FVmam"]) * bw, 0.0),
        "A_fil":   Cfil_ss * Vfil0,
        "A_plac": 0.0, "A_fplas": 0.0, "A_fliv": 0.0, "A_fkid": 0.0,
        "A_fbr":  0.0, "A_frest": 0.0, "A_amni": 0.0,
        "A_urine": 0.0, "A_milk": 0.0,
    }


def execute(user_params: dict) -> dict:
    """Run Rovira 2019 pregnancy PBPK for one PFAS compound.

    Parameters (in user_params)
    ---------------------------
    compound : str  — 'PFOA' or 'PFOS'  (default 'PFOA')
    CVINIT   : float — pre-pregnancy plasma (mg/L); default from Rovira 2019 T1
    BW0      : float — pre-pregnancy body weight (kg); default 70.0

    Returns
    -------
    dict with keys: compound, n_rows, t_end_h, peak_CA_maternal_mgL,
        CA_cord_mgL, transfer_ratio, timeseries (2 rows)
    """
    compound = str(user_params.get("compound", "PFOA")).upper()
    if compound not in ("PFOA", "PFOS"):
        raise ValueError(f"compound must be 'PFOA' or 'PFOS', got {compound!r}")

    is_pfos = (compound == "PFOS")
    pfx     = "PFOS_" if is_pfos else "PFOA_"
    mdl     = _get_model()

    params = {}
    params.update(mdl.const_params)
    params.update(mdl._nonconst_defaults)
    params["PFOS"]     = 1.0 if is_pfos else 0.0
    params["PFOA"]     = 0.0 if is_pfos else 1.0
    params["BW0"]      = float(user_params.get("BW0", BW0))
    params["BW_birth"] = BW_BIRTH

    for key in ("TMC", "KT", "Free", "PL", "Pfat", "Pbr", "Plg", "PK",
                "Pmar", "PG", "Pmam", "PR", "Ppla", "PRF"):
        params[key] = params[f"{pfx}{key}"]

    CVINIT = float(user_params.get("CVINIT", CVINIT_DEFAULT[compound]))
    params["CVINIT"] = CVINIT
    params["IVDOSE"] = _ss_ivdose(params, CVINIT)
    params.update(_build_y0(params, CVINIT))

    snaps = mdl.simulate(params, T_DEL, [T_GW12, T_DEL])

    rows = []
    for t_h, label, gw in [(T_GW12, "T1_GW12", 12), (T_DEL, "Delivery_GW38", 38)]:
        st    = snaps.get(t_h, {})
        ca_m  = st.get("CA",   float("nan"))
        ca_f  = st.get("CA_f", float("nan"))
        tr    = (ca_f / ca_m) if (ca_m and ca_m > 0) else float("nan")
        rows.append({
            "gestational_wk":  gw,
            "time_h":          t_h,
            "CA_maternal_mgL": ca_m,
            "CA_fetal_mgL":    ca_f,
            "transfer_ratio":  tr,
        })

    t1_ca  = rows[0]["CA_maternal_mgL"]
    del_ca = rows[1]["CA_maternal_mgL"]
    cord   = rows[1]["CA_fetal_mgL"]
    tr_del = rows[1]["transfer_ratio"]

    return {
        "compound":               compound,
        "n_rows":                 len(rows),
        "t_end_h":                T_DEL,
        "peak_CA_maternal_mgL":  max(t1_ca, del_ca) if all(
            not math.isnan(v) for v in (t1_ca, del_ca)) else float("nan"),
        "CA_cord_mgL":            cord,
        "transfer_ratio":         tr_del,
        "timeseries":             rows,
    }
