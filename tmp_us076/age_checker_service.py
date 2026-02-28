"""Age-Based Statutory Rate Checker Service (US-076).

Handles:
- before_submit validation on Salary Slip: warn when EPF/SOCSO/EIS components
  do not match age-appropriate statutory rates.
- Daily scheduler: alert payroll users when an employee is within 90 days of
  turning 60 (statutory rate transition).
"""
import frappe
from datetime import date, timedelta

from lhdn_payroll_integration.lhdn_payroll_integration.utils.statutory_rates import (
    get_statutory_rates_for_employee,
)

# Component names to inspect on Salary Slip deductions
SOCSO_EMPLOYEE_COMPONENT = "SOCSO Employee"
EIS_EMPLOYEE_COMPONENT = "EIS Employee"
EPF_EMPLOYEE_COMPONENT = "EPF Employee"


def _get_component_amount(salary_slip_doc, component_name):
    """Return the deduction amount for *component_name* on the Salary Slip (0 if absent)."""
    for row in salary_slip_doc.get("deductions") or []:
        if row.salary_component == component_name:
            return float(row.amount or 0)
    return 0.0


def validate_statutory_rates_before_submit(doc, method):
    """Before Salary Slip submit: warn if statutory deductions don't match age-based rates.

    Does NOT raise an exception — only shows a warning so payroll staff can
    override if the employee has a valid elected rate or other arrangement.
    """
    try:
        from frappe.utils import getdate

        employee_name = doc.employee
        if not employee_name:
            return

        payroll_date = getdate(doc.end_date or doc.posting_date)
        rates = get_statutory_rates_for_employee(employee_name, payroll_date)

        if not rates.get("over_60"):
            return  # Under 60 — standard rates, no special check required

        warnings = []

        # SOCSO: should be 0 for age >= 60
        socso_amt = _get_component_amount(doc, SOCSO_EMPLOYEE_COMPONENT)
        if socso_amt > 0:
            warnings.append(
                f"SOCSO Employee deduction is RM{socso_amt:.2f} but employee is aged "
                f"{rates['age']} (>=60) -- SOCSO coverage ceases at age 60 per SOCSO Act 1969."
            )

        # EIS: should be 0 for age >= 60
        eis_amt = _get_component_amount(doc, EIS_EMPLOYEE_COMPONENT)
        if eis_amt > 0:
            warnings.append(
                f"EIS Employee deduction is RM{eis_amt:.2f} but employee is aged "
                f"{rates['age']} (>=60) -- EIS coverage ceases at age 60 per EIS Act 2017."
            )

        # EPF: should be 5.5% (EPF_OVER_60_EMPLOYEE_RATE) for age >= 60
        epf_amt = _get_component_amount(doc, EPF_EMPLOYEE_COMPONENT)
        gross = float(doc.gross_pay or 0)
        if gross > 0 and epf_amt > 0:
            actual_epf_rate = epf_amt / gross
            expected_epf_rate = rates["epf_employee_rate"]  # 0.055
            deviation = abs(actual_epf_rate - expected_epf_rate) / expected_epf_rate
            if deviation > 0.05:  # > 5% deviation from expected rate
                warnings.append(
                    f"EPF Employee rate appears to be {actual_epf_rate:.1%} but "
                    f"statutory rate for age {rates['age']} (>=60) is "
                    f"{expected_epf_rate:.1%} per EPF Act 1991 Third Schedule."
                )

        if warnings:
            frappe.msgprint(
                "<b>Statutory Rate Warning (Age 60+)</b><br>" + "<br>".join(warnings),
                title="Age-Based Statutory Rate Check",
                indicator="orange",
            )

    except Exception:
        # Never block submission due to check errors
        frappe.log_error(frappe.get_traceback(), "Age statutory rate check failed")


# ---------------------------------------------------------------------------
# Daily Scheduler — Approaching Age 60 Alert
# ---------------------------------------------------------------------------

AGE_60_ALERT_DAYS = 90  # Alert when within 90 days of 60th birthday


def _get_employees_approaching_60():
    """Return employees whose 60th birthday falls within the next 90 days."""
    today = date.today()
    alert_cutoff = today + timedelta(days=AGE_60_ALERT_DAYS)

    employees = frappe.get_all(
        "Employee",
        filters={"status": "Active", "date_of_birth": ["!=", None]},
        fields=["name", "employee_name", "date_of_birth", "company"],
    )

    approaching = []
    for emp in employees:
        # Use dict-style access (works for both plain dicts and frappe._dict)
        dob = emp.get("date_of_birth") if hasattr(emp, "get") else emp["date_of_birth"]
        if isinstance(dob, str):
            from frappe.utils import getdate
            dob = getdate(dob)
        if dob is None:
            continue

        # 60th birthday
        try:
            birthday_60 = date(dob.year + 60, dob.month, dob.day)
        except ValueError:
            # Handle Feb 29 leap-year edge case
            birthday_60 = date(dob.year + 60, dob.month, 28)

        if today <= birthday_60 <= alert_cutoff:
            emp["birthday_60"] = birthday_60
            emp["days_until_60"] = (birthday_60 - today).days
            approaching.append(emp)

    return approaching


def check_approaching_age_60():
    """Daily scheduler: create ToDo alerts for employees approaching age 60.

    Employees within 90 days of turning 60 will have their payroll statutory
    rates change (EPF 5.5%/4%, SOCSO/EIS exempt). Payroll managers need advance
    notice to update salary components before the transition month.
    """
    approaching = _get_employees_approaching_60()
    if not approaching:
        return

    for emp in approaching:
        msg = (
            f"Employee {emp['employee_name']} ({emp['name']}) turns 60 on "
            f"{emp['birthday_60'].strftime('%d %b %Y')} "
            f"({emp['days_until_60']} days). "
            f"Statutory rates will change: EPF 5.5% employee / 4% employer; "
            f"SOCSO and EIS coverage will cease."
        )
        # Avoid duplicate ToDos: check if one already exists for this employee
        existing = frappe.get_all(
            "ToDo",
            filters={
                "reference_type": "Employee",
                "reference_name": emp["name"],
                "status": "Open",
                "description": ["like", "%turns 60%"],
            },
        )
        if existing:
            continue

        frappe.get_doc(
            {
                "doctype": "ToDo",
                "reference_type": "Employee",
                "reference_name": emp["name"],
                "description": msg,
                "status": "Open",
                "priority": "High",
                "date": emp["birthday_60"].strftime("%Y-%m-%d"),
            }
        ).insert(ignore_permissions=True)

    frappe.db.commit()
