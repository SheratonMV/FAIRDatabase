#!/usr/bin/env bash
# podman-setup.sh - Configure environment for running FAIRDatabase with Podman
#
# Usage:
#   bash scripts/podman-setup.sh
#   source scripts/podman-setup.sh  # to export vars into current shell

set -euo pipefail

echo "=== FAIRDatabase Podman Setup ==="

# --- Check podman-compose ---
if command -v podman-compose &>/dev/null; then
    echo "[OK] podman-compose found: $(podman-compose --version 2>&1 | head -1)"
elif command -v docker-compose &>/dev/null; then
    echo "[OK] docker-compose found (may work with Podman socket)"
else
    echo "[WARN] Neither podman-compose nor docker-compose found."
    echo "  Install: pip install podman-compose"
    echo "  Or:      sudo apt install podman-compose"
fi

# --- Check Podman version ---
if command -v podman &>/dev/null; then
    PODMAN_VERSION=$(podman --version | grep -oP '\d+\.\d+' | head -1)
    echo "[OK] Podman version: $PODMAN_VERSION"

    MAJOR=$(echo "$PODMAN_VERSION" | cut -d. -f1)
    MINOR=$(echo "$PODMAN_VERSION" | cut -d. -f2)

    if (( MAJOR < 5 )); then
        echo "[WARN] Podman < 5.0 detected."
        echo "  host.docker.internal may not resolve automatically."
        echo "  If the federated learning proxy fails, add to docker-compose.override.yml:"
        echo "    extra_hosts:"
        echo "      - \"host.docker.internal:host-gateway\""
    fi
else
    echo "[ERROR] Podman not found. Install it first."
    exit 1
fi

# --- Detect Podman socket for Vector container ---
PODMAN_SOCKET=""

# Try rootless socket first
ROOTLESS_SOCKET="/run/user/$(id -u)/podman/podman.sock"
if [[ -S "$ROOTLESS_SOCKET" ]]; then
    PODMAN_SOCKET="$ROOTLESS_SOCKET"
    echo "[OK] Rootless Podman socket: $PODMAN_SOCKET"
elif systemctl --user is-active podman.socket &>/dev/null 2>&1; then
    echo "[INFO] Podman socket service exists but socket not found. Starting..."
    systemctl --user start podman.socket
    if [[ -S "$ROOTLESS_SOCKET" ]]; then
        PODMAN_SOCKET="$ROOTLESS_SOCKET"
        echo "[OK] Rootless Podman socket started: $PODMAN_SOCKET"
    fi
fi

# Fall back to system socket
if [[ -z "$PODMAN_SOCKET" ]] && [[ -S "/run/podman/podman.sock" ]]; then
    PODMAN_SOCKET="/run/podman/podman.sock"
    echo "[OK] System Podman socket: $PODMAN_SOCKET"
fi

if [[ -z "$PODMAN_SOCKET" ]]; then
    echo "[WARN] No Podman socket found."
    echo "  The Vector (log aggregation) container needs a container socket."
    echo "  Try: systemctl --user enable --now podman.socket"
    PODMAN_SOCKET="/run/user/$(id -u)/podman/podman.sock"
    echo "  Using default path: $PODMAN_SOCKET"
fi

# --- Update .env if it exists ---
BACKEND_DIR="$(cd "$(dirname "$0")/.." && pwd)/backend"
ENV_FILE="$BACKEND_DIR/.env"

if [[ -f "$ENV_FILE" ]]; then
    if grep -q "DOCKER_SOCKET_LOCATION" "$ENV_FILE"; then
        sed -i "s|DOCKER_SOCKET_LOCATION=.*|DOCKER_SOCKET_LOCATION=$PODMAN_SOCKET|" "$ENV_FILE"
        echo "[UPDATE] Set DOCKER_SOCKET_LOCATION=$PODMAN_SOCKET in .env"
    else
        echo "DOCKER_SOCKET_LOCATION=$PODMAN_SOCKET" >> "$ENV_FILE"
        echo "[APPEND] Added DOCKER_SOCKET_LOCATION=$PODMAN_SOCKET to .env"
    fi
else
    echo "[SKIP] No .env found. Run bootstrap.sh first, then re-run this script."
fi

# --- Export for current shell ---
export DOCKER_SOCKET_LOCATION="$PODMAN_SOCKET"

echo ""
echo "=== Podman Setup Complete ==="
echo ""
echo "Usage:"
echo "  cd backend"
echo "  podman-compose up -d"
echo ""
echo "Or with docker-compose (using Podman socket):"
echo "  export DOCKER_HOST=unix://$PODMAN_SOCKET"
echo "  cd backend"
echo "  docker compose up -d"
