#!/bin/bash
# Phase 3: bench init as the normal user (wenjyue)
# Must run as wenjyue, NOT root
set -e

cd /home/wenjyue

if [ -d "frappe-bench" ]; then
  echo "=== frappe-bench already exists, skipping init ==="
else
  echo "=== Initializing bench (frappe version-16) ==="
  bench init frappe-bench --frappe-branch version-16 --python python3.12
  echo "=== bench init complete ==="
fi

cd frappe-bench

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
