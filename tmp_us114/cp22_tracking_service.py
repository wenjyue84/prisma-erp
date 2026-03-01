"""CP22 Submission Tracking Service (US-114).

Tracks CP22 (new employee LHDN notification) submission status on the Employee
DocType. Effective 1 September 2024, all CP22 must be filed via e-CP22 on
MyTax within 30 days of the employee's start date.

Statutory basis: Income Tax Act 1967, Section 83(2).
Penalty for non-compliance: RM200 – RM20,000.

Functions:
- check_pending_cp22_submissions(): daily scheduler job — alerts HR at 25 days,
  escalates to HR Manager at 28 days.
- get_pending_cp22_employees(): helper returning a list of pending employees
  (used by the Pending CP22 Submissions report).
"""
import frappe
from frappe.utils import add_days, date_diff, getdate, today

# Days at which we alert HR that the 30-day deadline is approaching
ALERT_DAY = 25
# Days at which we escalate to HR Manager (still no submission)
ESCALATE_DAY = 28

# Dedup markers: must appear in the ToDo description so LIKE search can find them
_PENDING_MARKER = "[CP22-PENDING]"
_ESCALATION_MARKER = "[CP22-ESCALATION]"


def check_pending_cp22_submissions():
    """Daily scheduler: create ToDo alerts for employees with Pending CP22 status.

    - Employees hired 1–25 days ago with Pending status → alert to HR role.
    - Employees hired 28+ days ago with Pending status → escalation to HR Manager.
    """
    today_date = getdate(today())

    # Window: hired 1 to 25 days ago (alert window)
    alert_from = add_days(today_date, -ALERT_DAY)
    alert_to = add_days(today_date, -1)

    pending_alert = frappe.get_all(
        "Employee",
        filters={
            "status": "Active",
            "custom_cp22_submission_status": "Pending",
            "date_of_joining": ["between", [alert_from, alert_to]],
        },
        fields=["name", "employee_name", "date_of_joining", "company"],
    )

    for emp in pending_alert:
        _create_cp22_todo(emp, today_date, role="HR User")

    # Escalation: hired 28+ days ago, still Pending
    escalate_cutoff = add_days(today_date, -ESCALATE_DAY)

    pending_escalate = frappe.get_all(
        "Employee",
        filters={
            "status": "Active",
            "custom_cp22_submission_status": "Pending",
            "date_of_joining": ["<", escalate_cutoff],
        },
        fields=["name", "employee_name", "date_of_joining", "company"],
    )

    for emp in pending_escalate:
        _create_cp22_todo(emp, today_date, role="HR Manager", escalated=True)

    if pending_alert or pending_escalate:
        frappe.db.commit()


def _create_cp22_todo(emp, today_date, role="HR User", escalated=False):
    """Create a ToDo alert for a pending CP22 employee.

    Skips creation if a non-closed ToDo already exists for the same employee
    and same role/escalation level to avoid duplicates.
    """
    emp_name = emp.get("name") if hasattr(emp, "get") else emp["name"]
    emp_full_name = emp.get("employee_name") if hasattr(emp, "get") else emp["employee_name"]
    joining_str = emp.get("date_of_joining") if hasattr(emp, "get") else emp["date_of_joining"]

    joining_date = getdate(joining_str)
    days_since = date_diff(today_date, joining_date)
    days_remaining = 30 - days_since

    if escalated:
        marker = _ESCALATION_MARKER
        description = (
            f"{marker} ESCALATION — CP22 submission overdue for {emp_full_name} "
            f"({emp_name}). Employed {days_since} days ago. "
            f"30-day LHDN filing deadline {'has passed' if days_remaining <= 0 else f'in {days_remaining} day(s)'}. "
            f"File via e-CP22 on MyTax immediately to avoid penalty (RM200–RM20,000)."
        )
        todo_priority = "High"
    else:
        marker = _PENDING_MARKER
        description = (
            f"{marker} CP22 submission pending for {emp_full_name} "
            f"({emp_name}). Employed {days_since} days ago. "
            f"{days_remaining} day(s) remaining to file via e-CP22 on MyTax."
        )
        todo_priority = "Medium"

    # Dedup: skip if open ToDo already exists for same employee and marker
    existing = frappe.get_all(
        "ToDo",
        filters={
            "reference_type": "Employee",
            "reference_name": emp_name,
            "status": "Open",
            "description": ["like", f"%{marker}%"],
        },
    )
    if existing:
        return

    frappe.get_doc(
        {
            "doctype": "ToDo",
            "reference_type": "Employee",
            "reference_name": emp_name,
            "description": description,
            "status": "Open",
            "priority": todo_priority,
            "role": role,
        }
    ).insert(ignore_permissions=True)


def get_pending_cp22_employees():
    """Return all Active employees with Pending CP22 status, with deadline info.

    Used by the 'Pending CP22 Submissions' Script Report.

    Returns a list of dicts with keys:
        employee, employee_name, company, date_of_joining,
        days_since_hire, days_remaining, status
    """
    today_date = getdate(today())

    employees = frappe.get_all(
        "Employee",
        filters={
            "status": "Active",
            "custom_cp22_submission_status": "Pending",
        },
        fields=[
            "name",
            "employee_name",
            "company",
            "date_of_joining",
            "custom_cp22_submission_status",
        ],
    )

    result = []
    for emp in employees:
        emp_name = emp.get("name") if hasattr(emp, "get") else emp["name"]
        joining_str = emp.get("date_of_joining") if hasattr(emp, "get") else emp["date_of_joining"]

        joining_date = getdate(joining_str)
        days_since = date_diff(today_date, joining_date)
        days_remaining = 30 - days_since

        result.append(
            {
                "employee": emp_name,
                "employee_name": emp.get("employee_name") if hasattr(emp, "get") else emp["employee_name"],
                "company": emp.get("company") if hasattr(emp, "get") else emp["company"],
                "date_of_joining": str(joining_date),
                "days_since_hire": days_since,
                "days_remaining": max(days_remaining, 0),
                "status": (
                    emp.get("custom_cp22_submission_status")
                    if hasattr(emp, "get")
                    else emp["custom_cp22_submission_status"]
                ),
            }
        )

    result.sort(key=lambda x: x["days_remaining"])
    return result
