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

if [[ "${1:-}" == "--auto" ]]; then
    AUTO_MODE=true
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

# --- Step 2: Auto-generate derived secrets ---

echo "[GENERATE] Creating derived secrets ..."

JWT_SECRET=$(generate_password)$(generate_password)
SECRET_KEY_BASE=$(generate_password)$(generate_password)
VAULT_ENC_KEY=$(generate_password | head -c 32)

ANON_KEY=$(generate_jwt "anon" "$JWT_SECRET")
SERVICE_ROLE_KEY=$(generate_jwt "service_role" "$JWT_SECRET")

echo "  JWT_SECRET: generated"
echo "  ANON_KEY: generated"
echo "  SERVICE_ROLE_KEY: generated"

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
PGRST_DB_SCHEMAS=public,_fd,storage,graphql_public

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

# Flask-specific Supabase vars
SUPABASE_URL=http://kong:8000
SUPABASE_KEY=$ANON_KEY
SUPABASE_SERVICE_ROLE_KEY=$SERVICE_ROLE_KEY
POSTGRES_USER=postgres
POSTGRES_SECRET=$POSTGRES_PASSWORD
POSTGRES_DB_NAME=postgres

# --- Federated Learning ---
FED_API_BASE=${FED_API_BASE:-http://host.docker.internal:7070}

# --- CORS ---
ALLOWED_ORIGINS=http://localhost:5000,http://localhost:3000
ENVEOF

echo ""
echo "  Dashboard login: supabase / $DASHBOARD_PASSWORD"

# --- Step 2: Create volumes directory structure ---

echo "[CREATE] Setting up $VOLUMES_DIR ..."

mkdir -p "$VOLUMES_DIR"/{api,db/data,functions/main,logs,pooler,storage}

# --- Kong API Gateway Config ---
cat > "$VOLUMES_DIR/api/kong.yml" << 'KONGEOF'
_format_version: '1.1'

consumers:
  - username: DASHBOARD
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

-- Supabase super admin
ALTER USER supabase_admin WITH PASSWORD :'pgpass';

-- Authenticator role (used by PostgREST)
ALTER USER authenticator WITH PASSWORD :'pgpass';

-- Supabase auth admin
ALTER USER supabase_auth_admin WITH PASSWORD :'pgpass';

-- Supabase storage admin
ALTER USER supabase_storage_admin WITH PASSWORD :'pgpass';

-- Dashboard user
ALTER USER supabase_admin WITH PASSWORD :'pgpass';
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
# This is evaluated by Supavisor at startup

{:ok, _} = Supavisor.Tenants.create_tenant(%{
  "id" => System.get_env("POOLER_TENANT_ID", "fairdatabase"),
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
})
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
echo "  $VOLUMES_DIR/db/{roles,jwt,realtime,webhooks,_supabase,logs,pooler}.sql"
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
echo "  Supabase Studio: http://localhost:3000"
echo "  Supabase API:    http://localhost:8000"
