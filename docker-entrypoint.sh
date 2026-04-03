#!/bin/bash
set -e

# Source .env if it exists and was bind-mounted (dev convenience).
# In production, environment variables come from docker-compose environment/env_file.
if [ -f /app/backend/.env ]; then
    set -a
    source /app/backend/.env
    set +a
fi

exec "$@"
