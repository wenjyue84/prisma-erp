#!/usr/bin/env python3
"""
generate_feb_payslips.py
========================
Generates February 2026 payslips for all eligible employees of "Arising Packaging".

Simulates the ERPNext Payroll Entry HR-admin flow:
  Step 1 — Company & Print Format setup (one-time admin task)
  Step 2 — Salary Structure Assignment fix for EMP-00001 (DRAFT → submitted structure)
  Step 3 — Per-employee: Create Salary Slip → fix earnings & deductions → Submit
  Step 4 — Download individual PDFs to ~/Desktop/Payslips_Feb2026/

Skipped employees (no salary structure assignment):
  HR-EMP-00002  Raj Kumar
  HR-EMP-00009  Lew Wen Jyue

Statutory amounts used:
  EPF   Employee : 11%  of basic
  EPF   Employer : 13%  of basic (≤ RM 5,000);  12% (> RM 5,000)  [Second Schedule]
  SOCSO Employee : PERKESO Schedule 2 lookup; ceiling at RM 5,000 wage
  SOCSO Employer : derived as employee × (29.65 / 19.75)
  EIS   Employee : 0.2% of min(basic, 5000)
  EIS   Employer : same as EIS Employee
  PCB            : estimated Monthly Tax Deduction (single, no dependents)

Usage:
    .venv-tests/Scripts/python.exe scripts/generate_feb_payslips.py
"""

import io
import json
import os
import re
import subprocess
import sys
from urllib.parse import quote

import requests

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# ── Config ─────────────────────────────────────────────────────────────────────
BASE         = "http://localhost:8080"
USER         = "Administrator"
PWD          = "admin"
COMPANY      = "Arising Packaging"
PERIOD_START = "2026-02-01"
PERIOD_END   = "2026-02-28"
POSTING_DATE = "2026-02-28"
DESKTOP      = os.path.join(os.path.expanduser("~"), "Desktop")
OUTPUT_DIR   = os.path.join(DESKTOP, "Payslips_Feb2026")
CUSTOM_PF    = "EA S.61 Payslip (Custom)"
AP_STRUCT    = "Arising Packaging Standard"
MY_STRUCT    = "Standard MY Payroll"

# ── Per-employee payroll config for Feb 2026 ───────────────────────────────────
# SOCSO Schedule 2 (First Category — Employment Injury + Invalidity):
#   RM 2,400.01–2,500  → Employee RM 9.75
#   RM 3,100.01–3,200  → Employee RM 12.50
#   RM 3,400.01–3,500  → Employee RM 13.75
#   RM 3,700.01–3,800  → Employee RM 15.00
#   RM 4,900.01–5,000  → Employee RM 19.75   (ceiling — applies to wages > RM 5,000 too)
EMPLOYEES = [
    {
        "emp_id":       "HR-EMP-00001",
        "emp_name":     "Ahmad Farid bin Zainal",
        "basic":        5000.0,
        "structure":    AP_STRUCT,
        "needs_new_ssa": True,          # current SSA links to DRAFT "LHDN Demo Structure"
        "ssa_base":     5000.0,
        "epf_ee":       550.00,         # 11% × 5000
        "socso_ee":      19.75,         # SOCSO ceiling band
        "eis_ee":        10.00,         # 0.2% × 5000
        "pcb":          113.00,
    },
    {
        "emp_id":       "HR-EMP-00003",
        "emp_name":     "Tan Teck Hong",
        "basic":        8000.0,
        "structure":    AP_STRUCT,
        "epf_ee":       880.00,         # 11% × 8000
        "socso_ee":      19.75,         # capped at RM 5,000 SOCSO ceiling
        "eis_ee":        10.00,         # capped at RM 5,000 EIS ceiling
        "pcb":          479.00,
    },
    {
        "emp_id":       "HR-EMP-00004",
        "emp_name":     "Ahmad Fadzillah",
        "basic":        5500.0,
        "structure":    AP_STRUCT,
        "epf_ee":       605.00,         # 11% × 5500
        "socso_ee":      19.75,         # capped at RM 5,000
        "eis_ee":        10.00,         # capped at RM 5,000
        "pcb":          148.00,
    },
    {
        "emp_id":       "HR-EMP-00005",
        "emp_name":     "Lee Chee Wai",
        "basic":        3500.0,
        "structure":    AP_STRUCT,
        "epf_ee":       385.00,         # 11% × 3500
        "socso_ee":      13.75,         # Schedule 2, RM 3,400.01–3,500 band
        "eis_ee":         7.00,         # 0.2% × 3500
        "pcb":           33.00,
    },
    {
        "emp_id":       "HR-EMP-00006",
        "emp_name":     "Faizal Ibrahim",
        "basic":        2500.0,
        "structure":    AP_STRUCT,
        "epf_ee":       275.00,         # 11% × 2500
        "socso_ee":       9.75,         # Schedule 2, RM 2,400.01–2,500 band
        "eis_ee":         5.00,         # 0.2% × 2500
        "pcb":           11.00,
    },
    {
        "emp_id":       "HR-EMP-00007",
        "emp_name":     "Siti Nurhaliza",
        "basic":        3800.0,
        "structure":    AP_STRUCT,
        "epf_ee":       418.00,         # 11% × 3800
        "socso_ee":      15.00,         # Schedule 2, RM 3,700.01–3,800 band
        "eis_ee":         7.60,         # 0.2% × 3800
        "pcb":           41.00,
    },
    {
        "emp_id":       "HR-EMP-00008",
        "emp_name":     "Wong Mei Ling",
        "basic":        3200.0,
        "structure":    AP_STRUCT,
        "epf_ee":       352.00,         # 11% × 3200
        "socso_ee":      12.50,         # Schedule 2, RM 3,100.01–3,200 band
        "eis_ee":         6.40,         # 0.2% × 3200
        "pcb":           25.00,
    },
    {
        "emp_id":       "HR-EMP-00010",
        "emp_name":     "Siti Aminah binti Hassan",
        "basic":        5000.0,
        # MY Struct has fixed earnings: Basic 5000 + Transport 500 + Housing 300
        "allowances": [
            {"salary_component": "Transport Allowance", "amount": 500.0},
            {"salary_component": "Housing Allowance",   "amount": 300.0},
        ],
        "structure":    MY_STRUCT,
        "epf_ee":       550.00,
        "socso_ee":      19.75,
        "eis_ee":        10.00,
        "pcb":          130.00,
    },
]

