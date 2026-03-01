"""Employment Pass (EP) Salary Threshold Validator.

Validates that expatriate employees on Employment Passes are paid at least the
ESD (Expatriate Services Division) minimum salary for their EP category before
a Salary Slip can be submitted for periods on or after 2026-06-01.

ESD Revised Thresholds (effective 2026-06-01, Cabinet approval 2025-10-17):
  Cat I  : RM 20,000 / month
  Cat II : RM 10,000 / month  (was RM 5,000-9,999)
  Cat III: RM  5,000 / month  (was RM 3,000-4,999)

US-142 acceptance criteria:
- Block Salary Slip before_submit if gross < category minimum (period_end >= 2026-06-01)
- HR can record override justification → logged to EP Override Log
- Does NOT block for "Not Applicable" EP category
"""
from datetime import date

import frappe
from frappe import _

# Effective date for the June 2026 ESD policy revision
EP_POLICY_EFFECTIVE_DATE = date(2026, 6, 1)

# Default thresholds in case the DocType table is empty
_DEFAULT_THRESHOLDS = {
    "Cat I": 20000.0,
    "Cat II": 10000.0,
    "Cat III": 5000.0,
}


def get_ep_category_minimum(ep_category: str, as_of_date: date) -> float:
    """Return the minimum salary for the given EP category on *as_of_date*.

    Reads from the EP Salary Threshold DocType first; falls back to hardcoded
    defaults so tests do not require database records.

    Args:
        ep_category: One of "Cat I", "Cat II", "Cat III", or "Not Applicable".
        as_of_date: The payroll period end date.

    Returns:
        float: Minimum monthly salary in MYR. 0.0 for "Not Applicable".
    """
    if ep_category in (None, "", "Not Applicable"):
        return 0.0

    # Query the most-recent effective threshold that is <= as_of_date
    rows = frappe.get_all(
        "EP Salary Threshold",
        filters={
            "ep_category": ep_category,
            "effective_date": ["<=", str(as_of_date)],
        },
        fields=["minimum_salary", "effective_date"],
        order_by="effective_date desc",
        limit=1,
    )
    if rows:
        return float(rows[0].minimum_salary)

    # Fall back to hardcoded defaults for periods >= 2026-06-01
    if as_of_date >= EP_POLICY_EFFECTIVE_DATE:
        return _DEFAULT_THRESHOLDS.get(ep_category, 0.0)

    return 0.0


def _get_ep_fields(employee_name: str) -> tuple:
    """Return (ep_category, ep_number, ep_expiry) for an employee.

    Returns ("Not Applicable", None, None) if the employee doc lacks EP fields.
    """
    try:
        emp = frappe.get_doc("Employee", employee_name)
        category = getattr(emp, "custom_ep_category", None) or "Not Applicable"
        ep_number = getattr(emp, "custom_ep_number", None)
        ep_expiry_raw = getattr(emp, "custom_ep_expiry_date", None)
        ep_expiry = None
        if ep_expiry_raw:
            if isinstance(ep_expiry_raw, date):
                ep_expiry = ep_expiry_raw
            else:
                from datetime import datetime
                ep_expiry = datetime.strptime(str(ep_expiry_raw), "%Y-%m-%d").date()
        return category, ep_number, ep_expiry
    except Exception:
        return "Not Applicable", None, None


