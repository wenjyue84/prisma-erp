"""Senior Citizen Employee Tax Deduction Service (US-187).

Malaysia Budget 2026: Additional employer income tax deduction for hiring
senior citizens (aged 60+) extended to YA2030.

Provides:
- is_senior_citizen(dob, as_of_date) — check if employee is aged 60+
- get_senior_citizens_for_company(company, year) — employees eligible for YA
- check_senior_citizen_contract_expiry_alerts() — daily scheduler alert
"""
import frappe
from datetime import date, timedelta
from frappe.utils import getdate, today as frappe_today, flt

# Eligible year range per Budget 2026 announcement
ELIGIBLE_YA_START = 2026
ELIGIBLE_YA_END = 2030

# Alert threshold: days before contract end date
CONTRACT_EXPIRY_ALERT_DAYS = 90

# Age threshold for senior citizen classification
SENIOR_CITIZEN_AGE = 60


def is_senior_citizen(dob, as_of_date=None):
    """Return True if the employee is aged 60 or above as_of_date.

    Args:
        dob: date or str — employee date of birth
        as_of_date: date or str — reference date (defaults to today)

    Returns:
        bool
    """
    if dob is None:
        return False

    if isinstance(dob, str):
        dob = getdate(dob)

    if as_of_date is None:
        as_of_date = date.today()
    elif isinstance(as_of_date, str):
        as_of_date = getdate(as_of_date)

    # Calculate exact age
    age = as_of_date.year - dob.year
    # Adjust if birthday hasn't occurred yet this year
    if (as_of_date.month, as_of_date.day) < (dob.month, dob.day):
        age -= 1

    return age >= SENIOR_CITIZEN_AGE


def get_age_as_of(dob, as_of_date=None):
    """Return integer age as of as_of_date."""
    if dob is None:
        return None
    if isinstance(dob, str):
        dob = getdate(dob)
    if as_of_date is None:
        as_of_date = date.today()
    elif isinstance(as_of_date, str):
        as_of_date = getdate(as_of_date)
    age = as_of_date.year - dob.year
    if (as_of_date.month, as_of_date.day) < (dob.month, dob.day):
        age -= 1
    return age


def get_senior_citizens_for_company(company, year):
    """Return senior citizen employees with total wages for the given year of assessment.

    Queries Salary Slips for employees who were 60+ during the calendar year.

    Args:
        company: str — company name
        year: int — year of assessment (YA2026–YA2030)

    Returns:
        list[dict] with keys:
            employee, employee_name, department, company,
            date_of_birth, age_at_ya_start, date_of_joining,
            contract_end_date, months_employed, total_wages
    """
    year = int(year)
    ya_start = date(year, 1, 1)
    ya_end = date(year, 12, 31)

    # Fetch all active or left employees for the company with DOB set
    employees = frappe.get_all(
        "Employee",
        filters={
            "company": company,
            "date_of_birth": ["!=", None],
        },
        fields=[
            "name",
            "employee_name",
            "department",
            "company",
            "date_of_birth",
            "date_of_joining",
            "relieving_date",
            "contract_end_date",
            "status",
        ],
    )

    results = []
    for emp in employees:
        dob = emp.get("date_of_birth")
        if not dob:
            continue
        if isinstance(dob, str):
            dob = getdate(dob)

        # Employee must have been 60+ at any point during the YA
        # (specifically: 60+ at start of YA, or turns 60 during YA)
        age_at_ya_start = get_age_as_of(dob, ya_start)
        if age_at_ya_start is None:
            continue

        # Check if they were 60+ at any point in the YA
        # They turn 60 if dob.year + 60 == year or dob.year + 60 <= year
        turns_60_date = None
        try:
            turns_60_date = date(dob.year + 60, dob.month, dob.day)
        except ValueError:
            turns_60_date = date(dob.year + 60, dob.month, 28)

        # Was the employee a senior citizen for any portion of the YA?
        if turns_60_date > ya_end:
            continue  # Not yet 60 during this YA

        # Determine employment period within the YA
        joined = emp.get("date_of_joining")
        if joined and isinstance(joined, str):
            joined = getdate(joined)

        relieved = emp.get("relieving_date")
        if relieved and isinstance(relieved, str):
            relieved = getdate(relieved)

        contract_end = emp.get("contract_end_date")
        if contract_end and isinstance(contract_end, str):
            contract_end = getdate(contract_end)

        # Employment period within the YA
        emp_start = max(joined or ya_start, ya_start)
        emp_end = min(relieved or ya_end, ya_end)

        # Senior citizen period: from max(turns_60_date, emp_start) onward
        sc_start = max(turns_60_date, emp_start)

        if sc_start > emp_end:
            continue  # Not senior citizen during employment in this YA

        # Calculate months employed as senior citizen in this YA
        months = _count_months(sc_start, emp_end)
        if months <= 0:
            continue

        # Query total wages from Salary Slips during senior citizen period in YA
        total_wages = _get_total_wages(emp["name"], company, sc_start, emp_end)

        results.append({
            "employee": emp["name"],
            "employee_name": emp["employee_name"],
            "department": emp.get("department") or "",
            "company": emp["company"],
            "date_of_birth": dob,
            "age_at_ya_start": age_at_ya_start if age_at_ya_start >= 60 else get_age_as_of(dob, turns_60_date),
            "turns_60_date": turns_60_date,
            "date_of_joining": joined,
            "contract_end_date": contract_end,
            "months_employed_as_sc": months,
            "total_wages": total_wages,
        })

    return results


