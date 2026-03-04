#!/bin/bash
# Kill any leftover processes
pkill -9 -f mysqld 2>/dev/null || true
sleep 1

# Clean up stale socket and pid files
rm -f /run/mysqld/mysqld.sock /run/mysqld/mysqld.pid
mkdir -p /run/mysqld
chown mysql:mysql /run/mysqld

echo "=== Starting fresh MariaDB ==="
mysqld_safe --no-defaults \
  --defaults-file=/etc/mysql/my.cnf \
  --socket=/run/mysqld/mysqld.sock \
  --pid-file=/run/mysqld/mysqld.pid \
  --log-error=/tmp/mariadb.log \
  2>/tmp/mariadb_safe.log &

echo "Waiting 8s..."
sleep 8

echo "=== Ping test ==="
mysqladmin -u root -padmin --socket=/run/mysqld/mysqld.sock ping && echo "MariaDB UP" || (echo "FAILED, log:"; tail -10 /tmp/mariadb.log)
