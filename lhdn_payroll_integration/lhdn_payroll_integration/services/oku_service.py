"""OKU (Disabled Employee) Double Deduction Service (US-194).

Malaysia Income Tax Act 1967: Section 34(6)(n) — additional deduction on
remuneration paid to disabled employees holding a valid Kad OKU from
Jabatan Kebajikan Masyarakat.

Budget 2026 extended this double deduction to YA2030.

Provides:
- is_oku_eligible_month(monthly_remuneration): checks ≤ RM4,000
- compute_annual_double_deduction(total_annual_remuneration): min(..., RM48,000)
- check_oku_expiry_alerts(): daily scheduler — warn 60 days before Kad OKU expiry
- get_oku_employees_for_company(company, year): list OKU employees with wages
- get_eligible_ya_range(): returns [2026, ..., 2030]
"""
import frappe
from datetime import date, timedelta
from frappe.utils import getdate, flt

# Double deduction cap per OKU employee per year of assessment (ITA 1967 S.34(6)(n))
OKU_ANNUAL_CAP = 48000.0

# Monthly salary cap for eligibility — employee must earn ≤ RM4,000/month
OKU_MONTHLY_CAP = 4000.0

# Days before Kad OKU expiry to trigger HR alert
OKU_EXPIRY_ALERT_DAYS = 60

# Eligible YA range per Budget 2026 announcement
ELIGIBLE_YA_START = 2026
ELIGIBLE_YA_END = 2030


def is_oku_eligible_month(monthly_remuneration):
    """Return True if monthly remuneration ≤ RM4,000 (eligibility for double deduction).

    Employees earning above RM4,000/month in any given month do not qualify
    for that month's remuneration to count toward the double deduction.

    Args:
        monthly_remuneration: float — gross monthly cash remuneration

    Returns:
        bool
    """
    return flt(monthly_remuneration) <= OKU_MONTHLY_CAP


def compute_annual_double_deduction(total_annual_remuneration):
    """Compute eligible double deduction base: min(total_annual_remuneration, RM48,000).

    Under ITA 1967 S.34(6)(n), the employer gets an additional deduction equal
    to the eligible remuneration paid (i.e., the total qualifying remuneration
    is deductible twice). The qualifying remuneration cap is RM48,000 per year.

    Args:
        total_annual_remuneration: float — total qualifying cash remuneration paid

    Returns:
        float — the eligible additional deduction amount (capped at RM48,000)
    """
    return min(flt(total_annual_remuneration), OKU_ANNUAL_CAP)


def check_oku_expiry_alerts():
    """Daily scheduler: create ToDo when Kad OKU expiry is within 60 days.

    Alerts HR/payroll so they can request renewal from Jabatan Kebajikan
    Masyarakat before the Kad OKU expires, maintaining double deduction
    eligibility for the year of assessment.
    """
    today = date.today()
    alert_cutoff = today + timedelta(days=OKU_EXPIRY_ALERT_DAYS)

    employees = frappe.get_all(
        "Employee",
        filters={
            "status": "Active",
            "custom_is_oku": 1,
            "custom_kad_oku_expiry_date": [
                "between",
                [today.strftime("%Y-%m-%d"), alert_cutoff.strftime("%Y-%m-%d")],
            ],
        },
        fields=[
            "name",
            "employee_name",
            "company",
            "custom_kad_oku_number",
            "custom_kad_oku_expiry_date",
        ],
    )

    for emp in employees:
        expiry = emp.get("custom_kad_oku_expiry_date")
        if isinstance(expiry, str):
            expiry = getdate(expiry)

        days_left = (expiry - today).days if expiry else 0
        kad_num = emp.get("custom_kad_oku_number") or "N/A"

        msg = (
            f"OKU Employee {emp['employee_name']} ({emp['name']}) — "
            f"Kad OKU {kad_num} expires on "
            f"{expiry.strftime('%d %b %Y') if expiry else 'N/A'} "
            f"({days_left} days). "
            f"Double deduction eligibility under ITA 1967 S.34(6)(n) "
            f"(extended to YA2030 per Budget 2026) requires a valid Kad OKU. "
            f"Request renewal from Jabatan Kebajikan Masyarakat before expiry."
        )

        # Avoid duplicate open alerts for this employee
        existing = frappe.get_all(
            "ToDo",
            filters={
                "reference_type": "Employee",
                "reference_name": emp["name"],
                "status": "Open",
                "description": ["like", "%Kad OKU%expires%"],
            },
        )
        if existing:
            continue

        frappe.get_doc({
            "doctype": "ToDo",
            "reference_type": "Employee",
            "reference_name": emp["name"],
            "description": msg,
            "status": "Open",
            "priority": "High",
            "date": expiry.strftime("%Y-%m-%d") if expiry else None,
        }).insert(ignore_permissions=True)

    frappe.db.commit()