# ── Employer section HTML patch ─────────────────────────────────────────────────
# The original template scans doc.earnings for "Employer" rows — those rows
# don't exist in our setup (employer contributions are not in earnings).
# This replacement derives employer amounts from the employee deduction rows.
_OLD_EMPLOYER_MARKER = '{%- for row in doc.earnings %}'
_NEW_EMPLOYER_SECTION = """\
{%- set _epf_ee = namespace(v=0.0) %}
  {%- set _socso_ee = namespace(v=0.0) %}
  {%- set _eis_ee = namespace(v=0.0) %}
  {%- for row in doc.deductions %}
    {%- if "EPF" in row.salary_component and "Employee" in row.salary_component %}
      {%- set _epf_ee.v = row.amount %}
    {%- elif "SOCSO" in row.salary_component and "Employee" in row.salary_component %}
      {%- set _socso_ee.v = row.amount %}
    {%- elif "EIS" in row.salary_component and "Employee" in row.salary_component %}
      {%- set _eis_ee.v = row.amount %}
    {%- endif %}
  {%- endfor %}
  {%- set employer_epf = namespace(total=0) %}
  {%- set employer_socso = namespace(total=0) %}
  {%- set employer_eis = namespace(total=0) %}
  {%- if _epf_ee.v > 0 %}
    {# EPF employer: 13% for basic ≤ RM5,000 (EPF_ee ≤ 550), 12% for basic > RM5,000 #}
    {%- set _er_rate = 12 if _epf_ee.v > 550 else 13 %}
    {%- set employer_epf.total = (_epf_ee.v / 11.0 * _er_rate) | round(2) %}
  {%- endif %}
  {%- if _socso_ee.v > 0 %}
    {# SOCSO employer: same wage-band ratio as employee (employer / employee ≈ 29.65 / 19.75) #}
    {%- set employer_socso.total = (_socso_ee.v * 29.65 / 19.75) | round(2) %}
  {%- endif %}
  {%- if _eis_ee.v > 0 %}
    {%- set employer_eis.total = _eis_ee.v %}
  {%- endif %}"""

# Sentinel: if the custom print format already contains this string, it's patched
_PATCH_SENTINEL = "_epf_ee = namespace"

# ── Session ────────────────────────────────────────────────────────────────────
ses = requests.Session()
ses.headers.update({"Accept": "application/json"})
_csrf = ""


