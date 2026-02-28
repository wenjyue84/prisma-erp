#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Prisma ERP — Comprehensive HTTP Test Runner
============================================

Usage:
  python tests/run_tests.py                     # run all suites
  python tests/run_tests.py --suite smoke        # single suite
  python tests/run_tests.py --suite smoke unit   # multiple suites
  python tests/run_tests.py --list              # list available suites
  python tests/run_tests.py --no-report         # skip HTML/JSON report
  python tests/run_tests.py --url http://1.2.3.4:8080  # override URL

Reports are written to test-reports/YYYY-MM-DD_HH-MM-SS/ as:
  - report.json  (machine-readable, feed to Claude Code)
  - report.html  (human-readable dashboard)
  - summary.txt  (plain-text console output)

Prerequisites:
  pip install requests   (or: uv pip install requests)
"""

import argparse
import io
import os
import sys
import time
import unittest
from datetime import datetime
from pathlib import Path

# Force UTF-8 output on Windows to handle box-drawing / emoji chars
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Ensure repo root is on sys.path so 'tests.*' imports work
REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

# Override URL from CLI before importing config
def _apply_url_override(url: str) -> None:
    os.environ["ERPNEXT_URL"] = url

from tests.reporters.json_reporter import JSONTestResult
from tests.reporters import html_reporter
from tests.config import BASE_URL, REPORT_DIR

# ── Suite registry ─────────────────────────────────────────────────────────────

SUITES = {
    "smoke": "tests.smoke.test_smoke",
    "unit:prisma_ai": "tests.unit.prisma_ai.test_chat_api",
    "unit:lhdn_payroll": "tests.unit.lhdn_payroll.test_payroll_doctypes",
    "integration": "tests.integration.test_workflows",
    "edge_cases": "tests.edge_cases.test_edge_cases",
    "security": "tests.security.test_security",
    "performance": "tests.performance.test_performance",
    "api_contract": "tests.api_contract.test_api_contract",
    "regression": "tests.regression.test_regression",
}

SUITE_ORDER = [
    "smoke",
    "unit:prisma_ai",
    "unit:lhdn_payroll",
    "api_contract",
    "regression",
    "integration",
    "edge_cases",
    "security",
    "performance",
]

SUITE_DESCRIPTIONS = {
    "smoke": "Basic HTTP connectivity & app installation checks",
    "unit:prisma_ai": "Prisma AI chat API — send_message, key info, settings",
    "unit:lhdn_payroll": "LHDN Payroll doctypes, custom fields, reports, workspace",
    "api_contract": "API response schema validation for all endpoints",
    "regression": "Guards against previously-fixed bugs",
    "integration": "End-to-end payroll & AI chat workflows",
    "edge_cases": "Boundary values, unusual inputs, corner cases",
    "security": "Auth enforcement, CSRF, injection attack prevention",
    "performance": "Response time SLAs & concurrent load testing",
}

# ── Helpers ────────────────────────────────────────────────────────────────────

def _color(text: str, code: str) -> str:
    """Wrap text in ANSI colour code if supported."""
    if sys.platform == "win32" and "WT_SESSION" not in os.environ:
        return text
    return f"\033[{code}m{text}\033[0m"

GREEN = lambda t: _color(t, "92")
RED   = lambda t: _color(t, "91")
YELLOW= lambda t: _color(t, "93")
CYAN  = lambda t: _color(t, "96")
BOLD  = lambda t: _color(t, "1")


def load_suite(module_path: str) -> unittest.TestSuite:
    loader = unittest.TestLoader()
    return loader.loadTestsFromName(module_path)


def run_suites(suite_names: list[str], verbosity: int = 1) -> JSONTestResult:
    result = JSONTestResult()
    result.startTestRun()

    for name in suite_names:
        module_path = SUITES[name]
        desc = SUITE_DESCRIPTIONS.get(name, "")
        print(f"\n{BOLD(CYAN(f'▶ Suite: {name}'))}  {desc}")
        print("─" * 70)

        suite = load_suite(module_path)
        test_count = suite.countTestCases()
        print(f"  Running {test_count} test(s)…")

        suite_start = time.perf_counter()
        suite.run(result)
        suite_elapsed = time.perf_counter() - suite_start

        # Print per-test summary for this suite
        suite_results = [r for r in result.results if r["category"] == name or name in r["id"]]
        for r in suite_results[-(test_count):]:
            icon = GREEN("✓") if r["status"] == "PASS" else RED("✗") if r["status"] in ("FAIL", "ERROR") else YELLOW("⊘")
            ms = f"{r['duration_ms']:.0f} ms"
            print(f"  {icon} {r['name']:<55} {ms:>8}")
            if r["error"]:
                print(f"      {RED(r['error']['type'])}: {r['error']['message'][:100]}")

        print(f"  Completed in {suite_elapsed:.2f}s")

    return result


def save_report(result: JSONTestResult, report_dir: str) -> tuple[str, str, str]:
    """Save JSON + HTML + TXT reports; return (json_path, html_path, txt_path)."""
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    out_dir = os.path.join(report_dir, ts)
    os.makedirs(out_dir, exist_ok=True)

    json_path = os.path.join(out_dir, "report.json")
    html_path = os.path.join(out_dir, "report.html")
    txt_path  = os.path.join(out_dir, "summary.txt")

    report_dict = result.to_dict()
    result.save(json_path)
    html_reporter.generate(report_dict, html_path)

    # Plain-text summary
    s = report_dict["summary"]
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(f"Prisma ERP Test Report — {ts}\n")
        f.write(f"URL: {BASE_URL}\n")
        f.write("=" * 60 + "\n")
        f.write(f"Total: {s['total']}  Pass: {s['passed']}  Fail: {s['failed']}  "
                f"Error: {s['errored']}  Skip: {s['skipped']}\n")
        f.write(f"Pass rate: {s['pass_rate']}\n\n")
        f.write("FAILURES & ERRORS:\n")
        for r in report_dict["all_results"]:
            if r["status"] in ("FAIL", "ERROR"):
                f.write(f"\n  [{r['status']}] {r['id']}\n")
                f.write(f"  {r['description']}\n")
                if r["error"]:
                    f.write(f"  {r['error']['type']}: {r['error']['message']}\n")
                    for line in (r["error"].get("traceback") or []):
                        f.write(f"    {line}")

    return json_path, html_path, txt_path


def print_summary(result: JSONTestResult) -> None:
    report = result.to_dict()
    s = report["summary"]
    print("\n" + "═" * 70)
    print(BOLD("PRISMA ERP TEST SUMMARY"))
    print("═" * 70)
    print(f"  Total  : {BOLD(str(s['total']))}")
    print(f"  Passed : {GREEN(str(s['passed']))}")
    print(f"  Failed : {RED(str(s['failed']))}")
    print(f"  Errors : {RED(str(s['errored']))}")
    print(f"  Skipped: {YELLOW(str(s['skipped']))}")
    print(f"  Rate   : {GREEN(s['pass_rate']) if s['failed']+s['errored']==0 else RED(s['pass_rate'])}")

    if s["failed"] + s["errored"] > 0:
        print(f"\n{RED('FAILURES & ERRORS:')}")
        for r in report["all_results"]:
            if r["status"] in ("FAIL", "ERROR"):
                print(f"  {RED('✗')} {r['name']}")
                if r["error"]:
                    print(f"    {r['error']['type']}: {r['error']['message'][:120]}")
    print("═" * 70)


# ── CLI ────────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prisma ERP comprehensive HTTP test runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--suite", "-s", nargs="+", metavar="SUITE",
        help=f"Suite(s) to run. Available: {', '.join(SUITE_ORDER)}",
    )
    parser.add_argument(
        "--list", "-l", action="store_true",
        help="List available suites and exit",
    )
    parser.add_argument(
        "--url", metavar="URL",
        help=f"Override ERPNext base URL (default: {BASE_URL})",
    )
    parser.add_argument(
        "--no-report", action="store_true",
        help="Skip writing JSON/HTML reports to disk",
    )
    parser.add_argument(
        "--report-dir", default=REPORT_DIR, metavar="DIR",
        help=f"Report output directory (default: {REPORT_DIR})",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Show extra output",
    )

    args = parser.parse_args()

    if args.url:
        _apply_url_override(args.url)

    if args.list:
        print(BOLD("\nAvailable Test Suites:"))
        print("─" * 60)
        for name in SUITE_ORDER:
            print(f"  {CYAN(name):<30} {SUITE_DESCRIPTIONS.get(name, '')}")
        return 0

    requested = args.suite if args.suite else SUITE_ORDER

    # Validate suite names
    unknown = [s for s in requested if s not in SUITES]
    if unknown:
        print(RED(f"Unknown suite(s): {', '.join(unknown)}"))
        print(f"Available: {', '.join(SUITE_ORDER)}")
        return 2

    print(BOLD(f"\n🧪 Prisma ERP Test Suite"))
    print(f"   Target: {CYAN(BASE_URL)}")
    print(f"   Suites: {', '.join(requested)}")
    print("─" * 70)

    # Check connectivity first
    try:
        import requests as _req
        r = _req.get(f"{BASE_URL}/api/method/frappe.ping", timeout=5)
        if r.status_code != 200:
            print(RED(f"\n⚠  Cannot reach {BASE_URL} (status {r.status_code})"))
            print("   Start the stack: docker compose -f pwd-myinvois.yml up -d")
            return 3
        print(GREEN(f"   Server alive ✓  ({r.elapsed.microseconds//1000} ms)"))
    except Exception as e:
        print(RED(f"\n✗  Cannot reach {BASE_URL}: {e}"))
        return 3

    result = run_suites(requested, verbosity=2 if args.verbose else 1)
    print_summary(result)

    if not args.no_report:
        json_path, html_path, txt_path = save_report(result, args.report_dir)
        print(f"\n📄 Reports saved:")
        print(f"   JSON : {json_path}")
        print(f"   HTML : {html_path}")
        print(f"   TXT  : {txt_path}")
        print(f"\n💡 To send errors to Claude Code:")
        print(f"   cat {txt_path}")

    report = result.to_dict()
    s = report["summary"]
    return 0 if s["failed"] + s["errored"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
