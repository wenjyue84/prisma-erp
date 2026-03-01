#!/usr/bin/env python3
"""
produce_payslip.py
==================

Programmatically simulates the ERPNext GUI flow to produce a Malaysian
LHDN-compliant payslip (Employment Act 1955 S.61 format) and saves the
PDF (or HTML) to the Desktop.

All records are left permanently in the database.
Idempotent: re-running skips already-existing records.

Usage:
    .venv-tests/Scripts/python.exe scripts/produce_payslip.py
"""

import io
import json
import os
import re
import sys
from urllib.parse import quote

import requests

# Force UTF-8 output on Windows (avoids cp1252 encode errors for box chars / arrows)
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# ── Configuration ──────────────────────────────────────────────────────────────
BASE         = "http://localhost:8080"
USER         = "Administrator"
PWD          = "admin"

COMPANY_NAME = "Arising Packaging"
STRUCT_NAME  = "Standard MY Payroll"
EMP_NAME     = "Siti Aminah binti Hassan"
PERIOD_START = "2026-03-01"
PERIOD_END   = "2026-03-31"
POSTING_DATE = "2026-03-31"

DESKTOP = os.path.join(os.path.expanduser("~"), "Desktop")

# ── Session ────────────────────────────────────────────────────────────────────
ses = requests.Session()
ses.headers.update({"Accept": "application/json"})
_csrf = ""


def login():
    global _csrf
    r = ses.post(f"{BASE}/api/method/login",
                 data={"usr": USER, "pwd": PWD}, timeout=30)
    r.raise_for_status()
    # Extract CSRF token from the /app bootstrap page (same way the browser does)
    boot = ses.get(f"{BASE}/app", timeout=30)
    m = re.search(r'frappe\.csrf_token\s*=\s*"([a-f0-9]+)"', boot.text)
    _csrf = m.group(1) if m else ""
    ses.headers["X-Frappe-CSRF-Token"] = _csrf
    print("✓ [1/9] Logged in to ERPNext")


# ── REST helpers ───────────────────────────────────────────────────────────────
def _list(doctype, filters=None, fields=None, limit=5):
    params = {
        "limit_page_length": limit,
        "filters": json.dumps(filters or []),
        "fields":  json.dumps(fields  or ["name"]),
    }
    r = ses.get(f"{BASE}/api/resource/{quote(doctype)}", params=params, timeout=30)
    r.raise_for_status()
    return r.json().get("data", [])


def _get(doctype, name):
    r = ses.get(f"{BASE}/api/resource/{quote(doctype)}/{quote(str(name))}",
                timeout=30)
    r.raise_for_status()
    return r.json()["data"]


def _create(doctype, payload):
    r = ses.post(f"{BASE}/api/resource/{quote(doctype)}",
                 json=payload, timeout=60)
    if r.status_code not in (200, 201):
        raise RuntimeError(
            f"Create '{doctype}' failed {r.status_code}:\n{r.text[:800]}"
        )
    data = r.json().get("data") or r.json()
    return data


def _update(doctype, name, payload):
    r = ses.put(f"{BASE}/api/resource/{quote(doctype)}/{quote(str(name))}",
                json=payload, timeout=60)
    if r.status_code not in (200, 201):
        raise RuntimeError(
            f"Update '{doctype}/{name}' failed {r.status_code}:\n{r.text[:800]}"
        )
    return r.json().get("data") or r.json()


def _submit(doctype, name):
    """Set docstatus=1 on a document."""
    doc = _get(doctype, name)
    doc["docstatus"] = 1
    return _update(doctype, name, doc)


# ── Steps ──────────────────────────────────────────────────────────────────────

