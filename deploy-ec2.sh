#!/usr/bin/env bash
# deploy-ec2.sh
# Hot-deploy lhdn_payroll_integration and prisma_assistant from the host git
# repo into running Docker containers — no image rebuild required.
#
# Usage (from EC2 host):
#   bash deploy-ec2.sh
#
# Usage (from local laptop):
#   ssh -i prisma-erp-key.pem ubuntu@<EC2_IP> "cd prisma-erp && bash deploy-ec2.sh"
#
# Why this exists:
#   The Docker image (wenjyue/erpnext-myinvois:v16) is static. Running git pull
#   on EC2 updates files on the HOST but NOT inside containers. This script
#   bridges that gap — copying updated app code into running containers so the
#   live site reflects the latest git commit instantly.
#
# What it does:
#   1. git pull origin main
#   2. docker cp lhdn_payroll_integration → backend container
#   3. docker cp prisma_assistant          → backend container
#   4. docker cp JS/CSS assets             → frontend container (separate volume!)
#   5. bench sync_fixtures (lhdn_payroll_integration)
#   6. bench clear-cache
#   7. restart backend/workers (picks up new Python modules)

set -euo pipefail

# ─── Config ──────────────────────────────────────────────────────────────────
COMPOSE_FILE="pwd-myinvois.yml"
BACKEND="prisma-erp-backend-1"
FRONTEND="prisma-erp-frontend-1"
SITE="frontend"
BENCH="$BACKEND:/home/frappe/frappe-bench"
APPS="/home/frappe/frappe-bench/apps"
ASSETS="/home/frappe/frappe-bench/sites/assets"

# ─── Colours ─────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()  { echo -e "${GREEN}→${NC}  $*"; }
warn()  { echo -e "${YELLOW}!${NC}  $*"; }
ok()    { echo -e "${GREEN}✓${NC}  $*"; }
die()   { echo -e "${RED}✗${NC}  $*" >&2; exit 1; }
hr()    { echo -e "${GREEN}──────────────────────────────────────────────────${NC}"; }

hr
echo "  prisma-erp EC2 hot-deploy"
hr

# ─── Preflight ───────────────────────────────────────────────────────────────
[ -f "$COMPOSE_FILE" ] || die "Run this script from the prisma-erp repo root."
command -v docker >/dev/null 2>&1 || die "docker not found."

# ─── 1. Git pull ─────────────────────────────────────────────────────────────
info "Checking git branch..."
BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [ "$BRANCH" != "main" ]; then
    warn "On branch '$BRANCH', switching to main..."
    git checkout main
fi
info "Pulling origin/main..."
git pull origin main
COMMIT=$(git rev-parse --short HEAD)
ok "Up to date at commit $COMMIT"

# ─── 2. Verify containers are up ─────────────────────────────────────────────
info "Checking containers..."
docker inspect "$BACKEND"  >/dev/null 2>&1 || die "Backend container '$BACKEND' not running. Start with: docker compose -f $COMPOSE_FILE up -d"
docker inspect "$FRONTEND" >/dev/null 2>&1 || die "Frontend container '$FRONTEND' not running."
ok "Both containers running"

# ─── 3. Hot-deploy: lhdn_payroll_integration ─────────────────────────────────
info "Deploying lhdn_payroll_integration → backend..."
docker cp lhdn_payroll_integration/. "$BACKEND:$APPS/lhdn_payroll_integration/"

# NOTE: sites/assets is a SEPARATE anonymous Docker volume per container.
# Copying to backend does NOT reach the frontend (nginx). Always cp to frontend.
info "Deploying lhdn_payroll_integration assets → frontend..."
docker exec "$FRONTEND" mkdir -p "$ASSETS/lhdn_payroll_integration"
docker cp lhdn_payroll_integration/lhdn_payroll_integration/public/. \
    "$FRONTEND:$ASSETS/lhdn_payroll_integration/"
ok "lhdn_payroll_integration deployed"

# ─── 4. Hot-deploy: prisma_assistant ─────────────────────────────────────────
info "Deploying prisma_assistant → backend..."
docker cp prisma_assistant/. "$BACKEND:$APPS/prisma_assistant/"

info "Deploying prisma_assistant assets → frontend..."
docker exec "$FRONTEND" mkdir -p "$ASSETS/prisma_assistant/js" "$ASSETS/prisma_assistant/css"
docker cp prisma_assistant/prisma_assistant/public/js/.  "$FRONTEND:$ASSETS/prisma_assistant/js/"
docker cp prisma_assistant/prisma_assistant/public/css/. "$FRONTEND:$ASSETS/prisma_assistant/css/"
ok "prisma_assistant deployed"

# ─── 5. Sync fixtures (workspace, custom fields, etc.) ───────────────────────
info "Syncing lhdn_payroll_integration fixtures..."
docker exec "$BACKEND" bash -c "
    cd /home/frappe/frappe-bench && \
    bench --site $SITE execute frappe.utils.fixtures.sync_fixtures \
        --kwargs '{\"app\": \"lhdn_payroll_integration\"}'
"
ok "Fixtures synced"

# ─── 6. Clear cache ──────────────────────────────────────────────────────────
info "Clearing Frappe cache..."
docker exec "$BACKEND" bash -c "
    cd /home/frappe/frappe-bench && \
    bench --site $SITE clear-cache && \
    bench --site $SITE clear-website-cache
"
ok "Cache cleared"

# ─── 7. Restart workers (picks up new Python code) ───────────────────────────
info "Restarting backend workers..."
docker compose -f "$COMPOSE_FILE" restart backend websocket scheduler queue-long queue-short
ok "Workers restarted"

# ─── Done ─────────────────────────────────────────────────────────────────────
hr
echo -e "  ${GREEN}Deploy complete!${NC}  commit=$COMMIT  site=http://\$(hostname -I | awk '{print \$1}'):8080"
hr
