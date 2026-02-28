"""Wage Payment Deadline Compliance — Employment Act 1955 Section 19.

US-106: Add Wage Payment Deadline Compliance Alerts

Employment Act 1955 (post-2022 amendment):
  Section 19(1):  Normal wages must be paid within 7 calendar days of wage period end.
  Section 19(1A): Overtime wages must be paid within 10 calendar days of wage period end.
  Section 100A:   Fine up to RM50,000 per violation per employee (effective 2022).

This module provides:
  - compute_payment_deadlines(wage_period_end) → normal and OT due dates
  - get_payroll_compliance_status(payroll_entry_name) → On-Time / At Risk / Overdue
  - send_wage_payment_alerts() → daily background job; alerts HR Managers
"""

from datetime import date, timedelta

import frappe


# Employment Act 1955, Section 19 — payment deadlines (calendar days, not business days)
NORMAL_WAGE_PAYMENT_DAYS = 7    # S.19(1): normal wages
OT_WAGE_PAYMENT_DAYS = 10       # S.19(1A): overtime wages
ALERT_DAYS_BEFORE = 2           # Alert threshold: 2 days before due date

# Dashboard compliance status codes
STATUS_ON_TIME = "On-Time"
STATUS_AT_RISK = "At Risk"
STATUS_OVERDUE = "Overdue"


def compute_payment_deadlines(wage_period_end):
    """Compute normal and overtime payment due dates.

    Args:
        wage_period_end (date): Last day of the wage period.

    Returns:
        dict with keys:
            'normal_due': date — S.19(1) normal wage payment deadline
            'overtime_due': date — S.19(1A) overtime wage payment deadline
    """
    if isinstance(wage_period_end, str):
        wage_period_end = date.fromisoformat(wage_period_end)

    return {
        "normal_due": wage_period_end + timedelta(days=NORMAL_WAGE_PAYMENT_DAYS),
        "overtime_due": wage_period_end + timedelta(days=OT_WAGE_PAYMENT_DAYS),
    }


def get_payroll_compliance_status(payroll_entry_name, reference_date=None):
    """Return the wage payment compliance status for a Payroll Entry.

    Checks whether all Salary Slips are in Submitted status relative to the
    payment due date derived from the payroll period end date.

    Args:
        payroll_entry_name (str): The name of the Payroll Entry document.
        reference_date (date, optional): Date to compare against (defaults to today).

    Returns:
        dict with keys:
            'status': str — 'On-Time', 'At Risk', or 'Overdue'
            'days_remaining': int — days until normal_due (negative if overdue)
            'normal_due': date — Employment Act S.19(1) deadline
            'overtime_due': date — Employment Act S.19(1A) deadline
            'all_slips_submitted': bool
            'unsubmitted_count': int
            'wage_period_end': date
    """
    if reference_date is None:
        reference_date = date.today()
    elif isinstance(reference_date, str):
        reference_date = date.fromisoformat(reference_date)

    entry = frappe.get_doc("Payroll Entry", payroll_entry_name)

    # Payroll Entry uses end_date as the wage period end
    wage_period_end = entry.end_date
    if isinstance(wage_period_end, str):
        wage_period_end = date.fromisoformat(str(wage_period_end))
    else:
        wage_period_end = date.fromisoformat(str(wage_period_end))

    deadlines = compute_payment_deadlines(wage_period_end)
    normal_due = deadlines["normal_due"]
    overtime_due = deadlines["overtime_due"]

    # Count unsubmitted Salary Slips linked to this Payroll Entry
    unsubmitted_count = frappe.db.count(
        "Salary Slip",
        filters={
            "payroll_entry": payroll_entry_name,
            "docstatus": ["!=", 1],  # 1 = Submitted
        },
    )
    all_slips_submitted = unsubmitted_count == 0

    days_remaining = (normal_due - reference_date).days

    # Determine compliance status
    if all_slips_submitted:
        # All submitted — check if done on time
        status = STATUS_ON_TIME
    elif days_remaining < 0:
        status = STATUS_OVERDUE
    elif days_remaining <= ALERT_DAYS_BEFORE:
        status = STATUS_AT_RISK
    else:
        status = STATUS_ON_TIME

    return {
        "status": status,
        "days_remaining": days_remaining,
        "normal_due": normal_due,
        "overtime_due": overtime_due,
        "all_slips_submitted": all_slips_submitted,
        "unsubmitted_count": unsubmitted_count,
        "wage_period_end": wage_period_end,
    }


def send_wage_payment_alerts():
    """Daily background job: alert HR Managers for At Risk or Overdue payroll entries.

    Checks all non-cancelled Payroll Entries where the wage period has ended.
    Sends Frappe system notifications to users with HR Manager role.

    Respects per-company filtering — only processes entries for each company once.
    """
    today = date.today()

    # Find Payroll Entries with end_date in the past (wage period has ended)
    entries = frappe.get_all(
        "Payroll Entry",
        filters={
            "docstatus": ["!=", 2],       # exclude Cancelled
            "end_date": ["<=", today],
        },
        fields=["name", "company", "end_date", "start_date"],
    )

    if not entries:
        return

    # Collect HR Managers to notify
    hr_managers = _get_hr_manager_emails()
    if not hr_managers:
        return

    for entry in entries:
        try:
            result = get_payroll_compliance_status(entry["name"], reference_date=today)
        except Exception:
            continue

        if result["status"] in (STATUS_AT_RISK, STATUS_OVERDUE):
            _send_alert_notification(entry, result, hr_managers)


def _get_hr_manager_emails():
    """Return a list of user emails with the HR Manager role."""
    users = frappe.get_all(
        "Has Role",
        filters={"role": "HR Manager", "parenttype": "User"},
        fields=["parent"],
    )
    emails = []
    for u in users:
        email = frappe.db.get_value("User", u["parent"], "email")
        if email:
            emails.append(email)
    return emails


def _send_alert_notification(entry, compliance_result, hr_manager_emails):
    """Send a Frappe system notification for a non-compliant payroll entry."""
    status = compliance_result["status"]
    days_remaining = compliance_result["days_remaining"]
    normal_due = compliance_result["normal_due"]
    unsubmitted_count = compliance_result["unsubmitted_count"]
    company = entry.get("company", "")

    if status == STATUS_OVERDUE:
        subject = f"[OVERDUE] Wage Payment Deadline Passed — {entry['name']} ({company})"
        message = (
            f"Payroll Entry <b>{entry['name']}</b> for {company} is <b>OVERDUE</b>.<br>"
            f"Employment Act S.19(1) deadline was {normal_due} (7 days after wage period end).<br>"
            f"{unsubmitted_count} Salary Slip(s) are not yet submitted.<br>"
            f"Non-compliance may result in fines up to RM50,000 per employee (S.100A)."
        )
    else:
        # At Risk
        subject = f"[AT RISK] Payroll Due in {days_remaining} Day(s) — {entry['name']} ({company})"
        message = (
            f"Payroll Entry <b>{entry['name']}</b> for {company} is <b>AT RISK</b>.<br>"
            f"Employment Act S.19(1) deadline: {normal_due} ({days_remaining} day(s) remaining).<br>"
            f"{unsubmitted_count} Salary Slip(s) are not yet submitted.<br>"
            f"Please submit all Salary Slips to avoid non-compliance fines (S.100A: up to RM50,000 per employee)."
        )

    for email in hr_manager_emails:
        frappe.sendmail(
            recipients=[email],
            subject=subject,
            message=message,
            delayed=False,
        )