def step_company():
    """Update Arising Packaging with LHDN TIN and address for payslip header."""
    rows = _list("Company", [["name", "=", COMPANY_NAME]])
    if not rows:
        raise RuntimeError(
            f"Company '{COMPANY_NAME}' not found. "
            "Run: docker exec prisma-erp-backend-1 bash -c "
            "'cd /home/frappe/frappe-bench && bench --site frontend execute frappe.setup_test_data.run'"
        )

    _update("Company", COMPANY_NAME, {
        "custom_company_tin_number": "C12345678901",
        "custom_integration_type":  "Sandbox",
        "address_line1": "Lot 5, Jalan Teknologi 3",
        "city":    "Shah Alam",
        "state":   "Selangor",
        "zip":     "40150",
        "country": "Malaysia",
        "company_description": "Reg. No: 202401234567  |  SST: W10-1234-56789012",
    })
    print(f"✓ [2/9] Company '{COMPANY_NAME}' updated with LHDN TIN + address")
    return COMPANY_NAME


def step_salary_structure(company):
    """Create 'Standard MY Payroll' salary structure if it does not exist."""
    rows = _list("Salary Structure", [["name", "=", STRUCT_NAME]], fields=["name", "docstatus"])
    if rows:
        existing_ds = int(rows[0].get("docstatus", 0))
        print(f"  → [3/9] Salary Structure '{STRUCT_NAME}' already exists (docstatus={existing_ds})")
        if existing_ds == 0:
            _submit("Salary Structure", STRUCT_NAME)
            print(f"     (submitted existing draft structure)")
        return STRUCT_NAME

    _create("Salary Structure", {
        "doctype":           "Salary Structure",
        "name":              STRUCT_NAME,
        "company":           company,
        "payroll_frequency": "Monthly",
        "is_active":         "Yes",
        "currency":          "MYR",
        # ── Earnings ─────────────────────────────────────────────────────────
        "earnings": [
            {
                "doctype":           "Salary Detail",
                "salary_component":  "Basic Salary",
                "amount":            5000,
                "idx":               1,
            },
            {
                "doctype":           "Salary Detail",
                "salary_component":  "Transport Allowance",
                "amount":            500,   # ≤ RM 6,000/yr → PCB-exempt per S.13(1)(a)
                "idx":               2,
            },
            {
                "doctype":           "Salary Detail",
                "salary_component":  "Housing Allowance",
                "amount":            300,
                "idx":               3,
            },
        ],
        # ── Deductions ────────────────────────────────────────────────────────
        "deductions": [
            {
                "doctype":           "Salary Detail",
                "salary_component":  "EPF Employee",
                "formula":           "base * 0.11",   # 11% — standard rate < 60
                "amount":            0,
                "idx":               1,
            },
            {
                "doctype":           "Salary Detail",
                "salary_component":  "SOCSO Employee",
                "amount":            19.75,            # RM 5,000 wage band (Schedule 2)
                "idx":               2,
            },
            {
                "doctype":           "Salary Detail",
                "salary_component":  "EIS Employee",
                "formula":           "base * 0.002",  # 0.2% — PERKESO EIS rate
                "amount":            0,
                "idx":               3,
            },
            {
                "doctype":           "Salary Detail",
                "salary_component":  "Monthly Tax Deduction",
                "amount":            130,              # PCB — single, chargeable ~MYR 59k/yr
                "idx":               4,
            },
        ],
    })
    # Salary Structure must be submitted (docstatus=1) for HRMS to find it
    _submit("Salary Structure", STRUCT_NAME)
    print(f"✓ [3/9] Salary Structure '{STRUCT_NAME}' created & submitted")
    return STRUCT_NAME


