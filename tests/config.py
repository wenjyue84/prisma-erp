"""
Test configuration for the Prisma ERP test suite.

Override defaults with environment variables:
  ERPNEXT_URL   — base URL (default: http://localhost:8080)
  ERPNEXT_USER  — login username (default: Administrator)
  ERPNEXT_PASS  — login password (default: admin)
  TEST_TIMEOUT  — HTTP timeout in seconds (default: 30)
  REPORT_DIR    — where to write reports (default: test-reports)
"""

import os

# ── Connection ─────────────────────────────────────────────────────────────────
BASE_URL = os.getenv("ERPNEXT_URL", "http://localhost:8080").rstrip("/")
USERNAME = os.getenv("ERPNEXT_USER", "Administrator")
PASSWORD = os.getenv("ERPNEXT_PASS", "admin")

# ── Timeouts ───────────────────────────────────────────────────────────────────
TIMEOUT = int(os.getenv("TEST_TIMEOUT", "30"))
AI_TIMEOUT = int(os.getenv("AI_TIMEOUT", "60"))   # AI calls can be slow
PERF_THRESHOLD_MS = int(os.getenv("PERF_THRESHOLD_MS", "2000"))   # 2 s default SLA

# ── Reporting ──────────────────────────────────────────────────────────────────
REPORT_DIR = os.getenv("TEST_REPORT_DIR", "test-reports")

# ── Expected app names ─────────────────────────────────────────────────────────
EXPECTED_APPS = ["frappe", "erpnext", "prisma_assistant", "lhdn_payroll_integration"]

# ── Known ERPNext site ─────────────────────────────────────────────────────────
SITE_NAME = "frontend"

# ── Test data identifiers (idempotent — created by setup_test_data.py) ─────────
TEST_COMPANY = "Arising Packaging"
TEST_CUSTOMER_CORP = "Tech Solutions Sdn Bhd"
TEST_CUSTOMER_IND = "Ahmad bin Abdullah"
