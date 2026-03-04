#!/bin/bash
# Kill old redis instances first
redis-cli -p 11000 shutdown nosave 2>/dev/null
redis-cli -p 13000 shutdown nosave 2>/dev/null
sleep 1

cd ~/frappe-bench
nohup bench start > /tmp/bench_start.log 2>&1 &
echo "bench PID: $!"
sleep 8
echo "=== FIRST 30 LINES ==="
head -30 /tmp/bench_start.log
echo "=== LAST 10 LINES ==="
tail -10 /tmp/bench_start.log
echo "=== Web port check ==="
ss -tlnp | grep 8080 || echo "port 8080 not listening"
