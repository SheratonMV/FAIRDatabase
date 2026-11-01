#!/usr/bin/env bash
# bootstrap.sh - One-command setup for FAIRDatabase Docker/Podman deployment
#
# Reads admin passwords from backend/.env (set by user from .env.example),
# then auto-generates all derived secrets (JWT, API keys, internal configs)
# and creates the backend/volumes/ directory with Supabase config files.
#
# Usage:
#   1. cp backend/.env.example backend/.env   (then edit passwords)
#   2. bash scripts/bootstrap.sh
#
# Or for a fully auto-generated setup (random passwords):
#   bash scripts/bootstrap.sh --auto

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND_DIR="$REPO_ROOT/backend"
VOLUMES_DIR="$BACKEND_DIR/volumes"
ENV_FILE="$BACKEND_DIR/.env"
AUTO_MODE=false

ROTATE_SECRETS=false

for arg in "$@"; do
    case "$arg" in
        --auto) AUTO_MODE=true ;;
        --rotate-secrets) ROTATE_SECRETS=true ;;
    esac
done

# An existing populated Postgres data volume means the internal Supabase
# roles already have passwords derived from the *original* secrets. Blindly
# regenerating JWT_SECRET / VAULT_ENC_KEY / keys here would desync the stack
# (Supavisor vault, issued JWTs) and crash-loop services on next `up`.
DB_DATA_DIR="$BACKEND_DIR/volumes/db/data"
DB_VOLUME_EXISTS=false
# Postgres makes this folder private to its own container user, so on a real
# install we usually cannot look inside (testing for PG_VERSION silently
# fails). Treat "exists but unreadable" or "not empty" as an existing
# database; only a missing or empty folder (as this script creates it) is new.
if [[ -d "$DB_DATA_DIR" ]]; then
    if [[ ! -r "$DB_DATA_DIR" || ! -x "$DB_DATA_DIR" ]] \
        || [[ -n "$(ls -A "$DB_DATA_DIR" 2>/dev/null)" ]]; then
        DB_VOLUME_EXISTS=true
    fi
fi
RESET_HINT="cd '$BACKEND_DIR' && docker compose down && sudo rm -rf '$DB_DATA_DIR'"

# --auto invents a new POSTGRES_PASSWORD. An existing database still expects
# the old one, so every Supabase service would fail to log in and restart
# forever. Stop before writing anything.
if [[ "$AUTO_MODE" == true && "$DB_VOLUME_EXISTS" == true ]]; then
    echo ""
    echo "[ERROR] --auto refused: a database already exists at"
    echo "        $DB_DATA_DIR"
    echo "  --auto would generate a new database password that the existing"
    echo "  database does not know, and the stack would stop working."
    echo "  Either:"
    echo "    - re-run WITHOUT --auto (reuses the passwords in backend/.env):"
    echo "        bash scripts/bootstrap.sh"
    echo "    - or start from scratch (DELETES ALL DATA):"
    echo "        $RESET_HINT"
    exit 1
fi

# --- Helper functions ---

generate_password() {
    openssl rand -base64 32 | tr -d '/+=' | head -c 32
}

generate_jwt() {
    local role="$1"
    local secret="$2"
    local header
    header=$(printf '{"alg":"HS256","typ":"JWT"}' | openssl base64 -e | tr -d '=' | tr '/+' '_-' | tr -d '\n')
    local now
    now=$(date +%s)
    local exp=$((now + 315360000))  # 10 years
    local payload
    payload=$(printf '{"role":"%s","iss":"supabase","iat":%d,"exp":%d}' "$role" "$now" "$exp" | openssl base64 -e | tr -d '=' | tr '/+' '_-' | tr -d '\n')
    local signature
    signature=$(printf '%s.%s' "$header" "$payload" | openssl dgst -sha256 -hmac "$secret" -binary | openssl base64 -e | tr -d '=' | tr '/+' '_-' | tr -d '\n')
    printf '%s.%s.%s' "$header" "$payload" "$signature"
}

# Read a variable from existing .env, return empty if not found or set to placeholder
read_env_var() {
    local var_name="$1"
    if [[ -f "$ENV_FILE" ]]; then
        local val
        val=$(grep -E "^${var_name}=" "$ENV_FILE" 2>/dev/null | tail -1 | cut -d= -f2-)
        # Treat placeholder values as empty
        if [[ "$val" == "change-me" || "$val" == "change-me-flask-secret" ]]; then
            echo ""
        else
            echo "$val"
        fi
    fi
}

echo "=== FAIRDatabase Bootstrap ==="
echo "Repo root: $REPO_ROOT"

# --- Step 1: Read admin passwords or generate them ---

if [[ "$AUTO_MODE" == true ]]; then
    echo "[AUTO] Generating all passwords automatically ..."
    POSTGRES_PASSWORD=$(generate_password)
    DASHBOARD_PASSWORD=$(generate_password | head -c 16)
    FLASK_SECRET_KEY=$(generate_password)
    SITE_URL="http://localhost:5000"
    SMTP_HOST=""
    SMTP_PORT="2500"
    SMTP_USER=""
    SMTP_PASS=""
    SMTP_ADMIN_EMAIL="admin@example.com"
    SMTP_SENDER_NAME="FAIRDatabase"
    DISABLE_SIGNUP="false"
    ENABLE_EMAIL_AUTOCONFIRM="true"
    FED_API_BASE="http://host.docker.internal:7070"
    # Settings the operator chose by hand survive an --auto re-run.
    ADMIN_EMAIL=$(read_env_var "ADMIN_EMAIL")
    ADMIN_BOOTSTRAP_ALLOW_AUTOCONFIRM=$(read_env_var "ADMIN_BOOTSTRAP_ALLOW_AUTOCONFIRM")
    ADMIN_BOOTSTRAP_ALLOW_AUTOCONFIRM=${ADMIN_BOOTSTRAP_ALLOW_AUTOCONFIRM:-true}
    FAIRDB_PLUGINS=$(read_env_var "FAIRDB_PLUGINS")
    FAIRDB_PLUGINS_DISABLED=$(read_env_var "FAIRDB_PLUGINS_DISABLED")
