#!/bin/bash
# Full bench setup: init with Python 3.12, clone + patch all apps
# Run as: wenjyue user
set -e

BENCH_DIR="/home/wenjyue/frappe-bench"
WIN_REPO="/mnt/c/Users/Jyue/Documents/1-projects/Projects/prisma-erp"

fix_requires_python() {
  local pyproject="$1/pyproject.toml"
  if [ -f "$pyproject" ]; then
    sed -i 's/requires-python = ">=3\.14"/requires-python = ">=3.12"/' "$pyproject"
    sed -i 's/target-version = "py314"/target-version = "py312"/' "$pyproject"
    echo "[patched] $pyproject"
  fi
}

# ── Phase 3: bench init ────────────────────────────────────────────────────
echo "=== Phase 3: bench init with Python 3.12 ==="
cd /home/wenjyue
bench init frappe-bench --frappe-branch version-16 --python python3.12
echo "=== bench init done ==="

cd "$BENCH_DIR"

# ── ERPNext ────────────────────────────────────────────────────────────────
echo "=== Cloning ERPNext version-16 ==="
git clone https://github.com/frappe/erpnext.git --branch version-16 --depth 1 apps/erpnext
fix_requires_python apps/erpnext
echo "=== Installing ERPNext ==="
./env/bin/uv pip install --quiet -e apps/erpnext --python ./env/bin/python

# ── HRMS ──────────────────────────────────────────────────────────────────
echo "=== Cloning HRMS version-16 ==="
git clone https://github.com/frappe/hrms.git --branch version-16 --depth 1 apps/hrms
fix_requires_python apps/hrms
echo "=== Installing HRMS ==="
./env/bin/uv pip install --quiet -e apps/hrms --python ./env/bin/python

# ── MyInvois (ERPGulf) ─────────────────────────────────────────────────────
echo "=== Cloning myinvois ==="
git clone https://github.com/ERPGulf/myinvois.git --branch main apps/myinvois_erpgulf
fix_requires_python apps/myinvois_erpgulf
echo "=== Installing myinvois (--no-deps as per Dockerfile) ==="
./env/bin/pip install --quiet --no-deps -e apps/myinvois_erpgulf
./env/bin/pip install --quiet "qrcode[pil]"

# ── Frappe Assistant Core ──────────────────────────────────────────────────
echo "=== Cloning frappe_assistant_core ==="
git clone https://github.com/buildswithpaul/Frappe_Assistant_Core --branch main apps/frappe_assistant_core
fix_requires_python apps/frappe_assistant_core
echo "=== Installing frappe_assistant_core ==="
./env/bin/uv pip install --quiet -e apps/frappe_assistant_core --python ./env/bin/python
# Restore versions overridden by frappe_assistant_core
./env/bin/pip install --quiet "beautifulsoup4~=4.13.5" "chardet~=5.2.0"

# ── Custom apps from Windows repo ─────────────────────────────────────────
echo "=== Copying lhdn_payroll_integration from repo ==="
cp -r "$WIN_REPO/lhdn_payroll_integration" apps/
fix_requires_python apps/lhdn_payroll_integration
echo "=== Installing lhdn_payroll_integration (--no-deps) ==="
./env/bin/pip install --quiet --no-deps -e apps/lhdn_payroll_integration

echo "=== Copying prisma_assistant from repo ==="
cp -r "$WIN_REPO/prisma_assistant" apps/
fix_requires_python apps/prisma_assistant
echo "=== Installing prisma_assistant (--no-deps) ==="
./env/bin/pip install --quiet --no-deps -e apps/prisma_assistant

# ── Summary ───────────────────────────────────────────────────────────────
echo ""
echo "=== Apps installed ==="
ls apps/
echo ""
echo "=== Python packages (frappe, erpnext, hrms) ==="
./env/bin/pip show frappe erpnext hrms 2>/dev/null | grep -E "^(Name|Version):"
echo ""
echo "=== Phase 3-4 COMPLETE ==="
