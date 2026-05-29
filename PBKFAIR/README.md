# Fork to FAIRDatabase

Drop-in integration of four PBPK models into the
[FAIRDatabase](../../../FAIRDatabase) Flask application:

- **RatierPBKModel** — Lifetime PFAS/PFOA model (birth → ~6.8 yr, Ratier/Verner)
- **GenericPBKModel** — Generic PFAS model (pregnancy + child, GW0 → 12 yr, PFOA/PFOS)
- **RoviraPBKModel** — Rovira 2019 deterministic pregnancy model (GW0 → GW38)
- **VernerPBKModel** — Verner 2015 Monte Carlo pregnancy model (GW0 → GW38)

---

## What's in here

```
Fork to FAIRDatabase/
├── RatierPBKModel/              Lifetime model package
│   ├── __init__.py
│   ├── Ratier2024FAIR.xml     Copy of sbml/lifetime_pbpk.xml (FAIR-annotated)
│   └── runner.py              PBPKModel class + execute(user_params) API
│
├── GenericPBKModel/           Generic PFAS model package
│   ├── __init__.py
│   ├── generic_pfas_pbpk.xml  Copy of Generic_PFAS_PBPK/sbml/generic_pfas_pbpk.xml
│   └── runner.py              GenericModel class + execute(user_params) API
│
├── RoviraPBKModel/            Rovira 2019 pregnancy model package
│   ├── __init__.py
│   ├── rovira2019_pfas_pbpk.xml
│   └── runner.py              RoviraModel class + execute(user_params) API
│
├── VernerPBKModel/            Verner 2015 MC pregnancy model package
│   ├── __init__.py
│   ├── ouidir_human_pbpk.xml
│   └── runner.py              VERNERModel class + execute(user_params) API
│
├── backend/src/ratier_model/         Flask blueprint for /model (lifetime model)
│   ├── __init__.py
│   ├── helpers.py             Validates input, calls RatierPBKModel runner
│   └── routes.py              /model/ui  /model/run  /model/scenarios
│
├── backend/src/generic_model/ Flask blueprint for /generic (generic model)
│   ├── __init__.py
│   ├── helpers.py             Validates input, calls GenericPBKModel runner
│   └── routes.py              /generic/ui  /generic/run  /generic/scenarios  /generic/compounds
│
├── backend/src/rovira_model/  Flask blueprint for /rovira (Rovira model)
│   ├── __init__.py
│   ├── helpers.py             Validates input, calls RoviraPBKModel runner
│   └── routes.py              /rovira/ui  /rovira/run  /rovira/compounds
│
├── backend/src/verner_model/  Flask blueprint for /verner (Verner MC model)
│   ├── __init__.py
│   ├── helpers.py             Validates input, calls VernerPBKModel runner
│   └── routes.py              /verner/ui  /verner/run  /verner/compounds
│
└── frontend/templates/
    ├── model/
    │   └── Ratier2024FAIR.html Lifetime model UI (extends dashboard base)
    ├── generic_model/
    │   └── generic.html       Generic model UI (extends dashboard base)
    ├── rovira_model/
    │   └── rovira.html        Rovira 2019 UI — table of GW12 + delivery results
    └── verner_model/
        └── verner.html        Verner 2015 MC UI — Chart.js percentile band chart
```

---

## How to install into FAIRDatabase

### 1 — Copy the files

```bash
FAIR=~/codes/FAIRDatabase
FORK=~/codes/PBKFAIR/"Fork to FAIRDatabase"

# Model packages → repo root (same level as AnonyBiome/)
cp -r "$FORK/RatierPBKModel"                  "$FAIR/"
cp -r "$FORK/GenericPBKModel"               "$FAIR/"
cp -r "$FORK/RoviraPBKModel"                "$FAIR/"
cp -r "$FORK/VernerPBKModel"                "$FAIR/"

# Blueprints → backend/src/
cp -r "$FORK/backend/src/ratier_model"      "$FAIR/backend/src/"
cp -r "$FORK/backend/src/generic_model"     "$FAIR/backend/src/"
cp -r "$FORK/backend/src/rovira_model"      "$FAIR/backend/src/"
cp -r "$FORK/backend/src/verner_model"      "$FAIR/backend/src/"

# Templates → frontend/templates/
cp -r "$FORK/frontend/templates/ratier_model" "$FAIR/frontend/templates/"
cp -r "$FORK/frontend/templates/generic_model" "$FAIR/frontend/templates/"
cp -r "$FORK/frontend/templates/rovira_model"  "$FAIR/frontend/templates/"
cp -r "$FORK/frontend/templates/verner_model"  "$FAIR/frontend/templates/"
```

### 2 — Add Python dependencies

Append to `FAIRDatabase/backend/requirements.txt`:

```
python-libsbml
scipy
numpy
pandas
```

Then reinstall:

```bash
cd "$FAIR/backend"
pip install -r requirements.txt
```

### 3 — Register the blueprints in app.py

In `FAIRDatabase/backend/app.py`, add following the existing pattern:

```python
# at the top with the other imports
from src.ratier_model.routes  import routes as model_routes
from src.generic_model.routes import routes as generic_model_routes
from src.rovira_model.routes  import routes as rovira_model_routes
from src.verner_model.routes  import routes as verner_model_routes

# inside create_app(), with the other register_blueprint calls
app.register_blueprint(model_routes,         url_prefix="/model")
app.register_blueprint(generic_model_routes, url_prefix="/generic")
app.register_blueprint(rovira_model_routes,  url_prefix="/rovira")
app.register_blueprint(verner_model_routes,  url_prefix="/verner")
```

### 4 — Add nav links (optional)

In whichever base template contains the sidebar/navbar, add:

