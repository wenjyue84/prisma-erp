#!/bin/bash
# Phase 2d-2e: Install Node.js 18, yarn, frappe-bench
set -e

echo "=== Installing Node.js 18 ==="
# Remove old node
apt-get remove -y nodejs 2>/dev/null || true

curl -fsSL https://deb.nodesource.com/setup_18.x | bash -
apt-get install -y nodejs

echo "=== Node version ==="
node --version

echo "=== Installing yarn ==="
npm install -g yarn
yarn --version

echo "=== Installing frappe-bench ==="
pip3 install frappe-bench

echo "=== bench version ==="
bench --version 2>/dev/null || /usr/local/bin/bench --version

echo "=== Done: Node + bench installed ==="
