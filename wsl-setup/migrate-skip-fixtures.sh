#!/bin/bash
cd ~/frappe-bench
bench --site frontend migrate --skip-fixtures > /tmp/migrate_out.txt 2>&1 || true
echo "=== RESULT ==="
tail -10 /tmp/migrate_out.txt
