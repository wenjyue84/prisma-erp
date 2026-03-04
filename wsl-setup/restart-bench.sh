#!/bin/bash
# Stop bench processes
pkill -f honcho 2>/dev/null || true
pkill -f "bench serve" 2>/dev/null || true
pkill -f "python.*frappe" 2>/dev/null || true
sleep 3
echo "Bench stopped"

# Kill old Redis on bench ports
redis-cli -p 11000 shutdown nosave 2>/dev/null || true
redis-cli -p 13000 shutdown nosave 2>/dev/null || true
sleep 1

# Start bench
cd ~/frappe-bench
nohup bench start > /tmp/bench_start.log 2>&1 &
echo "bench PID: $!"
sleep 8
echo "=== Last 15 lines ==="
tail -15 /tmp/bench_start.log
