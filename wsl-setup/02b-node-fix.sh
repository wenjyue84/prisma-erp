#!/bin/bash
# Fix libnode-dev conflict then install Node.js 18 + yarn + frappe-bench
set -e

echo "=== Removing conflicting libnode-dev ==="
apt-get remove -y libnode-dev 2>/dev/null || true
apt-get autoremove -y 2>/dev/null || true

echo "=== Installing Node.js 18 ==="
apt-get install -y nodejs

echo "=== Node version ==="
node --version
npm --version

echo "=== Installing yarn ==="
npm install -g yarn
yarn --version

echo "=== Installing frappe-bench ==="
pip3 install frappe-bench

echo "=== bench path ==="
which bench || find /usr -name bench 2>/dev/null | head -3
bench --version 2>/dev/null || python3 -m bench --version 2>/dev/null || echo "bench installed (may need PATH update)"

echo "=== Done ==="