def step_employee(company):
    """Create test employee 'Siti Aminah binti Hassan' if she does not exist."""
    rows = _list("Employee",
                 [["employee_name", "=", EMP_NAME]],
                 fields=["name", "employee_name"])
    if rows:
        emp_id = rows[0]["name"]
        print(f"  → [4/9] Employee '{EMP_NAME}' already exists: {emp_id}")
        return emp_id

    doc = _create("Employee", {
        "doctype":          "Employee",
        "first_name":       "Siti Aminah",
        "last_name":        "binti Hassan",
        "employee_name":    EMP_NAME,
        "company":          company,
        "date_of_joining":  "2024-01-01",
        "date_of_birth":    "1990-07-15",
        "gender":           "Female",
        "employment_type":  "Full-time",
        "department":       "Operations - AP",
        "designation":      "Manager",
        "status":           "Active",
        # ── LHDN Malaysia Setup fields (from custom_field fixture) ───────────
        "custom_id_type":                      "NRIC",
        "custom_id_value":                     "900715345678",
        "custom_lhdn_tin":                     "IG90071534567",
        "custom_requires_self_billed_invoice": 0,   # regular employee → exempt from e-invoice
        "custom_payment_means_code":           "30 : Credit Transfer",
        "custom_bank_account_number":          "1234567890123",
        "custom_is_foreign_worker":            0,
        # custom_worker_type left blank → exemption filter skips LHDN submission
    })
    emp_id = doc["name"]
    print(f"✓ [4/9] Employee created: {emp_id}  ({EMP_NAME})")
    return emp_id


def step_salary_assignment(employee, struct, company):
    """Assign the salary structure to the employee and submit it."""
    rows = _list(
        "Salary Structure Assignment",
        [["employee", "=", employee],
         ["salary_structure", "=", struct],
         ["docstatus", "!=", 2]],
        fields=["name", "docstatus"],
    )
    if rows:
        existing_name     = rows[0]["name"]
        existing_docstatus = int(rows[0].get("docstatus", 0))
        print(f"  → [5/9] Salary Structure Assignment already exists: {existing_name}")
        if existing_docstatus == 0:
            _submit("Salary Structure Assignment", existing_name)
            print(f"     (submitted existing draft assignment)")
        return existing_name

    doc  = _create("Salary Structure Assignment", {
        "doctype":           "Salary Structure Assignment",
        "employee":          employee,
        "salary_structure":  struct,
        "from_date":         "2026-01-01",
        "company":           company,
        "base":              5000,
        "currency":          "MYR",
    })
    name = doc["name"]
    _submit("Salary Structure Assignment", name)
    print(f"✓ [5/9] Salary Structure Assignment created & submitted: {name}")
    return name


def step_salary_slip(employee, struct, company):
    """Create the Salary Slip for March 2026 (ERPNext auto-calculates components)."""
    rows = _list(
        "Salary Slip",
        [["employee",   "=", employee],
         ["start_date", "=", PERIOD_START],
         ["docstatus",  "!=", 2]],
        fields=["name", "docstatus", "gross_pay", "net_pay"],
    )
    if rows:
        slip_name  = rows[0]["name"]
        docstatus  = int(rows[0].get("docstatus", 0))
        gross      = rows[0].get("gross_pay", "?")
        net        = rows[0].get("net_pay",   "?")
        print(f"  → [6/9] Salary Slip already exists: {slip_name}  "
              f"(Gross: MYR {gross}, Net: MYR {net})")
        return slip_name, docstatus

    doc = _create("Salary Slip", {
        "doctype":          "Salary Slip",
        "employee":         employee,
        "salary_structure": struct,
        "company":          company,
        "start_date":       PERIOD_START,
        "end_date":         PERIOD_END,
        "posting_date":     POSTING_DATE,
    })
    slip_name = doc["name"]
    gross     = doc.get("gross_pay", 0)
    net       = doc.get("net_pay",   0)
    print(f"✓ [6/9] Salary Slip created: {slip_name}  "
          f"(Gross: MYR {gross}, Net: MYR {net})")
    return slip_name, 0


def step_verify_pcb(slip_name):
    """Ensure Monthly Tax Deduction (PCB) is set; patch to MYR 130 if missing."""
    doc        = _get("Salary Slip", slip_name)
    deductions = doc.get("deductions", [])

    pcb_row    = next(
        (d for d in deductions if d.get("salary_component") == "Monthly Tax Deduction"),
        None,
    )
    pcb_amount = float(pcb_row.get("amount", 0)) if pcb_row else 0.0

    if pcb_amount > 0:
        print(f"  → [7/9] PCB already set: MYR {pcb_amount:.2f}")
        return

    if pcb_row:
        for row in deductions:
            if row.get("salary_component") == "Monthly Tax Deduction":
                row["amount"] = 130.0
    else:
        deductions.append({
            "doctype":           "Salary Detail",
            "salary_component":  "Monthly Tax Deduction",
            "amount":            130.0,
        })

    _update("Salary Slip", slip_name, {**doc, "deductions": deductions})
    print(f"✓ [7/9] PCB set to MYR 130.00")


