#!/bin/bash
echo "=== Killing hanging mysql processes ==="
pkill -f "mysql -u root" 2>/dev/null || true
pkill -f "mysqladmin" 2>/dev/null || true
sleep 2

echo "=== Restarting MariaDB ==="
service mariadb restart

echo "=== Testing ping ==="
mysqladmin -u root -padmin ping
echo "Done"
