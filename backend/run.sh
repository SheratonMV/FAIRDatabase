#!/usr/bin/env bash
source venv/bin/activate
set -a
source ./.env
set +a

# backend/.env holds the addresses the containers use to reach each other
# (db:5432, kong:8000). Flask on the host reaches the same services through
# the ports Docker publishes on this machine, so swap them here instead of
# asking anyone to edit .env (POSTGRES_PORT in .env is also the port Postgres
# listens on inside Docker; changing it there breaks the whole stack).
if [[ "${POSTGRES_HOST}" == "db" ]]; then
    export POSTGRES_HOST=127.0.0.1
    export POSTGRES_PORT=5433            # host side of db's "127.0.0.1:5433:5432"
fi
if [[ "${SUPABASE_URL}" == "http://kong:8000" ]]; then
    export SUPABASE_URL="http://localhost:${KONG_HTTP_PORT:-8000}"
fi

export PYTHONPATH=$(pwd)/..
flask run
