#!/usr/bin/env bash
# Runs via cron every 5 min. Shuts down EC2 if nginx idle 15+ min.
# Cron entry: */5 * * * * /home/ubuntu/prisma-erp/infra/wake-on-demand/auto-stop.sh >> /var/log/auto-stop.log 2>&1

IDLE_MIN=15
CONTAINER="prisma-erp-frontend-1"
LOG="/home/frappe/frappe-bench/logs/nginx.access.log"
COMPOSE_FILE="/home/ubuntu/prisma-erp/pwd-myinvois.yml"

ts() { date '+%Y-%m-%d %H:%M:%S'; }

# Container not running? Stack may already be down.
docker inspect "$CONTAINER" >/dev/null 2>&1 || { echo "$(ts) [SKIP] container not found"; exit 0; }

# Get last real user request (filter out socket.io polling + ping + health)
LAST=$(docker exec "$CONTAINER" grep -Ev '/socket\.io|/api/method/ping|/__frappe' \
       "$LOG" 2>/dev/null | tail -1)

if [ -z "$LAST" ]; then
    # No real requests ever — use container start time
    REF=$(docker inspect --format='{{.State.StartedAt}}' "$CONTAINER")
    LAST_EPOCH=$(date -d "$REF" +%s 2>/dev/null || echo 0)
else
    # Extract timestamp from nginx log: [01/Mar/2026:09:45:23 +0000]
    RAW=$(echo "$LAST" | grep -oP '\[\K[^\]]+')
    LAST_EPOCH=$(date -d "${RAW/\// }" +%s 2>/dev/null || echo 0)
fi

NOW=$(date +%s)
IDLE=$(( NOW - LAST_EPOCH ))
THRESH=$(( IDLE_MIN * 60 ))

echo "$(ts) [CHECK] idle ${IDLE}s / threshold ${THRESH}s"

[ "$IDLE" -lt "$THRESH" ] && { echo "$(ts) [ACTIVE] no action"; exit 0; }

echo "$(ts) [SHUTDOWN] idle ${IDLE}s — stopping stack then OS"
cd /home/ubuntu/prisma-erp
docker compose -f "$COMPOSE_FILE" down --timeout 30 || true
sudo /sbin/shutdown -h now "auto-stop: idle ${IDLE_MIN}min"