```html
<a href="/model/ui">PBPK Simulation (Lifetime)</a>
<a href="/generic/ui">PBPK Simulation (Generic PFAS)</a>
<a href="/rovira/ui">PBPK Simulation (Rovira 2019)</a>
<a href="/verner/ui">PBPK Simulation (Verner 2015 MC)</a>
```

### 5 — Start the app and navigate to

```
http://localhost:5000/model/ui      ← Lifetime PFAS model
http://localhost:5000/generic/ui    ← Generic PFAS model (PFOA/PFOS, pregnancy+child)
http://localhost:5000/rovira/ui     ← Rovira 2019 pregnancy model
http://localhost:5000/verner/ui     ← Verner 2015 MC pregnancy model
```

---

## API

### Lifetime PFAS model (`/model`)

| Method | Path | Description |
|--------|------|-------------|
| GET  | `/model/ui`        | Simulation UI (login required) |
| POST | `/model/run`       | Run a scenario, returns JSON |
| GET  | `/model/scenarios` | List available scenarios |

#### POST /model/run — request body

```json
{
  "scenario":  "bf_1yr",
  "HalfLife":  2.5,
  "RateInj":   0.451695,
  "BirthYear": 2007
}
```

#### POST /model/run — response

```json
{
  "scenario":    "bf_1yr",
  "n_rows":      3562,
  "t_end_min":   3561120.0,
  "peak_C_ven":  0.000123,
  "peak_Age_yr": 0.84,
  "final_C_ven": 0.0000987,
  "final_Age_yr": 6.77,
  "timeseries":  [{"time": 0, "Age": 0, "C_ven": 0.0, ...}, ...]
}
```

---

### Generic PFAS model (`/generic`)

| Method | Path | Description |
|--------|------|-------------|
| GET  | `/generic/ui`        | Simulation UI (login required) |
| POST | `/generic/run`       | Run a compound/scenario, returns JSON |
| GET  | `/generic/scenarios` | List available breastfeeding scenarios |
| GET  | `/generic/compounds` | List supported PFAS compounds |

#### POST /generic/run — request body

```json
{
  "compound":  "PFOA",
  "scenario":  "bf_1yr",
  "Ratio_GFR": 1.0
}
```

#### POST /generic/run — response

```json
{
  "compound":              "PFOA",
  "scenario":              "bf_1yr",
  "n_rows":                500,
  "t_end_h":               24252.0,
  "peak_CA_maternal_mgL":  0.000045,
  "peak_age_yr":           0.0,
  "peak_CA_fetal_mgL":     0.000038,
  "final_CA_maternal_mgL": 0.000041,
  "final_age_yr":          2.0,
  "timeseries":            [{"time_h": 0, "age_child_yr": -0.77, ...}, ...]
}
```

---

### Rovira 2019 pregnancy model (`/rovira`)

| Method | Path | Description |
|--------|------|-------------|
| GET  | `/rovira/ui`        | Simulation UI (login required) |
| POST | `/rovira/run`       | Run a deterministic simulation, returns JSON |
| GET  | `/rovira/compounds` | List supported PFAS compounds |

#### POST /rovira/run — request body

```json
{
  "compound": "PFOA",
  "CVINIT":   0.00034,
  "BW0":      70.0
}
```

#### POST /rovira/run — response

```json
{
  "compound":              "PFOA",
  "n_rows":                2,
  "t_end_h":               6384.0,
  "peak_CA_maternal_mgL":  0.000331,
  "CA_cord_mgL":           0.000311,
  "transfer_ratio":        0.94,
  "timeseries": [
    {"gestational_wk": 12, "time_h": 2016.0, "CA_maternal_mgL": 0.000331, "CA_fetal_mgL": 0.0,       "transfer_ratio": null},
    {"gestational_wk": 38, "time_h": 6384.0, "CA_maternal_mgL": 0.000331, "CA_fetal_mgL": 0.000311, "transfer_ratio": 0.94}
  ]
}
```

---

### Verner 2015 MC pregnancy model (`/verner`)

| Method | Path | Description |
|--------|------|-------------|
| GET  | `/verner/ui`        | Simulation UI (login required) |
| POST | `/verner/run`       | Run MC simulation, returns JSON |
| GET  | `/verner/compounds` | List supported PFAS compounds |

#### POST /verner/run — request body

```json
{
  "compound": "PFOA",
  "n_iter":   100,
  "seed":     42
}
```

#### POST /verner/run — response

```json
{
  "compound":  "PFOA",
  "n_iter":    100,
  "n_rows":    9,
  "t_end_h":   6570.0,
  "timeseries": [
    {"month": 1, "time_h": 730.0,  "CA_mean_mgL": 0.00248, "CA_p5_mgL": 0.00102, "CA_p25_mgL": 0.00180, "CA_p75_mgL": 0.00340, "CA_p95_mgL": 0.00512, "CA_f_mean_mgL": 0.00195},
    {"month": 2, "time_h": 1460.0, "CA_mean_mgL": 0.00245, "CA_p5_mgL": 0.00100, "CA_p25_mgL": 0.00178, "CA_p75_mgL": 0.00336, "CA_p95_mgL": 0.00508, "CA_f_mean_mgL": 0.00140},
    "... 9 rows total (months 1–9)"
  ]
}
```

---

## Notes

- The ODE integration (LSODA via scipy) takes **30–90 seconds** per run.
  For production use, consider wrapping `run_scenario()` in Celery or a
  background thread and polling for results.
- `RatierPBKModel/runner.py` caches the loaded model as a module-level singleton
  so the SBML parse + compile cost (few seconds) only occurs once per worker
  process.
- The `timeseries` field in the JSON response is downsampled to 500 points
  to keep response sizes manageable. Full-resolution CSV can be produced by
  calling `runner.execute()` directly and writing `df_out.to_csv()`.
