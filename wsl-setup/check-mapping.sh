#!/bin/bash
grep -rn "Small Text" ~/frappe-bench/apps/frappe/frappe/database/ | grep -v ".pyc" | head -10
echo "---"
grep -rn "column_type" ~/frappe-bench/apps/frappe/frappe/database/schema.py | head -5