def _count_months(start_date, end_date):
    """Count the number of months (inclusive) between two dates."""
    if start_date > end_date:
        return 0
    months = (end_date.year - start_date.year) * 12 + (end_date.month - start_date.month) + 1
    return max(months, 0)


def _get_total_wages(employee, company, start_date, end_date):
    """Sum gross_pay from submitted Salary Slips for the employee in the date range."""
    result = frappe.db.sql(
        """
        SELECT COALESCE(SUM(ss.gross_pay), 0) as total
        FROM `tabSalary Slip` ss
        WHERE ss.employee = %(employee)s
          AND ss.company = %(company)s
          AND ss.docstatus = 1
          AND ss.start_date >= %(start_date)s
          AND ss.end_date <= %(end_date)s
        """,
        {
            "employee": employee,
            "company": company,
            "start_date": start_date.strftime("%Y-%m-%d"),
            "end_date": end_date.strftime("%Y-%m-%d"),
        },
        as_dict=True,
    )
    return flt(result[0]["total"]) if result else 0.0


def check_senior_citizen_contract_expiry_alerts():
    """Daily scheduler: alert when a senior citizen employee's contract end date is approaching.

    Creates ToDo for HR/payroll when a senior citizen's contract end date is
    within 90 days — this flags potential lapse in tax deduction eligibility.
    """
    today = date.today()
    alert_cutoff = today + timedelta(days=CONTRACT_EXPIRY_ALERT_DAYS)

    employees = frappe.get_all(
        "Employee",
        filters={
            "status": "Active",
            "date_of_birth": ["!=", None],
            "contract_end_date": ["between", [today.strftime("%Y-%m-%d"), alert_cutoff.strftime("%Y-%m-%d")]],
        },
        fields=[
            "name",
            "employee_name",
            "date_of_birth",
            "contract_end_date",
            "company",
        ],
    )

    for emp in employees:
        dob = emp.get("date_of_birth")
        if not dob:
            continue

        # Only alert for senior citizens
        if not is_senior_citizen(dob, today):
            continue

        contract_end = emp.get("contract_end_date")
        if isinstance(contract_end, str):
            contract_end = getdate(contract_end)

        days_left = (contract_end - today).days if contract_end else 0
        age = get_age_as_of(dob, today)

        msg = (
            f"Senior Citizen Employee {emp['employee_name']} ({emp['name']}) — "
            f"aged {age} — contract ends on {contract_end.strftime('%d %b %Y')} "
            f"({days_left} days). "
            f"Budget 2026 additional employer tax deduction for senior citizen hiring "
            f"(YA2026-YA2030) will lapse on contract expiry. "
            f"Renew or document if employee continues employment."
        )

        # Avoid duplicate alerts
        existing = frappe.get_all(
            "ToDo",
            filters={
                "reference_type": "Employee",
                "reference_name": emp["name"],
                "status": "Open",
                "description": ["like", "%senior citizen%contract ends%"],
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
            "date": contract_end.strftime("%Y-%m-%d") if contract_end else None,
        }).insert(ignore_permissions=True)

    frappe.db.commit()


def get_eligible_ya_range():
    """Return the list of eligible year of assessment values (YA2026-YA2030)."""
    return list(range(ELIGIBLE_YA_START, ELIGIBLE_YA_END + 1))