def get_oku_employees_for_company(company, year):
    """Return OKU employees with annual remuneration data for the given YA.

    Queries Salary Slips for employees with custom_is_oku = 1.
    Computes total remuneration, eligible (≤RM4,000/month) remuneration,
    and the Section 34(6)(n) additional deduction amount.

    Args:
        company: str — company name
        year: int — year of assessment (YA2026–YA2030)

    Returns:
        list[dict] with keys:
            employee, employee_name, department, company,
            kad_oku_number, kad_oku_expiry_date,
            total_annual_remuneration, eligible_remuneration,
            eligible_deduction, double_deduction,
            months_with_eligible_salary, all_months_eligible
    """
    year = int(year)
    ya_start = date(year, 1, 1)
    ya_end = date(year, 12, 31)

    employees = frappe.get_all(
        "Employee",
        filters={"company": company, "custom_is_oku": 1},
        fields=[
            "name",
            "employee_name",
            "department",
            "company",
            "custom_kad_oku_number",
            "custom_kad_oku_expiry_date",
            "status",
        ],
    )

    results = []
    for emp in employees:
        slips = frappe.db.sql(
            """
            SELECT ss.start_date, ss.end_date, ss.gross_pay
            FROM `tabSalary Slip` ss
            WHERE ss.employee = %(employee)s
              AND ss.company = %(company)s
              AND ss.docstatus = 1
              AND ss.start_date >= %(start_date)s
              AND ss.end_date <= %(end_date)s
            ORDER BY ss.start_date
            """,
            {
                "employee": emp["name"],
                "company": company,
                "start_date": ya_start.strftime("%Y-%m-%d"),
                "end_date": ya_end.strftime("%Y-%m-%d"),
            },
            as_dict=True,
        )

        total_remuneration = 0.0
        eligible_remuneration = 0.0
        months_with_eligible_salary = 0
        months_exceeding_cap = 0

        for slip in slips:
            gross = flt(slip["gross_pay"])
            total_remuneration += gross
            if is_oku_eligible_month(gross):
                eligible_remuneration += gross
                months_with_eligible_salary += 1
            else:
                months_exceeding_cap += 1

        # Skip employees with no salary slips in this YA (unless active)
        if not slips:
            continue

        eligible_deduction = compute_annual_double_deduction(eligible_remuneration)
        double_deduction = eligible_deduction  # Section 34(6)(n) additional deduction

        expiry = emp.get("custom_kad_oku_expiry_date")
        if expiry and isinstance(expiry, str):
            expiry = getdate(expiry)

        all_months_eligible = months_exceeding_cap == 0 and months_with_eligible_salary > 0

        results.append({
            "employee": emp["name"],
            "employee_name": emp["employee_name"],
            "department": emp.get("department") or "",
            "company": emp["company"],
            "kad_oku_number": emp.get("custom_kad_oku_number") or "",
            "kad_oku_expiry_date": expiry,
            "total_annual_remuneration": total_remuneration,
            "eligible_remuneration": eligible_remuneration,
            "eligible_deduction": eligible_deduction,
            "double_deduction": double_deduction,
            "months_with_eligible_salary": months_with_eligible_salary,
            "all_months_eligible": 1 if all_months_eligible else 0,
        })

    results.sort(key=lambda r: (r.get("department") or "", r.get("employee_name") or ""))
    return results


def get_eligible_ya_range():
    """Return list of eligible year of assessment values (YA2026–YA2030)."""
    return list(range(ELIGIBLE_YA_START, ELIGIBLE_YA_END + 1))
