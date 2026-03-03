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

# pip install (idempotent -e reinstall)
docker exec "$BACKEND" bash -c \
    "/home/frappe/frappe-bench/env/bin/pip install --quiet --no-deps -e /home/frappe/frappe-bench/apps/prisma_assistant"

# Register in bench apps registry (sites/apps.txt) if not already there
docker exec "$BACKEND" bash -c \
    "grep -qxF prisma_assistant /home/frappe/frappe-bench/sites/apps.txt || echo prisma_assistant >> /home/frappe/frappe-bench/sites/apps.txt"

# Install into Frappe site (--force skips duplicate Module Def error)
docker exec "$BACKEND" bash -c \
    "cd /home/frappe/frappe-bench && bench --site $SITE install-app prisma_assistant --force 2>&1 | tail -5"

info "Deploying prisma_assistant assets → frontend..."
docker exec "$FRONTEND" mkdir -p "$ASSETS/prisma_assistant/js" "$ASSETS/prisma_assistant/css"
docker cp prisma_assistant/prisma_assistant/public/js/.  "$FRONTEND:$ASSETS/prisma_assistant/js/"
docker cp prisma_assistant/prisma_assistant/public/css/. "$FRONTEND:$ASSETS/prisma_assistant/css/"
ok "prisma_assistant deployed"

# ─── 4b. Tabler Icons: keep patched sprite in sync with frontend container ────
if [ -f "frappe_patches/tabler_lucide_icons.svg" ]; then
    info "Deploying Tabler icons -> frontend..."
    docker cp frappe_patches/tabler_lucide_icons.svg \
        "$FRONTEND:/home/frappe/frappe-bench/apps/frappe/frappe/public/icons/lucide/icons.svg"
    docker cp frappe_patches/tabler_lucide_icons.svg \
        "$FRONTEND:/home/frappe/frappe-bench/apps/frappe/frappe/public/icons/lucide.svg"
    ok "Tabler icons deployed"
else
    warn "frappe_patches/tabler_lucide_icons.svg not found — skipping icon deploy (run replace_frappe_icons.py to regenerate)"
fi

# ─── 4c. Custom desktop icons (ESS Mobile, E-Invoice, LHDN Payroll) ──────────
# hrms and myinvois_erpgulf are baked in the Docker image; SVGs must be copied
# from this repo into the containers on every deploy (not in the image layers).
# frappe.scrub(label) → filename: "ESS Mobile"→ess_mobile, "E-Invoice"→e_invoice
info "Deploying custom desktop icons..."

# ESS Mobile (hrms app): black phone icon
for CTR in "$BACKEND" "$FRONTEND"; do
    docker cp ess_mobile.svg \
        "$CTR:/home/frappe/frappe-bench/apps/hrms/hrms/public/images/ess_mobile.svg"
    docker exec "$CTR" bash -c "
        mkdir -p /home/frappe/frappe-bench/apps/hrms/hrms/public/icons/desktop_icons/solid
        mkdir -p /home/frappe/frappe-bench/apps/hrms/hrms/public/icons/desktop_icons/subtle
        cp /home/frappe/frappe-bench/apps/hrms/hrms/public/images/ess_mobile.svg \
           /home/frappe/frappe-bench/apps/hrms/hrms/public/icons/desktop_icons/solid/ess_mobile.svg
        cp /home/frappe/frappe-bench/apps/hrms/hrms/public/images/ess_mobile.svg \
           /home/frappe/frappe-bench/apps/hrms/hrms/public/icons/desktop_icons/subtle/ess_mobile.svg
    "
done