def step_submit_slip(slip_name, current_docstatus):
    """Submit the Salary Slip (docstatus 0 → 1)."""
    if current_docstatus == 1:
        print(f"  → [8/9] Salary Slip already submitted")
        return True

    try:
        _submit("Salary Slip", slip_name)
        print(f"✓ [8/9] Salary Slip submitted  (LHDN hook fires — "
              f"status will be 'Exempt' for regular employees)")
        return True
    except Exception as exc:
        msg = str(exc)
        print(f"  ⚠ [8/9] Submit failed — printing from draft instead.")
        print(f"     Reason: {msg[:300]}")
        return False


def step_download_pdf(slip_name):
    """Download the payslip as PDF (or HTML fallback) to the Desktop."""
    print(f"  [9/9] Requesting payslip PDF for {slip_name} ...")

    params = {
        "doctype":       "Salary Slip",
        "name":          slip_name,
        "format":        "EA S.61 Payslip",
        "no_letterhead": 1,
        "_lang":         "en",
    }
    r = ses.get(
        f"{BASE}/api/method/frappe.utils.print_format.download_pdf",
        params=params,
        timeout=60,
    )

    os.makedirs(DESKTOP, exist_ok=True)
    safe = slip_name.replace("/", "_").replace(" ", "_")
    out_pdf  = os.path.join(DESKTOP, f"Payslip_{safe}_Mar2026.pdf")
    out_html = out_pdf.replace(".pdf", ".html")

    ct = r.headers.get("Content-Type", "")

    if r.status_code == 200 and "application/pdf" in ct:
        with open(out_pdf, "wb") as f:
            f.write(r.content)
        print(f"✓ [9/9] PDF saved →  {out_pdf}")
        return out_pdf

    if r.status_code == 200:
        # Server returned HTML (wkhtmltopdf / weasyprint not installed)
        with open(out_html, "wb") as f:
            f.write(r.content)
        print(f"✓ [9/9] HTML saved →  {out_html}")
        print(f"     (PDF engine not available on this server — "
              f"open the HTML file in a browser and use File → Print → Save as PDF)")
        return out_html

    raise RuntimeError(
        f"PDF download failed  HTTP {r.status_code}:\n{r.text[:400]}"
    )


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    print("=" * 62)
    print("  Prisma ERP — LHDN-Compliant Payslip Generator")
    print("  Employee : Siti Aminah binti Hassan")
    print("  Period   : March 2026  (2026-03-01 → 2026-03-31)")
    print("=" * 62)

    login()
    company  = step_company()
    struct   = step_salary_structure(company)
    employee = step_employee(company)
    step_salary_assignment(employee, struct, company)
    slip_name, docstatus = step_salary_slip(employee, struct, company)
    step_verify_pcb(slip_name)
    step_submit_slip(slip_name, docstatus)
    out_file = step_download_pdf(slip_name)

    print()
    print("=" * 62)
    print("  Payslip breakdown (approximate):")
    print("    Basic Salary           MYR 5,000.00")
    print("    Transport Allowance    MYR   500.00  (PCB-exempt ≤ RM6k/yr)")
    print("    Housing Allowance      MYR   300.00")
    print("    ─────────────────────────────────────")
    print("    Gross Pay              MYR 5,800.00")
    print("    EPF Employee (11%)   − MYR   550.00")
    print("    SOCSO Employee       − MYR    19.75")
    print("    EIS Employee (0.2%)  − MYR    10.00")
    print("    PCB (Monthly Tax)    − MYR   130.00")
    print("    ─────────────────────────────────────")
    print("    Net Pay                MYR 5,090.25")
    print()
    print(f"  Output file: {out_file}")
    print("=" * 62)


if __name__ == "__main__":
    main()
