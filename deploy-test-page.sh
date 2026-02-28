#!/usr/bin/env bash
# deploy-test-page.sh
# Deploys /test web page to the running Docker stack.
# Run this whenever test.html or test.py is updated locally.

set -e
BACKEND="prisma-erp-backend-1"
APP_PATH="/home/frappe/frappe-bench/apps/prisma_assistant/prisma_assistant"

echo "→ Creating www/ directory..."
docker exec "$BACKEND" sh -c "mkdir -p ${APP_PATH}/www"

echo "→ Copying test.html..."
docker cp prisma_assistant/prisma_assistant/www/test.html "$BACKEND:${APP_PATH}/www/test.html"

echo "→ Copying test.py..."
docker cp prisma_assistant/prisma_assistant/www/test.py "$BACKEND:${APP_PATH}/www/test.py"

echo "→ Clearing Frappe cache..."
docker exec "$BACKEND" sh -c "cd /home/frappe/frappe-bench && bench --site frontend clear-cache && bench --site frontend clear-website-cache"

echo ""
echo "✓  Test page deployed! Visit: http://localhost:8080/test"
echo "   (Log in as Administrator first if redirected)"
