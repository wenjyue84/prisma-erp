#!/bin/bash
# prisma-erp session-start hook
# Starts the local ERPNext stack so it's ready in the browser at http://localhost:8080

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
COMPOSE_FILE="pwd-myinvois.yml"

echo "[session-start] prisma-erp: starting Docker stack..."

cd "$PROJECT_DIR" || exit 0

# Start Docker Desktop if daemon is not running
if ! docker info > /dev/null 2>&1; then
  echo "[session-start] Docker not running — launching Docker Desktop..."
  powershell.exe -Command "Start-Process 'C:\Program Files\Docker\Docker\Docker Desktop.exe'" 2>/dev/null
  # Wait up to 90s for daemon
  for i in $(seq 1 18); do
    sleep 5
    if docker info > /dev/null 2>&1; then
      echo "[session-start] Docker daemon ready."
      break
    fi
    echo "[session-start] Waiting for Docker daemon... ($i/18)"
  done
  if ! docker info > /dev/null 2>&1; then
    echo "[session-start] Docker daemon did not start in time — skipping."
    exit 0
  fi
fi

# Check if stack is already up (frontend container running)
if docker ps --format '{{.Names}}' 2>/dev/null | grep -q "prisma-erp-frontend"; then
  echo "[session-start] Stack already running → http://localhost:8080"
  exit 0
fi

# Start the stack detached
docker compose -f "$COMPOSE_FILE" up -d 2>&1 | tail -5

echo "[session-start] ERPNext stack started → http://localhost:8080"
