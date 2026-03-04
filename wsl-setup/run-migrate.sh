#!/bin/bash
cd ~/frappe-bench
bench --site frontend migrate 2>&1 | grep -E "Updating|OperationalError" | head -50
