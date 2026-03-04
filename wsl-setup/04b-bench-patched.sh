#!/bin/bash
# Full bench setup with pyproject.toml patching for >=3.14 typo
# Run as: wenjyue user
set -e

BENCH_DIR="/home/wenjyue/frappe-bench"
WIN_REPO="/mnt/c/Users/Jyue/Documents/1-projects/Projects/prisma-erp"

# Patch pyproject.toml: >=3.14 → >=3.10 (custom apps don't need 3.14)
# For frappe/erpnext/hrms with Python 3.14 venv this function is not needed
# but call it defensively; it's a no-op if requires-python is already correct
patch_pyproject() {
  local appdir="$1"
  local pyproject="$appdir/pyproject.toml"
  if [ -f "$pyproject" ]; then
    sed -i \
      -e 's/requires-python = ">=3\.14[^"]*"/requires-python = ">=3.10"/' \
      -e 's/target-version = "py314"/target-version = "py310"/' \
      "$pyproject"
    echo "[patched] $pyproject -> $(grep requires-python $pyproject | head -1)"
  fi
}

# Full install (with deps) but ignore requires-python -- for frappe/erpnext/hrms
pip_install() {
  local appdir="$1"
  echo "  pip install --ignore-requires-python -e $appdir"
  "$BENCH_DIR/env/bin/pip" install --quiet --ignore-requires-python -e "$appdir"
}

# No-deps install -- for custom/satellite apps where frappe already covers deps
pip_install_nodeps() {
  local appdir="$1"
  echo "  pip install --no-deps --ignore-requires-python -e $appdir"
  "$BENCH_DIR/env/bin/pip" install --quiet --no-deps --ignore-requires-python -e "$appdir"
}

# Pinned to exact versions from running Docker container (frappe bench version output)
FRAPPE_VER="v16.10.0"
ERPNEXT_VER="v16.7.0"
HRMS_VER="v16.4.2"

# ── Phase 3: bench init with Python 3.14 (matches Docker) ────────────────
echo "=== Phase 3: bench init with frappe $FRAPPE_VER (Python 3.14) ==="
cd /home/wenjyue

# bench init with Python 3.14 — frappe/erpnext/hrms require Python 3.14
bench init frappe-bench --frappe-branch "$FRAPPE_VER" --python python3.14 2>&1

cd "$BENCH_DIR"

# Verify frappe installed correctly
if ! ./env/bin/python -c "import frappe" 2>/dev/null; then
  echo "ERROR: frappe import failed"
  ./env/bin/python -c "import frappe" 2>&1
  exit 1
fi

echo "=== Verify frappe ==="
./env/bin/python -c "import frappe; print('frappe OK:', frappe.__version__)"

# ── ERPNext ────────────────────────────────────────────────────────────────
echo "=== Cloning ERPNext $ERPNEXT_VER ==="
[ -d apps/erpnext ] || git clone https://github.com/frappe/erpnext.git \
  --branch "$ERPNEXT_VER" --depth 1 apps/erpnext
patch_pyproject apps/erpnext
echo "=== Installing ERPNext ==="
# patch in case erpnext pinned version also has >=3.14 issues on older pip
patch_pyproject apps/erpnext
pip_install apps/erpnext

# ── HRMS ──────────────────────────────────────────────────────────────────
echo "=== Cloning HRMS $HRMS_VER ==="
[ -d apps/hrms ] || git clone https://github.com/frappe/hrms.git \
  --branch "$HRMS_VER" --depth 1 apps/hrms
patch_pyproject apps/hrms
echo "=== Installing HRMS ==="
pip_install apps/hrms

# ── MyInvois (ERPGulf) ─────────────────────────────────────────────────────
echo "=== Cloning myinvois ==="
[ -d apps/myinvois_erpgulf ] || git clone https://github.com/ERPGulf/myinvois.git \
  --branch main apps/myinvois_erpgulf
patch_pyproject apps/myinvois_erpgulf
echo "=== Installing myinvois (--no-deps) ==="
pip_install_nodeps apps/myinvois_erpgulf
./env/bin/pip install --quiet "qrcode[pil]"

# ── Frappe Assistant Core ──────────────────────────────────────────────────
echo "=== Cloning frappe_assistant_core ==="
[ -d apps/frappe_assistant_core ] || git clone \
  https://github.com/buildswithpaul/Frappe_Assistant_Core \
  --branch main apps/frappe_assistant_core
patch_pyproject apps/frappe_assistant_core
echo "=== Installing frappe_assistant_core ==="
pip_install apps/frappe_assistant_core
# Restore versions that frappe_assistant_core overrides (per CLAUDE.md)
./env/bin/pip install --quiet "beautifulsoup4~=4.13.5" "chardet~=5.2.0"

# ── Custom apps from Windows repo ─────────────────────────────────────────
echo "=== Copying + installing lhdn_payroll_integration ==="
[ -d apps/lhdn_payroll_integration ] || \
  cp -r "$WIN_REPO/lhdn_payroll_integration" apps/
patch_pyproject apps/lhdn_payroll_integration
pip_install_nodeps apps/lhdn_payroll_integration

echo "=== Copying + installing prisma_assistant ==="
[ -d apps/prisma_assistant ] || \
  cp -r "$WIN_REPO/prisma_assistant" apps/
patch_pyproject apps/prisma_assistant
pip_install_nodeps apps/prisma_assistant

# ── Summary ───────────────────────────────────────────────────────────────
echo ""
echo "=== Apps directory ==="
ls apps/
echo ""
echo "=== Installed packages ==="
./env/bin/pip show frappe erpnext hrms 2>/dev/null | grep -E "^(Name|Version):"
echo ""
echo "=== Phase 3-4 COMPLETE ==="
