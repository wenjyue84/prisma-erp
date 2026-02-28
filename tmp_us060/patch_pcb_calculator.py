"""Script to patch pcb_calculator.py for US-060 BIK integration.

Run this inside the container to inject BIK support.
"""

PCB_FILE = "/home/frappe/frappe-bench/apps/lhdn_payroll_integration/lhdn_payroll_integration/services/pcb_calculator.py"

with open(PCB_FILE, "r") as f:
    content = f.read()

# 1. Add import of bik_calculator at top (after 'import frappe')
OLD_IMPORT = "import frappe"
NEW_IMPORT = """import frappe

# BIK integration (US-060) — lazy import to avoid circular dependency
def _get_bik_for_employee(employee: str, slip_date) -> float:
    \"\"\"Return monthly BIK for an employee based on the salary slip date.

    Args:
        employee: Employee document name.
        slip_date: Date object or string with the salary slip period date.

    Returns:
        float: Monthly BIK amount to add to gross income (RM). 0.0 if no record.
    \"\"\"
    try:
        if slip_date:
            if hasattr(slip_date, "year"):
                year = slip_date.year
            else:
                import datetime as _dt
                year = _dt.date.fromisoformat(str(slip_date)[:10]).year
        else:
            year = int(frappe.utils.nowdate()[:4])
        from lhdn_payroll_integration.services.bik_calculator import calculate_monthly_bik_total
        return calculate_monthly_bik_total(employee, year)
    except Exception:
        return 0.0"""

if "_get_bik_for_employee" not in content:
    content = content.replace(OLD_IMPORT, NEW_IMPORT, 1)
    print("✓ Added _get_bik_for_employee helper")
else:
    print("✓ _get_bik_for_employee already present, skipping")

# 2. Inject BIK into validate_pcb_amount
OLD_ANNUAL = """    # Extract annual income from the slip
    monthly_gross = float(doc.gross_pay or 0)
    annual_income = monthly_gross * 12"""

NEW_ANNUAL = """    # Extract annual income from the slip
    monthly_gross = float(doc.gross_pay or 0)

    # BIK (US-060): add monthly BIK to gross income before annualising
    monthly_gross += _get_bik_for_employee(doc.employee, doc.start_date or doc.end_date)

    annual_income = monthly_gross * 12"""

if "BIK (US-060)" not in content:
    if OLD_ANNUAL in content:
        content = content.replace(OLD_ANNUAL, NEW_ANNUAL, 1)
        print("✓ Injected BIK into validate_pcb_amount")
    else:
        print("✗ Could not find annual_income block — manual patch needed")
else:
    print("✓ BIK already injected into validate_pcb_amount, skipping")

with open(PCB_FILE, "w") as f:
    f.write(content)

print("Done.")