def login():
    global _csrf
    r = ses.post(f"{BASE}/api/method/login",
                 data={"usr": USER, "pwd": PWD}, timeout=30)
    r.raise_for_status()
    boot = ses.get(f"{BASE}/app", timeout=30)
    m = re.search(r'frappe\.csrf_token\s*=\s*"([a-f0-9]+)"', boot.text)
    _csrf = m.group(1) if m else ""
    ses.headers["X-Frappe-CSRF-Token"] = _csrf
    print("  ✓ Logged in to ERPNext")


# ── REST helpers ───────────────────────────────────────────────────────────────
def _list(doctype, filters=None, fields=None, limit=20):
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
        raise RuntimeError(f"Create '{doctype}' failed {r.status_code}:\n{r.text[:600]}")
    return r.json().get("data") or r.json()


def _update(doctype, name, payload):
    r = ses.put(f"{BASE}/api/resource/{quote(doctype)}/{quote(str(name))}",
                json=payload, timeout=60)
    if r.status_code not in (200, 201):
        raise RuntimeError(f"Update '{doctype}/{name}' failed {r.status_code}:\n{r.text[:600]}")
    return r.json().get("data") or r.json()


def _cancel(doctype, name):
    r = ses.post(f"{BASE}/api/method/frappe.client.cancel",
                 json={"doctype": doctype, "name": name}, timeout=60)
    if r.status_code not in (200, 201):
        raise RuntimeError(f"Cancel '{doctype}/{name}' failed {r.status_code}:\n{r.text[:400]}")
    return r.json()


def _submit(doctype, name):
    doc = _get(doctype, name)
    doc["docstatus"] = 1
    return _update(doctype, name, doc)


# ── Step 1: Company ─────────────────────────────────────────────────────────────
def step_company():
    _update("Company", COMPANY, {
        "custom_company_tin_number": "C12345678901",
        "custom_integration_type":   "Sandbox",
        "address_line1":  "Lot 5, Jalan Teknologi 3",
        "city":    "Shah Alam",
        "state":   "Selangor",
        "zip":     "40150",
        "country": "Malaysia",
        "company_description": "Reg. No: 202401234567  |  SST: W10-1234-56789012",
    })
    print(f"  ✓ Company '{COMPANY}' LHDN fields updated")


# ── Step 2: Print Format ────────────────────────────────────────────────────────
def _read_html_template():
    """Return the EA S.61 payslip HTML template from disk."""
    script_dir  = os.path.dirname(os.path.abspath(__file__))
    repo_root   = os.path.dirname(script_dir)
    candidates  = [
        os.path.join(repo_root, "lhdn_payroll_integration", "lhdn_payroll_integration",
                     "lhdn_payroll_integration", "print_format", "ea_s61_payslip", "ea_s61_payslip.html"),
        os.path.join(repo_root, "lhdn_payroll_integration", "lhdn_payroll_integration",
                     "print_format", "ea_s61_payslip", "ea_s61_payslip.html"),
    ]
    for path in candidates:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
    return None


def _patch_employer_section(html):
    """Replace the broken employer section with the dynamic version."""
    # Find the employer namespace block and replace up to the endfor
    pattern = (
        r'\{%-\s*set employer_epf = namespace\(total=0\)\s*%\}.*?'
        r'\{%-\s*endfor\s*%\}'
    )
    replacement = (
        "{%- set employer_epf = namespace(total=0) %}\n"
        "  " + _NEW_EMPLOYER_SECTION
    )
    new_html, count = re.subn(pattern, replacement, html, flags=re.DOTALL)
    if count == 0:
        # Pattern didn't match — append a note but return original
        print("    ⚠ Could not locate employer section in template for patching")
        return html
    return new_html


def step_print_format():
    """Ensure custom print format exists with the dynamic employer section."""
    rows = _list("Print Format", [["name", "=", CUSTOM_PF]], fields=["name", "html"])
    existing_html = rows[0].get("html", "") if rows else ""

    if existing_html and _PATCH_SENTINEL in existing_html:
        print(f"  ✓ Print Format '{CUSTOM_PF}' already has employer section patch")
        return

    # Build patched HTML
    template = _read_html_template()
    if not template:
        print(f"  ⚠ HTML template not found — print format may show wrong employer amounts")
        return

    patched = _patch_employer_section(template)

    payload = {
        "doctype":               "Print Format",
        "name":                  CUSTOM_PF,
        "doc_type":              "Salary Slip",
        "module":                "LHDN Payroll Integration",
        "custom_format":         1,
        "standard":              "No",
        "print_format_type":     "Jinja",
        "print_format_builder_beta": 0,
        "disabled":              0,
        "html":                  patched,
        "font":                  "Default",
        "margin_top":    15,
        "margin_bottom": 15,
        "margin_left":   15,
        "margin_right":  15,
        "page_number":   "Hide",
        "show_section_headings": 0,
        "align_labels_right":    0,
    }
    if rows:
        _update("Print Format", CUSTOM_PF, payload)
        print(f"  ✓ Print Format '{CUSTOM_PF}' employer section patched ({len(patched):,} chars)")
    else:
        _create("Print Format", payload)
        print(f"  ✓ Print Format '{CUSTOM_PF}' created with employer section patch ({len(patched):,} chars)")


