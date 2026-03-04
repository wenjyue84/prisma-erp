#!/bin/bash
echo "=== MariaDB processes ==="
ps aux | grep -E "mysql|mysqld" | head -10
echo "=== Port 3306 ==="
ss -tlnp | grep 3306
echo "=== MariaDB ping (5s timeout) ==="
timeout 5 mysqladmin -u root -padmin ping 2>&1 || echo "TIMEOUT or error"
