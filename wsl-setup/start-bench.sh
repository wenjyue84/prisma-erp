#!/bin/bash
# Stop any leftover Redis on bench ports first
redis-cli -p 11000 shutdown nosave 2>/dev/null
redis-cli -p 13000 shutdown nosave 2>/dev/null
sleep 1

cd ~/frappe-bench
nohup bench start > /tmp/bench_start.log 2>&1 &
echo "bench PID: $!"
sleep 5
echo "=== Last 20 lines of bench log ==="
tail -20 /tmp/bench_start.log