def validate_ep_salary_before_submit(doc, method=None):
    """Hook: called on Salary Slip before_submit.

    Blocks submission if the employee is an EP holder and gross salary is below
    the ESD category minimum for periods from 2026-06-01 onwards.

    An HR Manager can bypass the block by recording a justification in
    `doc.custom_ep_override_justification`.  The override is logged to the
    EP Override Log doctype for audit purposes.
    """
    period_end = doc.end_date
    if not period_end:
        return

    if isinstance(period_end, str):
        period_end = date.fromisoformat(period_end)
    elif hasattr(period_end, "date"):
        period_end = period_end.date()

    # Policy only applies from 2026-06-01
    if period_end < EP_POLICY_EFFECTIVE_DATE:
        return

    ep_category, ep_number, ep_expiry = _get_ep_fields(doc.employee)

    if ep_category in (None, "", "Not Applicable"):
        return

    minimum = get_ep_category_minimum(ep_category, period_end)
    if minimum <= 0:
        return

    gross_salary = float(doc.gross_pay or 0)

    if gross_salary >= minimum:
        return  # Compliant — nothing to do

    # Below threshold — check for override justification
    justification = getattr(doc, "custom_ep_override_justification", None) or ""
    justification = justification.strip()

    if justification:
        # Record override in audit log and allow submission
        _log_ep_override(doc, ep_category, gross_salary, minimum, justification)
        frappe.msgprint(
            _(
                "EP salary override recorded for {0} ({1}). "
                "Gross RM {2:,.2f} is below {3} minimum RM {4:,.2f}. "
                "Justification: {5}"
            ).format(
                doc.employee_name or doc.employee,
                ep_category,
                gross_salary,
                ep_category,
                minimum,
                justification,
            ),
            title=_("EP Override Logged"),
            indicator="orange",
        )
        return

    # No justification — block submission
    frappe.throw(
        _(
            "EP Salary Compliance Violation: {0} ({1}) is on Employment Pass {2} "
            "but gross salary RM {3:,.2f} is below the ESD minimum RM {4:,.2f} for {2} "
            "effective 1 June 2026 (ESD Announcement, Cabinet approval 17 Oct 2025).\n\n"
            "To override, enter a justification in 'EP Override Justification' on the Salary Slip."
        ).format(
            doc.employee_name or doc.employee,
            ep_number or "N/A",
            ep_category,
            gross_salary,
            minimum,
        ),
        title=_("EP Salary Threshold Not Met"),
    )


def _log_ep_override(doc, ep_category: str, gross_salary: float, minimum: float, justification: str):
    """Create an EP Override Log record for the audit trail."""
    try:
        log = frappe.get_doc({
            "doctype": "EP Override Log",
            "salary_slip": doc.name,
            "employee": doc.employee,
            "ep_category": ep_category,
            "override_date": frappe.utils.now(),
            "gross_salary": gross_salary,
            "category_minimum": minimum,
            "override_justification": justification,
            "override_by": frappe.session.user,
        })
        log.insert(ignore_permissions=True)
    except Exception as exc:
        # Non-blocking — just log the error
        frappe.log_error(
            f"EP Override Log insert failed for {doc.name}: {exc}",
            "EP Validator Service",
        )


def get_ep_expiry_alerts(days_ahead: int = 90) -> list:
    """Return EP holders whose EP expires within *days_ahead* days.

    Used by the compliance dashboard / scheduled alert job.

    Returns:
        list[dict]: Each dict has keys: employee, employee_name, ep_category,
                    ep_number, ep_expiry_date, days_to_expiry.
    """
    from datetime import timedelta

    today = date.today()
    cutoff = today + timedelta(days=days_ahead)

    # Get all employees with an EP category set and expiry date within window
    employees = frappe.get_all(
        "Employee",
        filters={
            "status": "Active",
            "custom_ep_category": ["in", ["Cat I", "Cat II", "Cat III"]],
            "custom_ep_expiry_date": ["between", [str(today), str(cutoff)]],
        },
        fields=[
            "name", "employee_name",
            "custom_ep_category", "custom_ep_number",
            "custom_ep_expiry_date",
        ],
    )

    alerts = []
    for emp in employees:
        expiry = emp.custom_ep_expiry_date
        if isinstance(expiry, str):
            from datetime import datetime
            expiry = datetime.strptime(expiry, "%Y-%m-%d").date()
        days_left = (expiry - today).days
        alerts.append({
            "employee": emp.name,
            "employee_name": emp.employee_name,
            "ep_category": emp.custom_ep_category,
            "ep_number": emp.custom_ep_number,
            "ep_expiry_date": str(expiry),
            "days_to_expiry": days_left,
        })

    return sorted(alerts, key=lambda x: x["days_to_expiry"])