# ── Step 3: SSA fix for EMP-00001 ──────────────────────────────────────────────
def step_fix_ssa_emp001():
    """
    HR-EMP-00001's current SSA links to 'LHDN Demo Structure' which is DRAFT
    (docstatus=0). ERPNext will reject salary slip creation without a submitted
    structure. Create a new SSA pointing to the submitted 'Arising Packaging Standard'.
    """
    emp_id = "HR-EMP-00001"

    # Check if already has a valid SSA for AP Standard
    rows = _list(
        "Salary Structure Assignment",
        [["employee",         "=", emp_id],
         ["salary_structure", "=", AP_STRUCT],
         ["docstatus",        "!=", 2]],
        fields=["name", "docstatus"],
    )
    if rows:
        name = rows[0]["name"]
        ds   = int(rows[0].get("docstatus", 0))
        if ds == 0:
            _submit("Salary Structure Assignment", name)
            print(f"    ✓ EMP-00001 SSA for '{AP_STRUCT}' submitted: {name}")
        else:
            print(f"    ✓ EMP-00001 SSA for '{AP_STRUCT}' already exists: {name}")
        return

    doc  = _create("Salary Structure Assignment", {
        "doctype":          "Salary Structure Assignment",
        "employee":         emp_id,
        "salary_structure": AP_STRUCT,
        "from_date":        "2026-02-01",
        "company":          COMPANY,
        "base":             5000.0,
        "currency":         "MYR",
    })
    name = doc["name"]
    _submit("Salary Structure Assignment", name)
    print(f"    ✓ EMP-00001 new SSA created & submitted: {name}")


# ── Step 4: Per-employee salary slip ───────────────────────────────────────────

def _find_slip(emp_id):
    """Return (slip_name, docstatus) or (None, None) if no Feb 2026 slip."""
    rows = _list(
        "Salary Slip",
        [["employee",   "=", emp_id],
         ["start_date", "=", PERIOD_START],
         ["docstatus",  "!=", 2]],
        fields=["name", "docstatus", "gross_pay", "net_pay"],
    )
    if rows:
        return rows[0]["name"], int(rows[0].get("docstatus", 0))
    return None, None


def _create_slip(emp_id, structure):
    doc = _create("Salary Slip", {
        "doctype":          "Salary Slip",
        "employee":         emp_id,
        "salary_structure": structure,
        "company":          COMPANY,
        "start_date":       PERIOD_START,
        "end_date":         PERIOD_END,
        "posting_date":     POSTING_DATE,
    })
    return doc["name"]


def _fix_earnings(slip_name, cfg):
    """
    Ensure Basic Salary is set to cfg['basic'].
    For 'Arising Packaging Standard' the structure defines Basic=0 (empty formula),
    so we patch the earnings row directly.
    """
    doc      = _get("Salary Slip", slip_name)
    earnings = doc.get("earnings", [])

    basic_row = next(
        (e for e in earnings if "Basic" in e.get("salary_component", "")), None
    )

    target_basic = cfg["basic"]
    current_basic = float(basic_row.get("amount", 0)) if basic_row else 0.0

    if abs(current_basic - target_basic) < 0.01:
        return doc  # already correct

    if basic_row:
        basic_row["amount"] = target_basic
    else:
        earnings.insert(0, {
            "doctype":          "Salary Detail",
            "salary_component": "Basic Salary",
            "amount":           target_basic,
            "idx":              1,
        })

    # Re-index
    for i, row in enumerate(earnings, 1):
        row["idx"] = i

    updated = _update("Salary Slip", slip_name, {**doc, "earnings": earnings})
    return updated


