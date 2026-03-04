#!/bin/bash
# Phase 2a-2b: Install MariaDB 10.6, Redis, build tools
set -e

echo "=== Updating apt ==="
apt-get update -q

echo "=== Installing build tools, Python dev ==="
apt-get install -y git curl wget build-essential python3-dev python3-pip python3-venv libffi-dev libssl-dev

echo "=== Installing MariaDB server ==="
apt-get install -y mariadb-server mariadb-client

echo "=== Configuring MariaDB innodb for Frappe ==="
cat > /etc/mysql/mariadb.conf.d/99-frappe.cnf << 'MYCNF'
[mysqld]
character-set-server = utf8mb4
collation-server = utf8mb4_unicode_ci
skip-character-set-client-handshake
skip-innodb-read-only-compressed
innodb_strict_mode = 0
innodb_default_row_format = dynamic
MYCNF

echo "=== Starting MariaDB ==="
service mariadb start || true
sleep 2

echo "=== Setting MariaDB root password ==="
# Set root password to 'admin' (matching Docker setup)
mysql -u root -e "ALTER USER 'root'@'localhost' IDENTIFIED BY 'admin'; FLUSH PRIVILEGES;" 2>/dev/null || \
mysql -u root -padmin -e "FLUSH PRIVILEGES;" 2>/dev/null || \
mysqladmin -u root password 'admin' 2>/dev/null || true

echo "=== Installing Redis ==="
apt-get install -y redis-server

echo "=== Starting Redis ==="
service redis-server start || true

echo "=== MariaDB version ==="
mysql --version

echo "=== Redis version ==="
redis-cli --version

echo "=== Done: System deps installed ==="
