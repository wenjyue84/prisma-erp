#!/bin/bash
# Phase 5: Create ERPNext site with all apps
# Run as: wenjyue user (services started as root first)
set -e

BENCH_DIR="/home/wenjyue/frappe-bench"
cd "$BENCH_DIR"

echo "=== Starting MariaDB and Redis (via service as root) ==="
# Services need root - wenjyue calls them via sudo-less service wrapper
# (services were started during setup; just verify they're up)

echo "=== Checking MariaDB ==="
mysql -u root -padmin -e "SELECT 1;" 2>/dev/null && echo "MariaDB OK" || \
  (echo "MariaDB not running, trying to start..." && \
   service mariadb start 2>/dev/null || true && sleep 2)

echo "=== Checking Redis ==="
redis-cli ping 2>/dev/null && echo "Redis OK" || echo "Redis ping failed (may still work)"

echo "=== Creating site 'frontend' ==="
bench new-site frontend \
  --db-root-password admin \
  --admin-password admin \
  --no-mariadb-socket

echo "=== Installing apps on site ==="
bench --site frontend install-app erpnext
bench --site frontend install-app hrms
bench --site frontend install-app myinvois_erpgulf
bench --site frontend install-app lhdn_payroll_integration
bench --site frontend install-app prisma_assistant
bench --site frontend install-app frappe_assistant_core

echo "=== Enabling scheduler ==="
bench --site frontend enable-scheduler

echo "=== Site apps list ==="
bench --site frontend list-apps

echo "=== Phase 5 COMPLETE ==="
echo "=== Start bench with: cd ~/frappe-bench && bench start ==="
echo "=== Access at: http://localhost:8000 ==="