def _fix_deductions(slip_name, cfg):
    """
    Patch deductions so EPF / SOCSO / EIS / PCB have the correct amounts.
    Adds missing rows (e.g. EIS Employee, which AP Standard doesn't include).
    """
    doc        = _get("Salary Slip", slip_name)
    deductions = doc.get("deductions", [])

    # Targets: (keyword1, keyword2, canonical_name, target_amount)
    targets = [
        ("EPF",   "Employee", "EPF Employee",         cfg["epf_ee"]),
        ("SOCSO", "Employee", "SOCSO Employee",        cfg["socso_ee"]),
        ("EIS",   "Employee", "EIS Employee",          cfg["eis_ee"]),
        ("Monthly Tax", None, "Monthly Tax Deduction", cfg["pcb"]),
    ]

    changed = False
    for kw1, kw2, canonical, target in targets:
        row = next(
            (d for d in deductions
             if kw1 in d.get("salary_component", "")
             and (kw2 is None or kw2 in d.get("salary_component", ""))),
            None,
        )
        if row:
            if abs(float(row.get("amount", 0)) - target) > 0.005:
                row["amount"] = target
                changed = True
        else:
            deductions.append({
                "doctype":          "Salary Detail",
                "salary_component": canonical,
                "amount":           target,
            })
            changed = True

    if not changed:
        return

    # Re-index
    for i, row in enumerate(deductions, 1):
        row["idx"] = i

    _update("Salary Slip", slip_name, {**doc, "deductions": deductions})


def _submit_slip(slip_name, docstatus):
    if docstatus == 1:
        return
    try:
        _submit("Salary Slip", slip_name)
    except Exception as exc:
        msg = str(exc)
        if "already submitted" in msg.lower():
            return
        raise


def process_employee(cfg):
    """Create, fix, and submit the Feb 2026 salary slip for one employee."""
    emp_id   = cfg["emp_id"]
    emp_name = cfg["emp_name"]
    struct   = cfg["structure"]

    print(f"\n  [{emp_id}] {emp_name}")

    # Handle EMP-00001's DRAFT structure issue
    if cfg.get("needs_new_ssa"):
        step_fix_ssa_emp001()

    slip_name, docstatus = _find_slip(emp_id)

    if slip_name:
        print(f"    → Slip already exists: {slip_name} (docstatus={docstatus})")
        # If submitted, check basic salary; if wrong, we can't patch — just use it
        if docstatus == 1:
            doc = _get("Salary Slip", slip_name)
            basic_row = next(
                (e for e in doc.get("earnings", []) if "Basic" in e.get("salary_component", "")),
                None,
            )
            current_basic = float(basic_row.get("amount", 0)) if basic_row else 0.0
            if abs(current_basic - cfg["basic"]) > 0.01:
                print(f"    ⚠  Basic salary mismatch on submitted slip ({current_basic} vs {cfg['basic']})")
                print(f"       Cancel the slip manually and re-run to fix.")
            return slip_name, docstatus
        # If draft, we can fix it in place
    else:
        slip_name = _create_slip(emp_id, struct)
        docstatus  = 0
        print(f"    ✓ Slip created: {slip_name}")

    # Fix earnings (set Basic Salary to correct amount)
    doc_after_earnings = _fix_earnings(slip_name, cfg)
    basic_now = float(
        next(
            (e.get("amount", 0) for e in (doc_after_earnings or {}).get("earnings", [])
             if "Basic" in e.get("salary_component", "")),
            cfg["basic"],
        )
    )
    print(f"    ✓ Earnings fixed  — Basic: MYR {basic_now:,.2f}")

    # Fix deductions
    _fix_deductions(slip_name, cfg)
    gross = basic_now + sum(a["amount"] for a in cfg.get("allowances", []))
    net   = gross - (cfg["epf_ee"] + cfg["socso_ee"] + cfg["eis_ee"] + cfg["pcb"])
    print(f"    ✓ Deductions fixed — Gross: MYR {gross:,.2f}  Net: MYR {net:,.2f}")

    # Submit
    _submit_slip(slip_name, docstatus)
    print(f"    ✓ Salary Slip submitted")

    return slip_name, 1


# ── Step 5: PDF download ────────────────────────────────────────────────────────
def _find_browser():
    candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    ]
    return next((p for p in candidates if os.path.exists(p)), None)


