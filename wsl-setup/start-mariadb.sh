#!/bin/bash
# Ensure socket dir exists
mkdir -p /run/mysqld
chown mysql:mysql /run/mysqld

# Start MariaDB in background
mysqld_safe --defaults-file=/etc/mysql/my.cnf 2>/tmp/mariadb_start.log &
sleep 6

# Test
echo "=== Ping ==="
mysqladmin -u root -padmin ping && echo "UP" || echo "FAILED"

echo "=== Socket ==="
ls -la /run/mysqld/mysqld.sock 2>/dev/null || echo "No socket"
