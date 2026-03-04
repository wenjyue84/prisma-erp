#!/bin/bash
# Kill all mysql/mariadb processes
echo "=== Killing mysql processes ==="
pkill -9 -f mysql 2>/dev/null || true
pkill -9 -f mariadbd 2>/dev/null || true
sleep 3

echo "=== Starting MariaDB ==="
/usr/bin/mariadbd-safe --defaults-file=/etc/mysql/my.cnf 2>/dev/null &
MARIA_PID=$!
sleep 5
echo "MariaDB PID: $MARIA_PID"

echo "=== Ping test ==="
mysqladmin -u root -padmin ping && echo "MariaDB is UP"