elif [[ -f "$ENV_FILE" ]]; then
    echo "[READ] Reading admin passwords from $ENV_FILE ..."

    POSTGRES_PASSWORD=$(read_env_var "POSTGRES_PASSWORD")
    DASHBOARD_PASSWORD=$(read_env_var "DASHBOARD_PASSWORD")
    FLASK_SECRET_KEY=$(read_env_var "SECRET_KEY")
    SITE_URL=$(read_env_var "SITE_URL")
    SMTP_HOST=$(read_env_var "SMTP_HOST")
    SMTP_PORT=$(read_env_var "SMTP_PORT")
    SMTP_USER=$(read_env_var "SMTP_USER")
    SMTP_PASS=$(read_env_var "SMTP_PASS")
    SMTP_ADMIN_EMAIL=$(read_env_var "SMTP_ADMIN_EMAIL")
    SMTP_SENDER_NAME=$(read_env_var "SMTP_SENDER_NAME")
    DISABLE_SIGNUP=$(read_env_var "DISABLE_SIGNUP")
    ENABLE_EMAIL_AUTOCONFIRM=$(read_env_var "ENABLE_EMAIL_AUTOCONFIRM")
    FED_API_BASE=$(read_env_var "FED_API_BASE")
    # Required by _bootstrap_admin on every Flask boot to (re)promote the
    # admin user. Must be preserved across re-runs or the admin silently
    # loses their role.
    ADMIN_EMAIL=$(read_env_var "ADMIN_EMAIL")
    ADMIN_BOOTSTRAP_ALLOW_AUTOCONFIRM=$(read_env_var "ADMIN_BOOTSTRAP_ALLOW_AUTOCONFIRM")
    # Plugin selection — preserved across re-runs so an operator's choice of
    # which plugins to load isn't silently reset on every bootstrap.
    FAIRDB_PLUGINS=$(read_env_var "FAIRDB_PLUGINS")
    FAIRDB_PLUGINS_DISABLED=$(read_env_var "FAIRDB_PLUGINS_DISABLED")

    # Validate required passwords are set
    if [[ -z "$POSTGRES_PASSWORD" || -z "$DASHBOARD_PASSWORD" || -z "$FLASK_SECRET_KEY" ]]; then
        echo ""
        echo "[ERROR] Required passwords not set in $ENV_FILE."
        echo "  Please edit backend/.env and set these values:"
        [[ -z "$POSTGRES_PASSWORD" ]] && echo "    POSTGRES_PASSWORD=<your-database-password>"
        [[ -z "$DASHBOARD_PASSWORD" ]] && echo "    DASHBOARD_PASSWORD=<your-dashboard-password>"
        [[ -z "$FLASK_SECRET_KEY" ]] && echo "    SECRET_KEY=<your-flask-secret>"
        echo ""
        echo "  Or run with --auto to generate random passwords:"
        echo "    bash scripts/bootstrap.sh --auto"
        exit 1
    fi

    # Same rule the app applies at startup (config.require_strong_secret_key).
    # Checking here stops a weak key before the app container starts and
    # restarts in a loop.
    case "$(echo "$FLASK_SECRET_KEY" | tr '[:upper:]' '[:lower:]')" in
        supersecret|change-me-in-production|your-flask-secret|dev|secret) WEAK_KEY=true ;;
        *) WEAK_KEY=false ;;
    esac
    if [[ "$WEAK_KEY" == true || ${#FLASK_SECRET_KEY} -lt 16 ]]; then
        echo ""
        echo "[ERROR] SECRET_KEY in $ENV_FILE is too short (under 16 characters)"
        echo "        or a well-known placeholder. The app refuses to start with it."
        echo "  Generate one and paste it into backend/.env:"
        echo "    openssl rand -base64 32"
        exit 1
    fi

    echo "  POSTGRES_PASSWORD: set"
    echo "  DASHBOARD_PASSWORD: set"
    echo "  SECRET_KEY: set"
else
    echo ""
    echo "[ERROR] No .env file found at $ENV_FILE"
    echo ""
    echo "  Quick start:"
    echo "    cp backend/.env.example backend/.env"
    echo "    # Edit backend/.env and set your passwords"
    echo "    bash scripts/bootstrap.sh"
    echo ""
    echo "  Or auto-generate everything:"
    echo "    bash scripts/bootstrap.sh --auto"
    exit 1
fi

# --- Step 2: Derive secrets (idempotent) ---
#
# These are preserved across re-runs by reading them back from .env, exactly
# like POSTGRES_PASSWORD. Regenerating them against an existing DB volume
# desyncs the Supavisor vault and invalidates issued JWTs, which crash-loops
# Supabase services. Pass --rotate-secrets to force fresh values (only safe
# on a fresh volume, or paired with the documented repair path).

JWT_SECRET=$(read_env_var "JWT_SECRET")
SECRET_KEY_BASE=$(read_env_var "SECRET_KEY_BASE")
VAULT_ENC_KEY=$(read_env_var "VAULT_ENC_KEY")
ANON_KEY=$(read_env_var "ANON_KEY")
SERVICE_ROLE_KEY=$(read_env_var "SERVICE_ROLE_KEY")

HAVE_ALL_SECRETS=true
for s in "$JWT_SECRET" "$SECRET_KEY_BASE" "$VAULT_ENC_KEY" "$ANON_KEY" "$SERVICE_ROLE_KEY"; do
    [[ -z "$s" ]] && HAVE_ALL_SECRETS=false
done

if [[ "$ROTATE_SECRETS" == true && "$DB_VOLUME_EXISTS" == true ]]; then
    echo ""
    echo "[ERROR] --rotate-secrets refused: an existing DB volume was found at"
    echo "        $DB_DATA_DIR"
    echo "  Rotating JWT_SECRET / VAULT_ENC_KEY against existing internal-role"
    echo "  passwords will crash-loop Supabase. Either:"
    echo "    - wipe the volume (DESTROYS DATA): $RESET_HINT && re-run, or"
    echo "    - follow the existing-volume repair path in readme.md."
    exit 1
fi

if [[ "$HAVE_ALL_SECRETS" == true && "$ROTATE_SECRETS" != true ]]; then
    echo "[KEEP] Reusing existing derived secrets from $ENV_FILE (idempotent)."
else
    if [[ "$DB_VOLUME_EXISTS" == true && "$AUTO_MODE" != true ]]; then
        echo ""
        echo "[ERROR] Derived secrets are missing/incomplete but an existing DB"
        echo "        volume was found at $DB_DATA_DIR."
        echo "  Generating new secrets now would desync the existing database."
        echo "  Restore the original secrets into $ENV_FILE, or follow the"
        echo "  existing-volume repair path in readme.md."
        exit 1
    fi
    echo "[GENERATE] Creating derived secrets ..."
    JWT_SECRET=$(generate_password)$(generate_password)
    SECRET_KEY_BASE=$(generate_password)$(generate_password)
    VAULT_ENC_KEY=$(generate_password | head -c 32)
    ANON_KEY=$(generate_jwt "anon" "$JWT_SECRET")
    SERVICE_ROLE_KEY=$(generate_jwt "service_role" "$JWT_SECRET")
fi

echo "  JWT_SECRET: set"
echo "  ANON_KEY: set"
echo "  SERVICE_ROLE_KEY: set"

# --- Step 3: Write complete .env ---

echo "[WRITE] Writing $ENV_FILE ..."

cat > "$ENV_FILE" << ENVEOF
# =============================================================================
# FAIRDatabase Environment Configuration
# Generated by bootstrap.sh on $(date -u +"%Y-%m-%dT%H:%M:%SZ")
#
# Admin passwords (from your .env.example):
#   POSTGRES_PASSWORD, DASHBOARD_PASSWORD, SECRET_KEY
#
# Everything else was auto-generated. Do not edit unless you know what
# you are doing. To regenerate, run: bash scripts/bootstrap.sh
# =============================================================================

# --- Admin Passwords (from .env.example) ---
POSTGRES_PASSWORD=$POSTGRES_PASSWORD
DASHBOARD_PASSWORD=$DASHBOARD_PASSWORD

# --- PostgreSQL ---
POSTGRES_HOST=db
# Port Postgres listens on INSIDE Docker. Do not change: every Supabase
# service uses it. Flask on the host gets 127.0.0.1:5433 from run.sh.
POSTGRES_PORT=5432
POSTGRES_DB=postgres

# --- Supabase JWT (auto-generated) ---
JWT_SECRET=$JWT_SECRET
JWT_EXPIRY=3600
ANON_KEY=$ANON_KEY
SERVICE_ROLE_KEY=$SERVICE_ROLE_KEY

# --- Supabase API ---
SITE_URL=${SITE_URL:-http://localhost:5000}
API_EXTERNAL_URL=http://localhost:8000
SUPABASE_PUBLIC_URL=http://localhost:8000
ADDITIONAL_REDIRECT_URLS=
DISABLE_SIGNUP=${DISABLE_SIGNUP:-false}

# --- Supabase Studio ---
STUDIO_DEFAULT_ORGANIZATION=FAIRDatabase
STUDIO_DEFAULT_PROJECT=FAIRDatabase
DASHBOARD_USERNAME=supabase
STUDIO_PORT=3000

# --- Supabase Auth (Email) ---
ENABLE_EMAIL_SIGNUP=true
ENABLE_EMAIL_AUTOCONFIRM=${ENABLE_EMAIL_AUTOCONFIRM:-true}
ENABLE_ANONYMOUS_USERS=false

# --- Supabase Auth (Phone - disabled) ---
ENABLE_PHONE_SIGNUP=false
ENABLE_PHONE_AUTOCONFIRM=false

# --- SMTP ---
SMTP_ADMIN_EMAIL=${SMTP_ADMIN_EMAIL:-admin@example.com}
SMTP_HOST=${SMTP_HOST:-}
SMTP_PORT=${SMTP_PORT:-2500}
SMTP_USER=${SMTP_USER:-}
SMTP_PASS=${SMTP_PASS:-}
SMTP_SENDER_NAME=${SMTP_SENDER_NAME:-FAIRDatabase}

# --- Supabase Mailer URLs ---
MAILER_URLPATHS_CONFIRMATION=/auth/v1/verify
MAILER_URLPATHS_INVITE=/auth/v1/verify
MAILER_URLPATHS_RECOVERY=/auth/v1/verify
MAILER_URLPATHS_EMAIL_CHANGE=/auth/v1/verify

# --- Kong API Gateway ---
KONG_HTTP_PORT=8000
KONG_HTTPS_PORT=8443

# --- PostgREST ---
# _fd is deliberately absent: the app never reads it over REST, and listing it
# lets any signed-up user query app tables directly through Kong.
PGRST_DB_SCHEMAS=public,storage,graphql_public

# --- Supabase Realtime (auto-generated) ---
SECRET_KEY_BASE=$SECRET_KEY_BASE

# --- Supabase Edge Functions ---
FUNCTIONS_VERIFY_JWT=true

# --- Supabase Pooler (auto-generated) ---
POOLER_TENANT_ID=fairdatabase
POOLER_DEFAULT_POOL_SIZE=20
POOLER_MAX_CLIENT_CONN=100
POOLER_PROXY_PORT_TRANSACTION=6543
VAULT_ENC_KEY=$VAULT_ENC_KEY

# --- Docker / Podman ---
DOCKER_SOCKET_LOCATION=/var/run/docker.sock

# --- Supabase Image Proxy ---
IMGPROXY_ENABLE_WEBP_DETECTION=true

# --- Logflare (analytics - disabled) ---
LOGFLARE_API_KEY=placeholder-key

# --- Flask Application ---
ENV=development
SECRET_KEY=$FLASK_SECRET_KEY
UPLOAD_FOLDER=./uploads
ALLOWED_EXTENSIONS=csv

# Auto-promoted to admin on every Flask boot (_bootstrap_admin). Preserved
# across bootstrap re-runs; leave blank to skip admin auto-promotion.
ADMIN_EMAIL=$ADMIN_EMAIL
ADMIN_BOOTSTRAP_ALLOW_AUTOCONFIRM=${ADMIN_BOOTSTRAP_ALLOW_AUTOCONFIRM:-true}

# Plugin selection (loader auto-discovers backend/plugins/* otherwise).
#   FAIRDB_PLUGINS          — allowlist; ONLY these load (empty = all).
#   FAIRDB_PLUGINS_DISABLED — denylist; applied after the allowlist.
# Folder names: pbpk, horizontal_fl. Preserved across bootstrap re-runs.
FAIRDB_PLUGINS=$FAIRDB_PLUGINS
FAIRDB_PLUGINS_DISABLED=$FAIRDB_PLUGINS_DISABLED

# Flask-specific Supabase vars
SUPABASE_URL=http://kong:8000
SUPABASE_KEY=$ANON_KEY
SUPABASE_SERVICE_ROLE_KEY=$SERVICE_ROLE_KEY
POSTGRES_USER=postgres
POSTGRES_DB_NAME=postgres

# --- Federated Learning ---
FED_API_BASE=${FED_API_BASE:-http://host.docker.internal:7070}

# --- CORS ---
ALLOWED_ORIGINS=http://localhost:5000,http://localhost:3000
ENVEOF

echo ""
echo "  Dashboard login: supabase / $DASHBOARD_PASSWORD"
if [[ -z "$ADMIN_EMAIL" ]]; then
    echo "  [WARN] ADMIN_EMAIL is blank — Flask will NOT auto-promote any"
    echo "         admin user. Set ADMIN_EMAIL in $ENV_FILE and restart Flask."
else
    echo "  Admin (auto-promoted on boot): $ADMIN_EMAIL"
    if [[ "${ENABLE_EMAIL_AUTOCONFIRM:-true}" != "false" ]]; then
        if [[ "${ADMIN_BOOTSTRAP_ALLOW_AUTOCONFIRM:-true}" == "true" ]]; then
            echo "  [WARN] Signups are not e-mail-verified, and $ADMIN_EMAIL is"
            echo "         promoted anyway (ADMIN_BOOTSTRAP_ALLOW_AUTOCONFIRM=true)."
            echo "         Whoever registers that address first becomes admin:"
            echo "         register it yourself right after the stack is up."
        else
            echo "  [WARN] Signups are not e-mail-verified, so Flask will NOT"
            echo "         promote $ADMIN_EMAIL. Either configure SMTP_* and set"
            echo "         ENABLE_EMAIL_AUTOCONFIRM=false, or set"
            echo "         ADMIN_BOOTSTRAP_ALLOW_AUTOCONFIRM=true in $ENV_FILE."
        fi
    fi
fi

# --- Step 2: Create volumes directory structure ---

echo "[CREATE] Setting up $VOLUMES_DIR ..."

mkdir -p "$VOLUMES_DIR"/{api,db/data,functions/main,logs,pooler,storage}

# --- Kong API Gateway Config ---
cat > "$VOLUMES_DIR/api/kong.yml" << 'KONGEOF'
_format_version: '1.1'

consumers:
  - username: DASHBOARD
    basicauth_credentials:
      - username: $DASHBOARD_USERNAME
        password: $DASHBOARD_PASSWORD
  - username: anon
    keyauth_credentials:
      - key: ${SUPABASE_ANON_KEY}
  - username: service_role
    keyauth_credentials:
      - key: ${SUPABASE_SERVICE_KEY}

acls:
  - consumer: anon
    group: anon
  - consumer: service_role
    group: admin

services:
  - name: auth-v1-open
    url: http://auth:9999/verify
    routes:
      - name: auth-v1-open
        strip_path: true
        paths:
          - /auth/v1/verify
    plugins:
      - name: cors
  - name: auth-v1-open-callback
    url: http://auth:9999/callback
    routes:
      - name: auth-v1-open-callback
        strip_path: true
        paths:
          - /auth/v1/callback
    plugins:
      - name: cors
  - name: auth-v1-open-authorize
    url: http://auth:9999/authorize
    routes:
      - name: auth-v1-open-authorize
        strip_path: true
        paths:
          - /auth/v1/authorize
    plugins:
      - name: cors
  - name: auth-v1
    url: http://auth:9999/
    routes:
      - name: auth-v1-all
        strip_path: true
        paths:
          - /auth/v1/
    plugins:
      - name: cors
      - name: key-auth
        config:
          hide_credentials: false
      - name: acl
        config:
          hide_groups_header: true
          allow:
            - admin
            - anon

  - name: rest-v1
    url: http://rest:3000/
    routes:
      - name: rest-v1-all
        strip_path: true
        paths:
          - /rest/v1/
    plugins:
      - name: cors
      - name: key-auth
        config:
          hide_credentials: true
      - name: acl
        config:
          hide_groups_header: true
          allow:
            - admin
            - anon

  - name: realtime-v1-ws
    url: http://realtime-dev.supabase-realtime:4000/socket/
    routes:
      - name: realtime-v1-ws
        strip_path: true
        paths:
          - /realtime/v1/
    plugins:
      - name: cors
      - name: key-auth
        config:
          hide_credentials: false
      - name: acl
        config:
          hide_groups_header: true
          allow:
            - admin
            - anon

  - name: storage-v1
    url: http://storage:5000/
    routes:
      - name: storage-v1-all
        strip_path: true
        paths:
          - /storage/v1/
    plugins:
      - name: cors
      - name: key-auth
        config:
          hide_credentials: false
      - name: acl
        config:
          hide_groups_header: true
          allow:
            - admin
            - anon

  - name: functions-v1
    url: http://functions:8000/
    routes:
      - name: functions-v1-all
        strip_path: true
        paths:
          - /functions/v1/
    plugins:
      - name: cors
      - name: key-auth
        config:
          hide_credentials: false
      - name: acl
        config:
          hide_groups_header: true
          allow:
            - admin
            - anon

  - name: meta
    url: http://meta:8080/
    routes:
      - name: meta-all
        strip_path: true
        paths:
          - /pg/
    plugins:
      - name: key-auth
        config:
          hide_credentials: false
      - name: acl
        config:
          hide_groups_header: true
          allow:
            - admin

  - name: dashboard
    url: http://studio:3000/
    routes:
      - name: dashboard-all
        strip_path: true
        paths:
          - /
    plugins:
      - name: cors
      - name: basic-auth
        config:
          hide_credentials: true
KONGEOF

# --- DB Init Scripts ---

cat > "$VOLUMES_DIR/db/roles.sql" << 'SQLEOF'
-- Roles required for Supabase self-hosting
-- NOTE: These roles are created automatically by the supabase/postgres image
-- This file ensures they exist if using a custom Postgres instance

\set pgpass `echo "$POSTGRES_PASSWORD"`

-- Re-sync every internal Supabase role to the current POSTGRES_PASSWORD.
-- Must cover ALL roles the services authenticate as, else the missing ones
-- fail with SASL / 28P01 on an existing volume. Plain ALTER USER: psql does
-- NOT substitute :'pgpass' inside DO $$...$$ blocks. These roles always
-- exist on the supabase/postgres image.
ALTER USER postgres WITH PASSWORD :'pgpass';
ALTER USER supabase_admin WITH PASSWORD :'pgpass';
ALTER USER authenticator WITH PASSWORD :'pgpass';
ALTER USER supabase_auth_admin WITH PASSWORD :'pgpass';
ALTER USER supabase_storage_admin WITH PASSWORD :'pgpass';
SQLEOF

cat > "$VOLUMES_DIR/db/jwt.sql" << 'SQLEOF'
\set jwt_secret `echo "$JWT_SECRET"`
\set jwt_exp `echo "$JWT_EXP"`

ALTER DATABASE postgres SET "app.settings.jwt_secret" TO :'jwt_secret';
ALTER DATABASE postgres SET "app.settings.jwt_exp" TO :'jwt_exp';
SQLEOF

cat > "$VOLUMES_DIR/db/realtime.sql" << 'SQLEOF'
-- Realtime schema and publication setup
CREATE SCHEMA IF NOT EXISTS _realtime;
ALTER SCHEMA _realtime OWNER TO supabase_admin;
SQLEOF

cat > "$VOLUMES_DIR/db/webhooks.sql" << 'SQLEOF'
BEGIN;
  -- Create supabase_functions schema if not exists
  CREATE SCHEMA IF NOT EXISTS supabase_functions;
  ALTER SCHEMA supabase_functions OWNER TO supabase_admin;

  -- Create http_request function placeholder
  CREATE OR REPLACE FUNCTION supabase_functions.http_request()
    RETURNS trigger
    LANGUAGE plpgsql
    AS $$
    DECLARE
    BEGIN
      RETURN NEW;
    END;
    $$;

  ALTER FUNCTION supabase_functions.http_request() OWNER TO supabase_admin;

  -- Create hooks table
  CREATE TABLE IF NOT EXISTS supabase_functions.hooks (
    id bigserial PRIMARY KEY,
    hook_table_id integer NOT NULL DEFAULT 0,
    hook_name text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    request_id bigserial
  );

  ALTER TABLE supabase_functions.hooks OWNER TO supabase_admin;

  -- Create migrations table
  CREATE TABLE IF NOT EXISTS supabase_functions.migrations (
    version text PRIMARY KEY,
    inserted_at timestamptz NOT NULL DEFAULT now()
  );

  ALTER TABLE supabase_functions.migrations OWNER TO supabase_admin;
COMMIT;
SQLEOF

cat > "$VOLUMES_DIR/db/_supabase.sql" << 'SQLEOF'
-- Internal supabase schema
CREATE SCHEMA IF NOT EXISTS _supabase;
ALTER SCHEMA _supabase OWNER TO supabase_admin;
SQLEOF

cat > "$VOLUMES_DIR/db/logs.sql" << 'SQLEOF'
-- Analytics / Logs schema setup
CREATE SCHEMA IF NOT EXISTS _analytics;
ALTER SCHEMA _analytics OWNER TO supabase_admin;
SQLEOF

cat > "$VOLUMES_DIR/db/pooler.sql" << 'SQLEOF'
-- Pooler schema setup (Supavisor)
CREATE SCHEMA IF NOT EXISTS _supavisor;
ALTER SCHEMA _supavisor OWNER TO supabase_admin;
SQLEOF

# Idempotent auth schema/function ownership repair. On volumes where the
# auth schema was created by `postgres` (init scripts) instead of by GoTrue,
# the auth service's CREATE OR REPLACE FUNCTION migration fails with 42501.
cat > "$VOLUMES_DIR/db/auth_ownership.sql" << 'SQLEOF'
DO $$
BEGIN
  IF EXISTS (SELECT FROM information_schema.schemata WHERE schema_name='auth')
     AND EXISTS (SELECT FROM pg_roles WHERE rolname='supabase_auth_admin') THEN
    EXECUTE 'ALTER SCHEMA auth OWNER TO supabase_auth_admin';
  END IF;
END $$;
DO $$
DECLARE fn text;
BEGIN
  IF EXISTS (SELECT FROM pg_roles WHERE rolname='supabase_auth_admin') THEN
    FOR fn IN
      SELECT 'auth.' || p.proname || '(' ||
             pg_get_function_identity_arguments(p.oid) || ')'
      FROM pg_proc p
      JOIN pg_namespace n ON n.oid = p.pronamespace
      WHERE n.nspname = 'auth'
        AND p.proname IN ('uid','role','email','jwt')
    LOOP
      EXECUTE format('ALTER FUNCTION %s OWNER TO supabase_auth_admin', fn);
    END LOOP;
  END IF;
END $$;
SQLEOF

# Idempotent _fd/_demo ownership repair. On a fresh volume Postgres runs the
# mounted core schemas (migrate/rbac/demo) as supabase_admin, so those _fd
# tables, types and functions belong to supabase_admin. Flask logs in as
# `postgres`, which is NOT a superuser in this image, so it could not write
# _fd.user_roles (admin promotion), _fd.metadata_tables (uploads) or re-apply
# the schemas at boot ("must be owner of ..."). Hand everything in _fd and
# _demo that supabase_admin owns to postgres. Touches only those two schemas;
# safe to run every boot.
cat > "$VOLUMES_DIR/db/fd_ownership.sql" << 'SQLEOF'
DO $$
DECLARE
  sch text;
  r record;
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'postgres') THEN
    RETURN;
  END IF;

  -- The app's own schemas: _fd (datasets, roles, grants, plugins) and
  -- _demo (public demo API). Nothing else is touched.
  FOREACH sch IN ARRAY ARRAY['_fd', '_demo'] LOOP
    CONTINUE WHEN NOT EXISTS (SELECT FROM pg_namespace WHERE nspname = sch);

    IF (SELECT pg_get_userbyid(nspowner) FROM pg_namespace WHERE nspname = sch)
       = 'supabase_admin' THEN
      EXECUTE format('ALTER SCHEMA %I OWNER TO postgres', sch);
    END IF;

    -- Tables, views, materialized views. A table's own sequences (serial /
    -- identity columns) move with it.
    FOR r IN
      SELECT c.oid::regclass AS obj, c.relkind
      FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
      WHERE n.nspname = sch
        AND pg_get_userbyid(c.relowner) = 'supabase_admin'
        AND c.relkind IN ('r', 'p', 'v', 'm')
    LOOP
      EXECUTE format('ALTER %s %s OWNER TO postgres',
        CASE r.relkind WHEN 'v' THEN 'VIEW'
                       WHEN 'm' THEN 'MATERIALIZED VIEW'
                       ELSE 'TABLE' END,
        r.obj);
    END LOOP;

    -- Stand-alone sequences not tied to a table.
    FOR r IN
      SELECT c.oid::regclass AS obj
      FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
      WHERE n.nspname = sch AND c.relkind = 'S'
        AND pg_get_userbyid(c.relowner) = 'supabase_admin'
    LOOP
      EXECUTE format('ALTER SEQUENCE %s OWNER TO postgres', r.obj);
    END LOOP;

    -- Enum and domain types (e.g. _fd.user_role).
    FOR r IN
      SELECT t.oid::regtype AS obj
      FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
      WHERE n.nspname = sch
        AND pg_get_userbyid(t.typowner) = 'supabase_admin'
        AND t.typtype IN ('e', 'd')
    LOOP
      EXECUTE format('ALTER TYPE %s OWNER TO postgres', r.obj);
    END LOOP;

    -- Functions (current_role, handle_new_auth_user, ...). The SECURITY
    -- DEFINER ones then run as postgres instead of the superuser.
    FOR r IN
      SELECT p.oid::regprocedure AS obj
      FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
      WHERE n.nspname = sch
        AND pg_get_userbyid(p.proowner) = 'supabase_admin'
    LOOP
      EXECUTE format('ALTER ROUTINE %s OWNER TO postgres', r.obj);
    END LOOP;
  END LOOP;
END $$;
SQLEOF

# One-shot idempotent repair script run by the `db-init` compose service on
# every `up`, before realtime/auth/supavisor/flask start. Generated (not
# inline in compose) so Docker Compose does not $-interpolate $f / $$.
cat > "$VOLUMES_DIR/db/db-init.sh" << 'SH_EOF'
#!/bin/bash
set -u
echo "[db-init] waiting for db ..."
until pg_isready -q; do sleep 2; done

echo "[db-init] re-syncing internal role passwords (roles.sql)"
psql -v ON_ERROR_STOP=0 -f /init/roles.sql || echo "[db-init] WARN roles.sql"

echo "[db-init] ensuring _supabase database exists"
psql -tAc "SELECT 1 FROM pg_database WHERE datname='_supabase'" \
  | grep -q 1 || psql -c "CREATE DATABASE _supabase"

for f in realtime _supabase logs pooler; do
  if [ -f "/init/$f.sql" ]; then
    echo "[db-init] applying $f.sql"
    psql -v ON_ERROR_STOP=0 -f "/init/$f.sql" || echo "[db-init] WARN $f.sql"
  fi
done

# webhooks.sql touches the supabase_functions schema, which is owned by
# supabase_admin. In the supabase/postgres image `postgres` is NOT a superuser
# (supabase_admin is), so this must connect as supabase_admin or it fails with
# "permission denied for schema supabase_functions". The role's password is
# kept in sync with POSTGRES_PASSWORD by roles.sql, so the existing PGPASSWORD
# already authenticates it.
if [ -f /init/webhooks.sql ]; then
  echo "[db-init] applying webhooks.sql (as supabase_admin)"
  psql -U supabase_admin -v ON_ERROR_STOP=0 -f /init/webhooks.sql \
    || echo "[db-init] WARN webhooks.sql"
fi

# CREATE SCHEMA ... AUTHORIZATION supabase_admin makes supabase_admin the
# owner. To create an object owned by another role you must be a superuser or
# a MEMBER of that role; `postgres` is neither here, so as postgres this fails
# with "must be member of role supabase_admin" — but ONLY on a fresh volume.
# On a populated volume the schema already exists and IF NOT EXISTS skips
# before the privilege check, which masks the bug. This is the load-bearing
# line for supavisor (pooler): if it fails, the pooler crash-loops. Run it as
# supabase_admin (its password is synced to POSTGRES_PASSWORD by roles.sql).
echo "[db-init] ensuring _supavisor schema in _supabase db"
psql -U supabase_admin -d _supabase -v ON_ERROR_STOP=0 \
  -c "CREATE SCHEMA IF NOT EXISTS _supavisor AUTHORIZATION supabase_admin" \
  || echo "[db-init] WARN _supavisor schema"

if [ -f /init/auth_ownership.sql ]; then
  # ALTER SCHEMA auth OWNER ... requires ownership of the auth schema, which is
  # owned by supabase_admin (the image's real superuser). Running as postgres
  # fails with "must be owner of schema auth", so connect as supabase_admin.
  echo "[db-init] repairing auth schema/function ownership (as supabase_admin)"
  psql -U supabase_admin -v ON_ERROR_STOP=0 -f /init/auth_ownership.sql \
    || echo "[db-init] WARN auth ownership"
fi

if [ -f /init/fd_ownership.sql ]; then
  # Changing an owner away from supabase_admin needs supabase_admin (or a
  # superuser), so connect as it, like the auth repair above.
  echo "[db-init] handing _fd/_demo schema objects to postgres (as supabase_admin)"
  psql -U supabase_admin -v ON_ERROR_STOP=0 -f /init/fd_ownership.sql \
    || echo "[db-init] WARN _fd ownership"
fi

echo "[db-init] done"
SH_EOF
chmod +x "$VOLUMES_DIR/db/db-init.sh"

# --- Vector logging config ---
cat > "$VOLUMES_DIR/logs/vector.yml" << 'VECTOREOF'
api:
  enabled: true
  address: 0.0.0.0:9001

sources:
  docker_host:
    type: docker_logs
    exclude_containers:
      - supabase-vector

transforms:
  project_logs:
    type: remap
    inputs:
      - docker_host
    source: |-
      .project = "default"
      .event_message = del(.message)
      .appname = del(.container_name)
      del(.container_created_at)
      del(.container_id)
      del(.source_type)
      del(.stream)
      del(.label)
      del(.image)
      del(.host)
      del(.timestamp)

sinks:
  logflare:
    type: "http"
    inputs:
      - project_logs
    uri: "http://analytics:4000/api/logs?source_name=docker_host&api_key=${LOGFLARE_API_KEY}"
    method: "post"
    encoding:
      codec: "json"
    batch:
      max_bytes: 1049000
      timeout_secs: 2
    request:
      retry_max_duration_secs: 10
    healthcheck:
      enabled: false
VECTOREOF

# --- Pooler config ---
cat > "$VOLUMES_DIR/pooler/pooler.exs" << 'POOLEREOF'
# Supavisor pooler configuration
# This is evaluated by Supavisor at startup via `supavisor eval`.
#
# `eval` runs WITHOUT booting the OTP application, so Ecto (Supavisor.Repo)
# is not started and Tenants.create_tenant/1 would crash with
# "could not lookup Ecto repo Supavisor.Repo because it was not started".
# We must explicitly start the app first. We also make the tenant insert
# idempotent so re-running on an existing volume does not crash-loop.

{:ok, _} = Application.ensure_all_started(:supavisor)

tenant_id = System.get_env("POOLER_TENANT_ID", "fairdatabase")

params = %{
  "id" => tenant_id,
  "db_host" => "db",
  "db_port" => String.to_integer(System.get_env("POSTGRES_PORT", "5432")),
  "db_database" => System.get_env("POSTGRES_DB", "postgres"),
  "ip_version" => "auto",
  "require_user" => false,
  "upstream_tls_ca" => "",
  "upstream_verify" => "none",
  "default_max_clients" => String.to_integer(System.get_env("POOLER_MAX_CLIENT_CONN", "100")),
  "default_pool_size" => String.to_integer(System.get_env("POOLER_DEFAULT_POOL_SIZE", "20")),
  "users" => [
    %{
      "db_user" => "postgres",
      "db_password" => System.get_env("POSTGRES_PASSWORD"),
      "mode_type" => "transaction",
      "pool_size" => String.to_integer(System.get_env("POOLER_DEFAULT_POOL_SIZE", "20")),
      "pool_checkout_timeout" => 60000,
      "is_manager" => true
    }
  ]
}

case Supavisor.Tenants.get_tenant_by_external_id(tenant_id) do
  nil ->
    case Supavisor.Tenants.create_tenant(params) do
      {:ok, _} ->
        IO.puts("[pooler.exs] tenant #{tenant_id} created")

      # Tolerate a race / unique violation: another boot created it.
      {:error, %Ecto.Changeset{errors: errors}} ->
        IO.puts("[pooler.exs] tenant #{tenant_id} create skipped: #{inspect(errors)}")

      other ->
        IO.puts("[pooler.exs] tenant #{tenant_id} create returned: #{inspect(other)}")
    end

  _existing ->
    IO.puts("[pooler.exs] tenant #{tenant_id} already exists; skipping")
end
POOLEREOF

# --- Edge Functions main entrypoint ---
cat > "$VOLUMES_DIR/functions/main/index.ts" << 'FNEOF'
import { serve } from "https://deno.land/std@0.168.0/http/server.ts";

serve(async (req: Request) => {
  const url = new URL(req.url);
  const pathParts = url.pathname.split("/").filter(Boolean);

  // Route to the appropriate function
  if (pathParts.length > 0) {
    const functionName = pathParts[0];
    const functionPath = `/home/deno/functions/${functionName}/index.ts`;

    try {
      const module = await import(functionPath);
      if (typeof module.default === "function") {
        return module.default(req);
      }
      // If the module uses serve() pattern, Deno edge runtime handles it
    } catch (e) {
      return new Response(
        JSON.stringify({ error: `Function '${functionName}' not found` }),
        { status: 404, headers: { "Content-Type": "application/json" } }
      );
    }
  }

  return new Response(
    JSON.stringify({ message: "FAIRDatabase Edge Functions" }),
    { status: 200, headers: { "Content-Type": "application/json" } }
  );
});
FNEOF

# --- Step 3: Copy edge functions ---

echo "[COPY] Copying edge functions to volumes ..."

if [[ -d "$REPO_ROOT/supabase/functions" ]]; then
    for fn_dir in "$REPO_ROOT/supabase/functions"/*/; do
        fn_name=$(basename "$fn_dir")
        if [[ "$fn_name" != "main" ]]; then
            mkdir -p "$VOLUMES_DIR/functions/$fn_name"
            cp -r "$fn_dir"* "$VOLUMES_DIR/functions/$fn_name/"
            echo "  Copied: $fn_name"
        fi
    done
else
    echo "  [WARN] No supabase/functions/ directory found"
fi

# --- Step 4: Create uploads directory ---

mkdir -p "$BACKEND_DIR/uploads"

# --- Done ---

echo ""
echo "=== Bootstrap Complete ==="
echo ""
echo "Files created:"
echo "  $ENV_FILE"
echo "  $VOLUMES_DIR/api/kong.yml"
echo "  $VOLUMES_DIR/db/{roles,jwt,realtime,webhooks,_supabase,logs,pooler,auth_ownership,fd_ownership}.sql"
echo "  $VOLUMES_DIR/db/db-init.sh"
echo "  $VOLUMES_DIR/logs/vector.yml"
echo "  $VOLUMES_DIR/pooler/pooler.exs"
echo "  $VOLUMES_DIR/functions/main/index.ts"
echo "  $VOLUMES_DIR/functions/{edge functions copied}"
echo ""
echo "Next steps:"
echo "  cd backend"
echo "  docker compose up -d          # Start all services"
echo "  docker compose ps             # Check service health"
echo ""
echo "Access:"
echo "  Flask app:       http://localhost:5000"
echo "  Supabase Studio: http://localhost:${KONG_HTTP_PORT:-8000} (via Kong, dashboard login)"
echo "  Supabase API:    http://localhost:8000"
