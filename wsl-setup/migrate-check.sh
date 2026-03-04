#!/bin/bash
cd ~/frappe-bench
bench --site frontend migrate > /tmp/migrate_out.txt 2>&1 || true
# Show last lines and grep for key info
echo "=== LAST 30 LINES ==="
tail -30 /tmp/migrate_out.txt
echo ""
echo "=== DOCTYPE BEING PROCESSED WHEN ERROR OCCURRED ==="
grep -E "Updating DocTypes" /tmp/migrate_out.txt | tail -5
