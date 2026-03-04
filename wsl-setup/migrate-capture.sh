#!/bin/bash
cd ~/frappe-bench
bench --site frontend migrate > /tmp/migrate_out.txt 2>&1 || true
