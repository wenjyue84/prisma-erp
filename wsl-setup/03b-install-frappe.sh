#!/bin/bash
# Install frappe into venv after pkg-config fix, then continue with get-app
set -e
cd /home/wenjyue/frappe-bench

echo "=== Installing frappe into venv ==="
./env/bin/pip install -e apps/frappe

echo "=== Frappe installed, verifying ==="
./env/bin/python -c "import frappe; print('frappe OK:', frappe.__version__)"

echo "=== Running bench setup to create Procfile/config ==="
bench setup redis 2>/dev/null || true

echo "=== Fetching ERPNext v16 ==="
bench get-app erpnext --branch version-16

echo "=== Fetching HRMS v16 ==="
bench get-app hrms --branch version-16

echo "=== Fetching myinvois (ERPGulf) ==="
bench get-app https://github.com/ERPGulf/myinvois.git --branch main

echo "=== Fetching frappe_assistant_core ==="
bench get-app https://github.com/buildswithpaul/Frappe_Assistant_Core --branch main

echo "=== Apps fetched: ==="
ls apps/

echo "=== Phase 3 complete ==="