def download_pdf(slip_name, cfg):
    emp_id = cfg["emp_id"]
    r = ses.get(
        f"{BASE}/printview",
        params={
            "doctype":       "Salary Slip",
            "name":          slip_name,
            "format":        CUSTOM_PF,
            "no_letterhead": 1,
            "_lang":         "en",
        },
        timeout=60,
    )
    r.raise_for_status()

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    safe     = slip_name.replace("/", "_").replace(" ", "_")
    out_html = os.path.join(OUTPUT_DIR, f"Payslip_{emp_id}_Feb2026.html")
    out_pdf  = out_html.replace(".html", ".pdf")

    html = r.text
    if "<head>" in html and 'name="base"' not in html:
        html = html.replace("<head>", f'<head>\n<base href="{BASE}/">', 1)

    with open(out_html, "w", encoding="utf-8") as f:
        f.write(html)

    browser = _find_browser()
    if browser:
        file_url = "file:///" + out_html.replace("\\", "/")
        cmd = [
            browser,
            "--headless", "--disable-gpu", "--no-sandbox",
            "--run-all-compositor-stages-before-draw",
            f"--print-to-pdf={out_pdf}",
            file_url,
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, timeout=90)
            if result.returncode == 0 and os.path.exists(out_pdf) and os.path.getsize(out_pdf) > 1000:
                os.remove(out_html)
                print(f"    ✓ PDF saved: {os.path.basename(out_pdf)}")
                return out_pdf
        except Exception as e:
            print(f"    ⚠ Browser PDF failed: {e}")

    print(f"    ✓ HTML saved: {os.path.basename(out_html)}  (open & Ctrl+P → Save as PDF)")
    return out_html


# ── Main ────────────────────────────────────────────────────────────────────────
def main():
    print()
    print("=" * 68)
    print("  Prisma ERP — Feb 2026 Bulk Payslip Generator")
    print(f"  Company : {COMPANY}")
    print(f"  Period  : {PERIOD_START}  →  {PERIOD_END}")
    print(f"  Output  : {OUTPUT_DIR}")
    print("=" * 68)

    print("\n[SETUP]")
    login()
    step_company()
    step_print_format()

    print("\n[PAYROLL PROCESSING — simulating Payroll Entry flow]")
    results = []
    errors  = []

    for cfg in EMPLOYEES:
        try:
            slip_name, ds = process_employee(cfg)
            results.append((cfg, slip_name, ds))
        except Exception as exc:
            emp = cfg["emp_id"]
            print(f"\n  [{emp}] ✗ FAILED: {exc}")
            errors.append((cfg, str(exc)))

    print("\n[DOWNLOADING PDFs]")
    pdfs = []
    for cfg, slip_name, ds in results:
        try:
            out = download_pdf(slip_name, cfg)
            pdfs.append((cfg, out))
        except Exception as exc:
            print(f"    ⚠ PDF failed for {cfg['emp_id']}: {exc}")

    # ── Summary ─────────────────────────────────────────────────────────────────
    print()
    print("=" * 68)
    print("  SUMMARY — February 2026 Payroll")
    print("=" * 68)
    header = f"  {'EmpID':<15} {'Name':<28} {'Basic':>8}  {'Net Pay':>8}  {'Status'}"
    print(header)
    print("  " + "-" * 64)

    for cfg in EMPLOYEES:
        basic    = cfg["basic"]
        allow    = sum(a["amount"] for a in cfg.get("allowances", []))
        gross    = basic + allow
        net      = gross - (cfg["epf_ee"] + cfg["socso_ee"] + cfg["eis_ee"] + cfg["pcb"])
        emp_done = any(r[0]["emp_id"] == cfg["emp_id"] for r in results)
        status   = "✓ done" if emp_done else "✗ FAIL"
        print(f"  {cfg['emp_id']:<15} {cfg['emp_name']:<28} {basic:>8,.0f}  {net:>8,.2f}  {status}")

    if errors:
        print()
        print("  ERRORS:")
        for cfg, msg in errors:
            print(f"    {cfg['emp_id']}: {msg[:100]}")

    print()
    print(f"  Skipped: HR-EMP-00002 (Raj Kumar), HR-EMP-00009 (Lew Wen Jyue) — no SSA")
    print(f"  PDFs  : {OUTPUT_DIR}")
    print()
    print("  Deduction note:")
    print("    EPF Employer : 13% for basic ≤ RM5,000;  12% for basic > RM5,000")
    print("    SOCSO Employer: derived dynamically in print format (employer/employee ratio)")
    print("    EIS Employer  : same as EIS Employee")
    print()
    print("  LHDN e-invoice submission: skipped (regular employees exempt by default)")
    print("=" * 68)


if __name__ == "__main__":
    main()
