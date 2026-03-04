#!/bin/bash
# Install missing npm deps in each app, then build
set -e

cd ~/frappe-bench

echo "=== Installing erpnext npm deps ==="
cd apps/erpnext && yarn install --frozen-lockfile 2>&1 | tail -5
cd ~/frappe-bench

echo "=== Installing hrms npm deps ==="
cd apps/hrms && yarn install --frozen-lockfile 2>&1 | tail -5
cd ~/frappe-bench

echo "=== Running bench build ==="
bench build --app frappe --app erpnext --app hrms --app lhdn_payroll_integration --app prisma_assistant 2>&1 | tail -20

echo "=== Build done ==="
