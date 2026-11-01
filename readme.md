# FAIRDatabase

Steps to set up and use the Microbiome FAIR Database locally.

---

## Table of Contents

- [Quick Start (Docker)](#quick-start-docker)
  - [Option A: Fully Automatic Setup](#option-a-fully-automatic-setup-zero-config)
    - [Step 1 — Generate config automatically](#step-1--generate-config-automatically)
    - [Step 2 — Start the stack](#step-2--start-the-stack)
    - [Step 3 — Register and log in](#step-3--register-and-log-in)
  - [Option B: Manual Setup (Set Your Own Passwords)](#option-b-manual-setup-set-your-own-passwords)
    - [Step 1 — Create the environment file](#step-1--create-the-environment-file)
    - [Step 2 — Set your passwords](#step-2--set-your-passwords)
    - [Step 3 — Bootstrap and start the stack](#step-3--bootstrap-and-start-the-stack)
    - [Step 4 — Register and log in](#step-4--register-and-log-in)
  - [Optional: run Flask on the host (for development)](#optional-run-flask-on-the-host-for-development)
  - [Access the Application](#access-the-application)
  - [Stopping and Resetting](#stopping-and-resetting)
  - [Selecting which plugins to load](#selecting-which-plugins-to-load)
  - [Database schemas](#database-schemas)
  - [Troubleshooting](#troubleshooting)
- [Quick Start (Podman)](#quick-start-podman)
- [Development Setup (Run Flask locally)](#development-setup-run-flask-locally)
- [Running Tests](#running-tests)
- [Setting Up RBAC for Your Institute](#setting-up-rbac-for-your-institute)
  - [Roles at a Glance](#roles-at-a-glance)
  - [Step 1 — Bootstrap the First Admin](#step-1--bootstrap-the-first-admin)
  - [Step 2 — Onboard New Users](#step-2--onboard-new-users)
  - [Step 3 — Assign Roles](#step-3--assign-roles)
  - [Step 4 — Grant Dataset Access](#step-4--grant-dataset-access)
  - [Step 5 — Audit Changes](#step-5--audit-changes)
  - [Service Ports Reference](#service-ports-reference)
  - [Operational Notes](#operational-notes)
- [Application Routes](#application-routes)
  - [Authentication](#authentication)
  - [Dashboard](#dashboard)
  - [Data Management](#data-management)
  - [Privacy Routes](#privacy-routes)

---

## Quick Start (Docker)

Requires [Docker](https://docs.docker.com/get-docker/) (with Compose v2), plus `bash` and `openssl` for the setup script; both are standard on Linux and macOS. On Windows, run everything inside WSL2 (Ubuntu), with Docker Desktop's WSL integration turned on. Choose one of the two options below — **Option A** for a zero-config quickstart, **Option B** if you want to set your own passwords.

---

> The Flask app runs **in a container** (`fairdatabase-flask`, defined directly in `backend/docker-compose.yml`). `docker compose up -d` starts the whole stack — Supabase **and** the app. You do **not** create a venv or run `./run.sh` for normal use; that is only for host-based development (see [Optional: run Flask on the host](#optional-run-flask-on-the-host-for-development)).

### Option A: Fully Automatic Setup (Zero Config)

#### Step 1 — Generate config automatically

```bash
bash scripts/bootstrap.sh --auto
```

> The Supabase Studio dashboard login is printed to your terminal. All generated passwords and keys are stored in `backend/.env`; keep that file safe and out of git (it is already git-ignored).

> Run `--auto` **once**, on a fresh install. To re-run the setup later (e.g. after changing `ADMIN_EMAIL`), use `bash scripts/bootstrap.sh` without `--auto`: it reuses the passwords in `backend/.env`. `--auto` refuses to run once a database exists, because a new password would lock the stack out of its own database.

> **Admin user:** `--auto` cannot guess who the admin is, so it leaves `ADMIN_EMAIL=` blank (it prints a `[WARN]`). To get an auto-promoted admin, set `ADMIN_EMAIL=<your-email>` in `backend/.env` after this step, then (re)start the stack. `_bootstrap_admin` promotes that account to `admin` on every boot, and the value is preserved across future `bootstrap.sh` re-runs — so you set it once. Without it, assign roles manually via `/admin/users`. See [When ADMIN_EMAIL is promoted](#when-admin_email-is-promoted) before exposing the app beyond your own machine.

> **Plugin selection** Setup your plugins via the allowlist (FAIRDB_PLUGINS) or the reject list (FAIRDB_PLUGINS_DISABLED)
#### Step 2 — Start the stack

```bash
cd backend
docker compose up -d
```

Wait about a minute for services to become healthy (on first start `realtime` shows `unhealthy` for up to a minute while it sets up its tables; that is normal):

```bash
docker compose ps
```

All key services (`supabase-auth`, `supabase-kong`, `supabase-db`, `fairdatabase-flask`) should show `(healthy)`.

> `supabase-db-init` is a one-shot setup container — it will show `Exited (0)` once finished. That is expected, not a failure.

> No `.env` host-edit step is needed: the container reaches the database and Supabase by Docker service name (`db`, `kong`), set in the override's `environment:` block, which takes precedence over `backend/.env`.

#### Step 3 — Register and log in

There is no default user account. You must register before you can log in:

1. Go to **http://localhost:5000/auth/register** and create an account with any email and password.
2. You will be redirected to **http://localhost:5000/auth/login** — use the same credentials to log in.

`ENABLE_EMAIL_AUTOCONFIRM=true` is set by default so no email verification is required.

> **Admin promotion:** `_bootstrap_admin` only runs at Flask startup, so a user set in `ADMIN_EMAIL` is promoted to `admin` on the *next* boot after they register. After registering that account, run `docker compose restart flask-app` once. Full order: set `ADMIN_EMAIL` → `up` → register that email → `docker compose restart flask-app`.

---

### Option B: Manual Setup (Set Your Own Passwords)

#### Step 1 — Create the environment file

```bash
cp backend/.env.example backend/.env
```

#### Step 2 — Set your passwords

Open `backend/.env` and change these three variables from `change-me` to values of your choice:

- `POSTGRES_PASSWORD` — PostgreSQL database password.
- `DASHBOARD_PASSWORD` — Password for the Supabase Studio dashboard (username is always `supabase`).
- `SECRET_KEY` — Secret key for Flask session security. At least 16 characters; generate one with `openssl rand -base64 32`. `bootstrap.sh` rejects shorter keys and common placeholders, because the app refuses to start with them.

Use letters and digits for `POSTGRES_PASSWORD` (e.g. `openssl rand -hex 24`): it is placed inside database connection URLs, where `@`, `/`, `:` or `#` break the connection.

**Optional variables (leave as defaults unless needed):**
- `ADMIN_EMAIL` — Email auto-promoted to `admin` on every boot. Set it now and it is preserved across `bootstrap.sh` re-runs. Leave empty to disable auto-promotion (assign roles manually via `/admin/users`). See [When ADMIN_EMAIL is promoted](#when-admin_email-is-promoted).
- `ADMIN_BOOTSTRAP_ALLOW_AUTOCONFIRM` — `bootstrap.sh` sets it to `true`. Only matters while `ENABLE_EMAIL_AUTOCONFIRM=true`; see the same section.
- `SITE_URL` — Where the app runs (default: `http://localhost:5000`).
- `SMTP_*` — Email server settings. Leave blank if you don't need email sending.
- `DISABLE_SIGNUP` — Set to `true` to prevent new user registrations.
- `ENABLE_EMAIL_AUTOCONFIRM` — Set to `true` so new users skip email verification (recommended for local testing).

#### Step 3 — Bootstrap and start the stack

```bash
bash scripts/bootstrap.sh

cd backend
docker compose up -d
```

Wait about a minute for services to become healthy (on first start `realtime` shows `unhealthy` for up to a minute while it sets up its tables; that is normal):

```bash
docker compose ps
```

All key services (`supabase-auth`, `supabase-kong`, `supabase-db`, `fairdatabase-flask`) should show `(healthy)`.

> `supabase-db-init` is a one-shot setup container — it will show `Exited (0)` once finished. That is expected, not a failure.

#### Step 4 — Register and log in

There is no default user account. You must register before you can log in:

1. Go to **http://localhost:5000/auth/register** and create an account with any email and password.
2. You will be redirected to **http://localhost:5000/auth/login** — use the same credentials to log in.

`ENABLE_EMAIL_AUTOCONFIRM=true` is set by default so no email verification is required.

> **Admin promotion:** `_bootstrap_admin` only runs at Flask startup, so a user set in `ADMIN_EMAIL` is promoted to `admin` on the *next* boot after they register. After registering that account, run `docker compose restart flask-app` once. Full order: set `ADMIN_EMAIL` → `up` → register that email → `docker compose restart flask-app`.

---

### Optional: run Flask on the host (for development)

Only needed for active app development (live reload, debugger) — **not** for normal use, where Flask runs in the `fairdatabase-flask` container.

To avoid two Flask instances fighting over port `5000`, run the Supabase stack **without** the app container:

```bash
cd backend
docker compose up -d --scale flask-app=0     # Supabase + db-init only
```

No `.env` edits are needed: `run.sh` replaces the Docker-internal addresses in `backend/.env` (`db:5432`, `kong:8000`) with the ports Docker publishes on your machine (`127.0.0.1:5433`, `localhost:8000`) for the Flask process only. Do **not** change `POSTGRES_PORT` in `backend/.env`; it is also the port Postgres listens on inside Docker, and changing it breaks the whole stack.

Run the app from `backend/`:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
../scripts/install-plugin-deps.sh   # PBPK + FL plugins' packages (torch, libsbml); ~2 min
./run.sh
```

Without the plugin packages the app still starts, but the PBPK and federated-learning pages are missing (the loader skips plugins whose packages are not installed).

---

### Access the Application

Once everything is running:

| Service | URL | Description |
|---|---|---|
| **Main Application** | http://localhost:5000 | The FAIRDatabase app — register and log in here. |
| **Database Dashboard** | http://localhost:8000 | Supabase Studio — view and manage database tables. Your browser asks for a login: username `supabase`, password = your `DASHBOARD_PASSWORD`. Studio has no login of its own, so it is only reachable through this gateway (Kong), and only from this machine. From another computer, open a tunnel first: `ssh -L 8000:127.0.0.1:8000 you@server`, then browse to `http://localhost:8000`. |
| **API Endpoint** | http://localhost:8000 (`/auth`, `/rest`, `/storage`, `/functions`) | Supabase API — used internally by the app. Same gateway as the dashboard. |

### Stopping and Resetting

If you need to stop the application or want to wipe the data and start over:

```bash
cd backend

# Stop all services but KEEP your data
docker compose down
```

**Factory reset (deletes all data).** The database lives in the folder `backend/volumes/db/data`, not in a Docker volume, so `docker compose down -v` does **not** remove it. Postgres owns that folder, so deleting it needs `sudo`:

```bash
cd backend
docker compose down -v
sudo rm -rf volumes/db/data
cd .. && bash scripts/bootstrap.sh --auto     # or without --auto to keep your .env passwords
cd backend && docker compose up -d
```

### Selecting which plugins to load

Feature plugins under `backend/plugins/` (currently **pbpk**,
**horizontal_fl** and **vertical_fl**) are auto-discovered and mounted at Flask boot. To run only a
subset, set these in `backend/.env` (both default to empty = load everything):

```bash
# Allowlist — load ONLY these plugins (folder names, comma-separated)
FAIRDB_PLUGINS=pbpk

# Denylist — load everything EXCEPT these (applied after the allowlist)
FAIRDB_PLUGINS_DISABLED=horizontal_fl
```

Then `docker compose up -d` (or `docker compose restart flask-app` if already
running). The loader logs each skipped plugin at startup
(`docker compose logs flask-app | grep -i plugin`).

Notes:
- Names are the plugin **folder** names (`pbpk`, `horizontal_fl`, `vertical_fl`).
- This is a runtime switch — the image still contains all plugin code and its
  Python deps. A disabled plugin's routes, schema, and storage buckets are
  simply never mounted/applied; nothing else changes.
- A plugin whose `required_packages` aren't installed also skip-mounts itself
  with a warning — independent of this allowlist.

### Database schemas

Application-level schemas are applied **automatically** on fresh DB init and on every Flask container boot:

**Core schemas:**
- `backend/migrate_schema.sql` — `_fd` schema for CSV-upload metadata and tables
- `backend/rbac_schema.sql` — Role-based access control: user roles, dataset grants, RLS policies, audit tables
- `backend/demo_schema.sql` — Public demo API support

**Kernel schemas** (applied by the plugin loader at Flask boot):
- `backend/kernel/sql/001_kernel.sql` — `_fd.plugin_audit` (the generic mutation audit log used by `kernel.audit`)
- `backend/kernel/sql/002_dp_budget.sql` — `_fd.fl_epsilon_budget` and the `metadata_tables.fl_eligible` column (backing `kernel.dp_budget`)

**Plugin schemas** (each plugin owns its own; applied by the loader from its manifest's `sql_migrations`):
- `backend/plugins/pbpk/sql/001_schema.sql` — PBPK parameter sets, runs, and run artifacts
- `backend/plugins/horizontal_fl/sql/001_schema.sql` — FL tasks, rounds, clients, round submissions
- `backend/plugins/vertical_fl/sql/001_schema.sql` — vertical FL tasks, parties, patient-ID matching (PSI), rounds

**How it works:**
- On a fresh `db` volume, only the **core** schemas are mounted into `/docker-entrypoint-initdb.d/migrations/` and run by Postgres at first init (in order: `100-fd-schema`, `101-fd-rbac`, `103-fd-demo`). Order matters: `rbac_schema.sql` defines `_fd.current_role()`, which plugin RLS policies depend on.
- On every `flask-app` container start, the entrypoint re-applies the core schemas via `psql` (see `docker-entrypoint.sh`), and the Flask app factory then runs the **plugin loader**, which applies kernel SQL and every discovered plugin's `sql_migrations`. All files are idempotent (`IF NOT EXISTS`, `ADD COLUMN IF NOT EXISTS`, `CREATE POLICY IF NOT EXISTS`), so re-runs are safe.

**Custom schemas:** New plugin schemas just go in `plugins/<name>/sql/`; the loader picks them up — no `docker-compose.yml` or `docker-entrypoint.sh` edits needed. Core schemas (rare) follow the same mount + entrypoint pattern as the existing three.

### PBPK simulation artifacts

The `/model/runs/<run_id>/artifacts` endpoints accept binary outputs (jpg, png, mp4, vtk/vtu/vtp) attached to a persisted simulation run. Bytes live in the Supabase Storage bucket `pbpk-artifacts`; catalog rows in `_fd.pbpk_run_artifacts` carry the RBAC.

- **Bucket** — declared in `plugins/pbpk/plugin.py` and created automatically on Flask boot by the plugin loader's `bootstrap_plugin_buckets`. Idempotent; "already exists" is a no-op.
- **Storage RLS** — apply once, by hand, when you want browsers to read objects directly via signed URLs without going through Flask:
  ```bash
  PGPASSWORD=$POSTGRES_SECRET psql \
      -h $POSTGRES_HOST -p $POSTGRES_PORT \
      -U $POSTGRES_USER -d $POSTGRES_DB_NAME \
      -f backend/plugins/pbpk/sql/pbpk_storage_policies.sql
  ```
  Until applied, the bucket is reachable only via the service-role client (the Flask backend), which is fine for the PoC — every browser read flows through `/model/runs/<id>/artifacts` and the backend issues short-lived signed URLs.
- **Limits** — 200 MB per file; signed URL TTL 10 minutes. Allowed types: `image/jpeg`, `image/png`, `video/mp4`, and the `.vtk` / `.vtu` / `.vtp` mesh family (sent as `application/octet-stream`).
- **Upload example** — form posts need the session's CSRF token (see [Scripting the app with curl](#scripting-the-app-with-curl)):
  ```bash
  curl -b cookies.txt -H "X-CSRFToken: $CSRF" -F "file=@conc_field.png" \
       http://localhost:5000/model/runs/42/artifacts
  ```

### Troubleshooting

**`ImportError: libexpat.so.1: cannot open shared object file`** when the `flask-app` container starts.

The PBPK simulation module (`PBKFAIRModel/`) depends on `python-libsbml`, which is a Python wrapper around a C library that links against `libexpat`. The base `python:3.10-slim` image does not include it. The Dockerfile installs it via `apt-get install libexpat1`. If you ever swap the base image or strip apt packages, libsbml will fail to import and `flask-app` will enter a restart loop. The full set of system libs required by the image is: `libpq5` (psycopg2), `libexpat1` (libsbml), `postgresql-client` (entrypoint migrations), `curl` (healthcheck). If you add scientific Python packages later (e.g. cvxpy, hdf5-based libs), expect to extend this list — check the import error for the missing `.so` and add the matching debian package.

**Supabase services crash-loop on an existing/migrated DB volume** (`supabase-pooler`, `realtime`, or `auth` restarting; logs show `28P01 password authentication failed`, `3D000 database "_supabase" does not exist`, `3F000 schema "_supavisor"/"_realtime" does not exist`, or `42501 must be owner of function uid`).

Root cause: the `supabase/postgres` image only runs the SQL in `docker-entrypoint-initdb.d` on **first** DB init. On a pre-existing volume those internals are never (re)applied. This is now handled automatically by the **`db-init`** one-shot service in `docker-compose.yml`: it runs on every `up` *before* realtime/auth/supavisor/flask (`depends_on: service_completed_successfully`) and idempotently re-syncs internal role passwords, creates the `_supabase` database, the `_supavisor`/`_realtime` schemas, and repairs `auth` ownership. If you still see these errors:

- Confirm `db-init` exited 0: `docker compose logs supabase-db-init`.
- If `roles.sql` warns about auth failure, the volume's **`postgres`** superuser password itself drifted from `POSTGRES_PASSWORD` (db-init connects over TCP and cannot self-heal that one). Manual repair, run inside the DB container which trusts the local socket:
  ```bash
  docker exec -it supabase-db psql -U postgres -c \
    "ALTER USER postgres WITH PASSWORD '<value of POSTGRES_PASSWORD in backend/.env>';"
  docker compose up -d   # db-init then fixes the remaining roles
  ```
- `bootstrap.sh --auto` and `--rotate-secrets` refuse to run while `backend/volumes/db/data` holds a database (new passwords/keys would lock the stack out of it). To intentionally start clean, follow the factory reset in [Stopping and Resetting](#stopping-and-resetting) (**destroys all data**).

**`port is already allocated` / `address already in use`** on `docker compose up`.

Another program already uses one of the ports the stack needs: 5000 (app), 8000 (Supabase gateway), 5433 (database), or 5432 / 6543 (connection pooler). The most common case is a Postgres installed directly on the computer, which holds 5432. Find the program with `sudo ss -ltnp | grep -E ':(5000|8000|5433|5432|6543) '`, then either stop it or change the **left-hand** number of that port in `backend/docker-compose.yml` (e.g. `127.0.0.1:5442:5432`). Moving 5000 or 8000 also means changing the URLs that `bootstrap.sh` writes into `backend/.env` (`SITE_URL`, `API_EXTERNAL_URL`), and a later `bootstrap.sh` run resets them, so for those two it is simpler to stop the other program.

**`flask-app` keeps restarting with `SECRET_KEY is missing, too short`.** Put a key of at least 16 characters in `backend/.env` (`openssl rand -base64 32`), then `docker compose up -d`.

**Editing a bind-mounted file then `docker restart`ing fails on WSL2** with `mount ... no such file or directory` (e.g. after editing `volumes/pooler/pooler.exs` or any `volumes/db/*`).

Docker Desktop's WSL2 backend caches the inode of bind-mounted files; editing one (especially from the Windows side or via an editor that replaces rather than truncates) invalidates the reference. `docker restart <svc>` then cannot re-establish the mount. **Recreate, do not restart:**

```bash
docker compose up -d --force-recreate --no-deps <service>
```

If the Docker CLI itself hangs (`docker ps`/`docker info` time out — a separate WSL2 wedge, often triggered by a stuck `docker exec` against a missing database), restart Docker Desktop from Windows; running containers and the DB volume are unaffected.

---

## Quick Start (Podman)

```bash
# One-time setup
bash scripts/podman-setup.sh

# Then same workflow as Docker
cp backend/.env.example backend/.env
# Edit backend/.env with your passwords
bash scripts/bootstrap.sh
cd backend
podman-compose up -d
```

---

## Running Tests

### Containerized tests (recommended)

Run the full test suite against the live Supabase stack:

```bash
cd backend

# Unit + integration tests (pytest)
docker compose -f docker-compose.yml -f docker-compose.test.yml run --rm test-runner

# Edge function tests (security, output validation, Aitchison distance)
docker compose -f docker-compose.yml -f docker-compose.test.yml run --rm edge-test-runner
```

### Local tests (without Docker)

Requires a running Supabase stack and Python venv. First create the test config (once): copy the example and fill the empty values (`SECRET_KEY`, `SUPABASE_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `POSTGRES_PASSWORD`) from `backend/.env` (`ANON_KEY` → `SUPABASE_KEY`, `SERVICE_ROLE_KEY` → `SUPABASE_SERVICE_ROLE_KEY`). `tests/.env.test` is git-ignored — never commit it.

```bash
cd backend
cp tests/.env.test.example tests/.env.test   # then fill it in
```

Tests that need the database are **skipped**, not failed, when it is unreachable, so check the skip count. The plugin tests also need the plugins' packages: run `../scripts/install-plugin-deps.sh` once in the venv.

```bash
cd backend
source venv/bin/activate
export PYTHONPATH=$(pwd)/..
./run_test.sh                     # excludes slow tests
pytest                            # all tests including slow ones
pytest tests/auth/test_authentication.py -v   # single file
```

---

## Development Setup (Run Flask locally)

If you are a developer and prefer to run the Flask application directly on your machine (outside of Docker) so you can easily edit the code, while keeping the Supabase database inside Docker.

### Dependencies

- Python 3.10
- Node.js 18.17+ (for Supabase CLI, optional)

### Supabase setup

1. Set your passwords and bootstrap:
    ```bash
    cp backend/.env.example backend/.env
    # Edit backend/.env with your passwords as described in the Quick Start
    bash scripts/bootstrap.sh
    ```

2. Start only the database and Supabase services (this will still run in Docker; `--scale flask-app=0` keeps the app container off port 5000):
    ```bash
    cd backend
    docker compose up -d --scale flask-app=0
    ```

### Flask setup

All commands below must be run from inside the `backend/` directory.

1. Navigate to the `backend` directory:
    ```bash
    cd backend
    ```

2. Set up a Python virtual environment to isolate your dependencies:
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```

3. Install the required Python packages, then the plugins' own packages (PBPK and federated learning need `libsbml` and `torch`; about 2 minutes):
    ```bash
    pip install -r requirements.txt
    ../scripts/install-plugin-deps.sh
    ```

4. Leave `backend/.env` as `bootstrap.sh` wrote it. It holds Docker-internal addresses (`POSTGRES_HOST=db`, `POSTGRES_PORT=5432`, `SUPABASE_URL=http://kong:8000`); `run.sh` swaps them for the host-published ports (`127.0.0.1:5433`, `localhost:8000`) when it starts Flask. Do **not** edit `POSTGRES_PORT` in `.env`: the Supabase containers use it too.

5. Start the Flask development server:
    ```bash
    ./run.sh
    ```

The application will now be running at `http://localhost:5000` and will automatically reload if you make changes to the Python code.

### Logging in for the first time

There is no default user account. You must register before you can log in:

1. Go to **http://localhost:5000/auth/register** and create an account with any email and password.
2. You will be redirected to **http://localhost:5000/auth/login** — use the same credentials to log in.

`ENABLE_EMAIL_AUTOCONFIRM=true` is set by default, so no email verification is required.

---

## Setting Up RBAC for Your Institute

This is the end-to-end guide for an institute deploying FAIRDatabase from scratch and controlling who can do what. It assumes you have followed the Quick Start above and the stack is reachable on `http://localhost:5000`.

### Roles at a Glance

Every authenticated user holds **exactly one** role from `_fd.user_role`:

| Role           | Sign-up default? | Upload datasets | Modify datasets         | Read datasets                    | Manage roles | Manage grants            |
|----------------|------------------|-----------------|-------------------------|----------------------------------|--------------|--------------------------|
| **admin**      | no               | yes             | any dataset             | any dataset                      | yes          | any dataset              |
| **curator**    | no               | yes             | datasets they own       | own + explicitly granted         | no           | datasets they own        |
| **accessor**   | no               | no              | no                      | only datasets explicitly granted | no           | no                       |
| **visualizer** | **yes**          | no              | no                      | catalog + aggregate stats only   | no           | no                       |

New sign-ups always land in `visualizer`. An admin must promote them before they can upload or read raw data.

### Step 1 — Bootstrap the First Admin

There is no admin account by default. The cleanest path is the boot-time bootstrap.

1. Decide which email will be the institute admin (e.g. `data-steward@your-institute.org`). This email must belong to a Supabase user, so register it first at `http://localhost:5000/auth/register`.
2. Set the email in `backend/.env`:
   ```
   ADMIN_EMAIL=data-steward@your-institute.org
   ```
3. Restart the Flask container (or the local Flask process):
   ```bash
   cd backend && docker compose restart flask-app
   ```
4. On boot, `_bootstrap_admin` (in `backend/app.py`) looks up that email via the Supabase admin API and **upserts** `_fd.user_roles` to `admin`. The action is idempotent — leave `ADMIN_EMAIL` set permanently if you want the admin role re-asserted on every boot (useful if someone accidentally demotes the admin).
5. Log in as that user. You should now see an **Admin** entry in the dashboard navigation; the admin console lives at `http://localhost:5000/admin/users`.

If you do not want a fixed admin (e.g. you are migrating from another system), you can bootstrap directly in Postgres instead:

```bash
docker compose exec db psql -U postgres -c \
  "INSERT INTO _fd.user_roles (user_id, role, assigned_by)
   VALUES ('<uuid-from-supabase-studio>', 'admin', NULL)
   ON CONFLICT (user_id) DO UPDATE SET role = 'admin';"
```

### Step 2 — Onboard New Users

There are two patterns; pick whichever fits your institute:

**Self-service (default).** Anyone can register at `http://localhost:5000/auth/register`. New accounts default to `visualizer` (catalog + aggregate stats only), so self-service is safe — they cannot reach raw data until an admin promotes them.

**Closed registration.** Set `DISABLE_SIGNUP=true` in `backend/.env` and re-run `bash scripts/bootstrap.sh` then `docker compose up -d`. New users must then be created by an admin via Supabase Studio (`http://localhost:8000` → Authentication → Users → *Add user*). The dashboard password is whatever you set as `DASHBOARD_PASSWORD`.

Email verification is off by default (`ENABLE_EMAIL_AUTOCONFIRM=true`). Flip it to `false` if your institute requires email confirmation; then configure the `SMTP_*` variables.

### Step 3 — Assign Roles

Logged in as `admin`, go to `http://localhost:5000/admin/users`. The page lists every Supabase user with their current role and a dropdown to change it.

- **Promote a researcher to `curator`** so they can upload and own datasets.
- **Promote an analyst to `accessor`** so you can later grant them specific datasets.
- **Demote** a user back to `visualizer` to revoke all dataset access in one step.

Every change writes a row to `_fd.role_audit` recording who changed whom, when, and from what to what.

Programmatic alternative (admin only; needs the CSRF token, see [Scripting the app with curl](#scripting-the-app-with-curl)):

```bash
curl -X POST http://localhost:5000/admin/users/<user-uuid>/role \
  -b cookies.txt -H "X-CSRFToken: $CSRF" \
  -d "role=curator"
```

#### When ADMIN_EMAIL is promoted

Promotion trusts that whoever registered `ADMIN_EMAIL` owns that inbox. With `ENABLE_EMAIL_AUTOCONFIRM=true` (the default) nobody's address is checked, so whoever registers that email first becomes admin. The app therefore promotes only when one of these holds:

- `ENABLE_EMAIL_AUTOCONFIRM=false` (real e-mail confirmation; needs the `SMTP_*` settings), or
- `ADMIN_BOOTSTRAP_ALLOW_AUTOCONFIRM=true` — `bootstrap.sh` sets this so a local install works out of the box.

Otherwise Flask logs `Not promoting ADMIN_EMAIL=...` at boot and nobody is promoted. On any machine other users can reach, either register the admin account yourself **before** opening the app to others, or set `ADMIN_BOOTSTRAP_ALLOW_AUTOCONFIRM=false` and turn on e-mail confirmation.

#### Scripting the app with curl

Every form POST (`multipart/form-data` or `x-www-form-urlencoded`) must carry the session's CSRF token, or the app answers **400**. JSON requests (`Content-Type: application/json`) are exempt. To script form posts, keep one cookie jar and read the token from the login page:

```bash
# 1. Open the login page: starts a session and gives you its token.
CSRF=$(curl -s -c cookies.txt http://localhost:5000/auth/login \
       | grep -o 'name="csrf_token" value="[^"]*"' | cut -d'"' -f4)
# 2. Log in with the same session; the token stays valid afterwards.
curl -s -b cookies.txt -c cookies.txt -X POST http://localhost:5000/auth/login \
     --data-urlencode "email=you@example.org" --data-urlencode "password=..." \
     --data-urlencode "csrf_token=$CSRF" -o /dev/null
```

Logging out is a form POST too (`POST /auth/logout`); a plain link or GET no longer logs out.

### Step 4 — Grant Dataset Access

Datasets are owned by whoever uploaded them (`metadata_tables.owner_id`). Owners — and any admin — can grant read access to other users.

1. Navigate to `http://localhost:5000/dashboard/search` and find the dataset's metadata-table ID (visible to admins/owners).
2. Open `http://localhost:5000/admin/datasets/<dataset_id>/grants`.
3. Pick a user from the *Grant access* dropdown and submit. The grantee can now read that dataset via `/search`, `/display`, `/table_preview`, and the `get-dataset-visualization` edge function.
4. To revoke, click *Revoke* next to the user in the grants list.

Grants are scoped per dataset; there is no "read everything" grant short of the `admin` role. Every grant/revoke is recorded in `_fd.grant_audit`.

### Step 5 — Audit Changes

Two append-only audit tables capture every privileged action:

| Table              | Captures                                                                     |
|--------------------|------------------------------------------------------------------------------|
| `_fd.role_audit`   | `user_id`, `old_role`, `new_role`, `changed_by`, `changed_at`                |
| `_fd.grant_audit`  | `dataset_id`, `user_id`, `action` (`granted`/`revoked`), `changed_by`, `at`  |

Inspect them via Supabase Studio (`http://localhost:8000` → Table Editor → `_fd` schema) or directly:

```bash
docker compose exec db psql -U postgres -c \
  "SELECT * FROM _fd.role_audit ORDER BY changed_at DESC LIMIT 20;"
```

Both tables are written by the Flask handlers in `backend/src/admin/form.py`. They are not exposed via the web UI — read them in Postgres if you need a compliance trail.

### Service Ports Reference

| Port  | Service                | Bound by             | Used for                                                |
|-------|------------------------|----------------------|---------------------------------------------------------|
| 5000  | Flask app              | `flask-app` container | User-facing UI; admin console; auth routes              |
| 8000, 8443 | Supabase Kong (gateway)| `kong` container | Supabase API (auth, edge functions) **and** Studio at `/` (dashboard login). **This machine only** (`127.0.0.1`) |
| 5433  | PostgreSQL (host map)  | `db` container       | Host Flask → DB; `psql` from your machine. **This machine only** (`127.0.0.1`) |
| 5432, 6543 | Connection pooler (supavisor) | `supavisor` container | Pooled DB connections. **This machine only** (`127.0.0.1`) |

Only the app (5000) is reachable from other machines. Studio (container port 3000) is deliberately **not** published: it has no login of its own, so it is reached only through Kong on 8000, which asks for the dashboard password. Kong and the database ports listen on `127.0.0.1` only; the app reaches them over the internal Docker network. To use Studio or `psql` from another computer, open an SSH tunnel (e.g. `ssh -L 8000:127.0.0.1:8000 -L 5433:127.0.0.1:5433 you@server`). The dashboard password travels as plain HTTP, which a tunnel encrypts; do not publish 8000 to the network without TLS in front.

If any of these collide with another service on the host, change the host-side port mapping in `backend/docker-compose.yml` (left side of `host:container`). Do **not** change the in-container ports or `POSTGRES_PORT` in `.env` — they are referenced by other Supabase services.

### Operational Notes

- **Defense in depth.** RBAC is enforced at three layers: the Flask `@login_required(*roles)` decorator, handler-side ownership/grant checks (`backend/src/dashboard/helpers.py`), and Postgres RLS policies (`backend/rbac_schema.sql`). Flask connects as `postgres`, which in the Supabase image is **not** a superuser but does bypass RLS (`BYPASSRLS`), so RLS protects only direct DB / edge-function callers — layers 1 and 2 are load-bearing for the web app.
- **Who owns the app's tables.** On a brand-new database the core schemas are created by `supabase_admin`, which would leave the app unable to write its own tables. The `db-init` service fixes this on every `docker compose up` by handing everything in the `_fd` and `_demo` schemas to `postgres` (`backend/volumes/db/fd_ownership.sql`, generated by `bootstrap.sh`). If the app logs `must be owner of ...` or `permission denied for table user_roles`, re-run `bash scripts/bootstrap.sh` (without `--auto`) and `docker compose up -d`.
- **Edge functions** at `/functions/v1/get-dataset-stats` and `/functions/v1/get-dataset-visualization` re-check role + ownership/grant via `supabase/functions/_shared/authz.ts`. They are safe to expose to first-party clients (e.g. an institute portal) using a user JWT.
- **Schema migrations** for the RBAC tables live in `backend/rbac_schema.sql` and re-apply on every Flask boot. Safe to re-run; no destructive operations.
- **Disabling auto-promotion.** Once your team is set up, you can leave `ADMIN_EMAIL` set (idempotent re-assertion) or clear it. Clearing has no effect on existing roles — it only stops the boot-time check.

---

## Application Routes

### Authentication

#### `/auth/login` (**POST**) – Logs in a user. Form fields:

- `email` (string)
- `password` (string)
- `csrf_token` (string) — from the login page; see [Scripting the app with curl](#scripting-the-app-with-curl)

#### Responses:
- **200**: Redirect to dashboard upon successful login.
- **400**: Missing username or password in the request.
- **401**: Invalid username or password.
- **429**: Too many requests (rate-limited).

#### `/auth/logout` (**POST**) – Logs out and clears the session. Form field `csrf_token`. A GET returns 405.

#### `/auth/register` (**POST**) – Registers a new user. Requires a JSON body with the following fields:
- `email` (string)
- `username` (string)
- `password` (string)

In addition to that, both `email` and `username` must be unique.

#### Responses:
- **200**: Redirect to homepage upon successful registration.
- **400**: Missing form data or weak password.
- **429**: Too many requests (rate-limited).
- **500**: Internal server error (including retryable errors).

---

### Dashboard

#### `/dashboard` (**GET**) – Displays the user dashboard. Any authenticated user.

#### Responses:
- **200**: Renders the dashboard page with the user's email and the current request path.
- **401**: User not logged in.

#### `/upload` (**POST**) – Uploads a CSV file, processes it, and stores chunks in PostgreSQL tables. **Requires: admin, curator**

File must be multipart form-data with:
- `file` (file): The CSV file to upload. Required.
- `description` (string, optional): Description of the file.
- `origin` (string, optional): Source or origin of the data.

#### Responses:
- **200**: File uploaded and processed successfully.
- **400**: Error during file processing (missing file, invalid CSV format, etc.).
- **401**: User not logged in.
- **403**: User does not have upload permission (not admin or curator).

#### `/search` (**GET**, **POST**) – Search and display table names. **Requires: admin, curator, accessor**

Curators see only tables they own; accessors see only tables they've been granted access to.

#### Parameters:
- `search` (formData, string, optional): Column name to search for.
- `value0`, `value1` (formData, string, optional): Filter values for search results.

#### Responses:
- **200**: Renders search page with matching table names.
- **401**: User not logged in.
- **403**: User does not have read permission.

#### `/display` (**GET**, **POST**) – Download filtered database tables as zipped CSV files. **Requires: admin, curator, accessor**

Returns only tables the user is authorized to read. Same access controls as `/search`.

#### Parameters:
- `search_term` (session, array): Search parameters `[column_name, match_value, is_zero_filter]`.

#### Responses:
- **200**: ZIP file containing matched CSVs.
- **400**: Invalid input or query failure.
- **401**: User not logged in.
- **403**: User not authorized to access one or more tables (returns 404 to avoid existence leak).
- **404**: No matching data found.
- **500**: Query execution failure.

#### `/table_preview` (**GET**) – Preview table data and metadata statistics. **Requires: admin, curator, accessor**

#### Parameters:
- `table_name` (query, string, required): Table to preview.
- `search_term` (session, string, optional): Search term from previous query.

#### Responses:
- **200**: Table preview with statistics (first 15 rows, 8 columns).
- **400**: Table name missing.
- **401**: User not logged in.
- **403**: User not authorized to access this table (returned as 404 to avoid existence leak).
- **404**: Table not found.
- **500**: Data fetching error.

#### `/update` (**POST**) – Update data in a dataset. **Requires: admin, curator (only owns)**

#### Parameters:
- `row_id` (formData, string): ID of row to update.
- `column_name` (formData, string): Column to modify.
- `new_value` (formData, string): New value.

#### Responses:
- **200**: Renders update page.
- **401**: User not logged in.
- **403**: User cannot modify this dataset.
- **404**: Column or data not found.
- **500**: Update failed.

#### `/return_to_dashboard` (**GET**) – Reset session flags and return to dashboard. Any authenticated user.

#### Responses:
- **200**: Dashboard page with flags reset.
- **401**: User not logged in.

---

### Data Management

#### `/data_generalization` (**GET**, **POST**) – Data generalization workflow. **Requires: admin, curator**

Users can upload CSV files, review and drop columns, address missing values, select quasi-identifiers, and perform mappings.

#### Parameters:
- `file` (formData, file): CSV file to upload (optional).
- `submit_button` (formData, string): Action identifier (required).

#### Responses:
- **200**: Data generalization form rendered, or after successful upload/submission.
- **400**: Bad input, session error, or expired session.
- **401**: User not authenticated.
- **403**: User does not have data generalization permission (not admin or curator).

#### `/consolidated_return` (**GET**, **POST**) – Workflow step transitions. **Requires: admin, curator**

Updates session state and redirects.

#### Parameters:
- `state` (formData, string): Step identifier (`"1"`, `"2"`, `"3"`, `"4"`).

#### Responses:
- **302**: Redirect to `/data_generalization` with updated session.
- **403**: User not authorized.

#### `/p29score` (**GET**, **POST**) – Calculate p29 privacy risk score. **Requires: admin, curator, accessor**

Computes privacy risk based on quasi-identifiers and sensitive attributes.

#### Parameters:
- `submit_button` (formData, string): Action (e.g., "Calculate Score").
- `quasi_identifiers` (formData, array, optional): Quasi-identifying columns.
- `sensitive_attributes` (formData, array, optional): Sensitive attribute columns.

#### Responses:
- **200**: Form rendered (GET) or score calculated (POST).
- **400**: Expired session, missing file, or overlapping column selections.
- **401**: User not authenticated.
- **403**: User not authorized.

#### `/upload_metadata/<table_name>` (**GET**, **POST**) – Upload sample metadata for a dataset. **Requires: admin, curator (owns table)**

Allows curators to attach sample metadata (e.g., taxonomy, units) to a dataset they own. Admins can upload metadata for any dataset.

#### Parameters:
- `table_name` (path, string): Name of the dataset table.
- `metadata_file` (formData, file, POST only): CSV file with sample metadata.

#### Responses:
- **200**: Metadata upload form (GET) or success (POST).
- **401**: User not authenticated.
- **403**: User cannot modify this table (not owner or admin).
- **404**: Table not found.

---

### Index Route

`/` (**GET**) – Renders the homepage based on whether the user is authenticated.

#### Responses:
- **200**:
  - If the user is logged in (`"user"` in session): renders `/dashboard/dashboard.html`.
  - If the user is not logged in: renders `/auth/login.html`.
- **401**: Not explicitly returned, but unauthenticated access implicitly results in rendering the login page.

---

### Privacy Processing Routes

#### `/privacy_processing` (**GET**) – Compute privacy metrics. **Requires: admin, curator, accessor**

Computes and displays privacy enforcement results: p29 score, k-anonymity, l-diversity, t-closeness.

#### Responses:
- **200**: Renders privacy metrics with top-10 problems and reasons.
- **400**: Uploaded file missing, empty, or unreadable; expired session.
- **401**: User not authenticated.
- **403**: User not authorized.

---

#### `/differential_privacy` (**GET**, **POST**) – Apply differential privacy noise. **Requires: admin, curator**

Adds noise to selected columns of the uploaded dataset.

#### Responses:
- **200**: GET renders form; POST applies noise and re-renders with confirmation.
- **400**: File missing/unreadable or invalid column selection.
- **401**: User not authenticated.
- **403**: User not authorized.

---

### Admin Routes

#### `/admin/users` (**GET**) – User role management console. **Requires: admin**

Lists all Supabase users with their current roles (admin, curator, accessor, visualizer).

#### Responses:
- **200**: Renders user list with role assignment form.
- **401**: User not authenticated.
- **403**: User is not admin.

#### `/admin/users/<user_id>/role` (**POST**) – Assign or change a user's role. **Requires: admin**

#### Parameters:
- `user_id` (path, string): UUID of target user.
- `role` (formData, string): New role (`admin`, `curator`, `accessor`, or `visualizer`).

#### Responses:
- **302**: Redirect to `/admin/users` with success or error message.
- **400**: Invalid role value.
- **401**: User not authenticated.
- **403**: User is not admin.

#### `/admin/datasets/<dataset_id>/grants` (**GET**) – View and manage dataset access grants. **Requires: admin, curator (owns dataset)**

Admins can manage any dataset; curators can only manage datasets they own.

#### Parameters:
- `dataset_id` (path, int): Metadata table ID of the dataset.

#### Responses:
- **200**: Renders grants page with current grantees and available users.
- **401**: User not authenticated.
- **403**: User cannot manage this dataset.
- **404**: Dataset not found or user not authorized.

#### `/admin/datasets/<dataset_id>/grants` (**POST**) – Grant dataset access to a user. **Requires: admin, curator (owns dataset)**

#### Parameters:
- `dataset_id` (path, int): Metadata table ID.
- `user_id` (formData, string): UUID of user to grant access.

#### Responses:
- **302**: Redirect to grants page with success/error message.
- **400**: Missing user_id or invalid input.
- **401**: User not authenticated.
- **403**: User cannot manage this dataset.

#### `/admin/datasets/<dataset_id>/grants/<user_id>/revoke` (**POST**) – Revoke dataset access. **Requires: admin, curator (owns dataset)**

#### Parameters:
- `dataset_id` (path, int): Metadata table ID.
- `user_id` (path, string): UUID of user to revoke access from.

#### Responses:
- **302**: Redirect to grants page with success/error message.
- **401**: User not authenticated.
- **403**: User cannot manage this dataset.
- **404**: Grant not found.

---

### Edge Functions (Supabase)

Edge functions enforce role-based authorization independently of the Flask backend (defense-in-depth).

#### `/functions/v1/get-dataset-stats` (**POST**) – Aggregate dataset statistics. **Requires: authenticated JWT**

Returns statistics for all datasets the caller is authorized to read.

**Authorization:** Requests must include a valid Supabase JWT in the `Authorization: Bearer <token>` header. Service-role tokens see all datasets; user tokens see only their own + granted datasets.

#### Request:
```json
{ }
```

#### Responses:
- **200**: JSON array of dataset statistics (row count, column count, etc.).
- **400**: Query execution error.
- **401**: Missing or invalid Authorization header.
- **500**: Database connection error.

#### `/functions/v1/get-dataset-visualization` (**POST**) – Visualization data for a dataset. **Requires: authenticated JWT**

Returns visualization metadata for a specific table if the caller is authorized.

**Authorization:** User must own the dataset or have an explicit grant. Non-existent datasets return 404 (not 403) to avoid leaking existence.

#### Request:
```json
{
  "table_name": "mydata_p1"
}
```

#### Responses:
- **200**: Visualization data for the requested table.
- **400**: Missing table_name or query error.
- **401**: Missing or invalid Authorization header.
- **403**: User not authorized to access this table (also returned for non-existent tables to avoid existence leaks).
- **500**: Database error.