# E-Invoice (myinvois_erpgulf): blue document icon
# Workspace Sidebar is named "Malaysia Compliance" → frappe.scrub("Malaysia Compliance")
# = malaysia_compliance → icon file must be malaysia_compliance.svg (not e_invoice.svg)
for CTR in "$BACKEND" "$FRONTEND"; do
    docker cp prisma_einvoice.svg \
        "$CTR:/home/frappe/frappe-bench/apps/myinvois_erpgulf/myinvois_erpgulf/public/images/prisma_einvoice.svg"
    docker exec "$CTR" bash -c "
        mkdir -p /home/frappe/frappe-bench/apps/myinvois_erpgulf/myinvois_erpgulf/public/icons/desktop_icons/solid
        mkdir -p /home/frappe/frappe-bench/apps/myinvois_erpgulf/myinvois_erpgulf/public/icons/desktop_icons/subtle
        cp /home/frappe/frappe-bench/apps/myinvois_erpgulf/myinvois_erpgulf/public/images/prisma_einvoice.svg \
           /home/frappe/frappe-bench/apps/myinvois_erpgulf/myinvois_erpgulf/public/icons/desktop_icons/solid/malaysia_compliance.svg
        cp /home/frappe/frappe-bench/apps/myinvois_erpgulf/myinvois_erpgulf/public/images/prisma_einvoice.svg \
           /home/frappe/frappe-bench/apps/myinvois_erpgulf/myinvois_erpgulf/public/icons/desktop_icons/subtle/malaysia_compliance.svg
    "
done

# Update Desktop Icon DB records (label must match Workspace Sidebar name for is_permitted)
docker exec "$BACKEND" bash -c "
cd /home/frappe/frappe-bench
bench --site $SITE execute frappe.db.set_value --args \"['Desktop Icon', 'Malaysia Compliance', 'app', 'myinvois_erpgulf']\" 2>/dev/null || true
bench --site $SITE execute frappe.db.commit
" && ok "E-Invoice Desktop Icon updated" || warn "E-Invoice icon update failed (non-fatal)"

# ESS Mobile: set app=hrms and logo_url so both desktop grid and sidebar show it
docker exec "$BACKEND" bash -c "
cd /home/frappe/frappe-bench
bench --site $SITE execute frappe.db.set_value --args \"['Desktop Icon', {'label': 'ESS Mobile'}, 'app', 'hrms']\"
bench --site $SITE execute frappe.db.set_value --args \"['Desktop Icon', {'label': 'ESS Mobile'}, 'logo_url', '/assets/hrms/images/ess_mobile.svg']\"
bench --site $SITE execute frappe.db.commit
" && ok "ESS Mobile icon updated" || warn "ESS Mobile icon update failed (non-fatal)"

# LHDN Payroll: set app=lhdn_payroll_integration and logo_url
docker exec "$BACKEND" bash -c "
cd /home/frappe/frappe-bench
bench --site $SITE execute frappe.db.set_value --args \"['Desktop Icon', {'label': 'LHDN Payroll'}, 'app', 'lhdn_payroll_integration']\"
bench --site $SITE execute frappe.db.set_value --args \"['Desktop Icon', {'label': 'LHDN Payroll'}, 'logo_url', '/assets/lhdn_payroll_integration/images/lhdn_payroll.svg']\"
bench --site $SITE execute frappe.db.commit
" && ok "LHDN Payroll icon updated" || warn "LHDN Payroll icon update failed (non-fatal)"

ok "Custom desktop icons deployed"

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

# ─── 6b. Re-apply 3-tier AI settings (Gemini → OpenAI → Ollama) ──────────────
info "Applying 3-tier AI settings..."
docker exec "$BACKEND" bash -c "
    cd /home/frappe/frappe-bench && \
    bench --site $SITE execute prisma_assistant.configure_ai_settings.run 2>&1 | tail -3
" && ok "AI settings applied (Gemini → OpenAI → Ollama via Tailscale)" \
  || warn "AI settings script failed — check DB manually"

# ─── 7. Restart workers (picks up new Python code) ───────────────────────────
info "Restarting backend workers..."
docker compose -f "$COMPOSE_FILE" restart backend websocket scheduler queue-long queue-short
ok "Workers restarted"

# ─── Done ─────────────────────────────────────────────────────────────────────
hr
echo -e "  ${GREEN}Deploy complete!${NC}  commit=$COMMIT  site=http://\$(hostname -I | awk '{print \$1}'):8080"
hr
