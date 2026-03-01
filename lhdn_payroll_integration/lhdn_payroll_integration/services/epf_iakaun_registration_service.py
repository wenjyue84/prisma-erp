"""EPF i-Akaun Registration Deadline Alert Service (US-166).

Effective October 2025, all foreign workers on valid work passes must contribute
to EPF. Employers must register newly eligible foreign employees in i-Akaun
Employer within 30 days of the mandatory commencement date (or within 30 days
of hire for new foreign workers engaged from October 2025 onwards).

Valid work passes triggering mandatory EPF:
  - Employment Pass
  - Work Permit
  - Professional Visit Pass
  - Residence Pass-Talent

Excluded:
  - Domestic servants (maids, cooks, cleaners, babysitters, drivers in private
    households) — Third Schedule EPF Act 1991

This module provides:
  - check_foreign_worker_iakaun_deadlines()  — scheduled daily job entry point
  - get_employees_needing_registration(today_date) — returns list of employee dicts
  - is_registration_overdue(employee_doc, today_date) — True if deadline has passed
  - is_legacy_foreign_worker(date_of_joining) — hired before Oct 2025 (legacy set)
"""

from datetime import date

import frappe
from frappe.utils import getdate, get_url_to_form

# EPF mandatory date for foreign workers (Oct 1, 2025)
EPF_FW_MANDATORY_DATE = date(2025, 10, 1)

# 30 days from the mandatory date: legacy workers had until Nov 14, 2025 to register
# (EPF announced Oct 15; actual mandatory date Oct 1 + 30 days registration grace = Oct 31,
#  but regulators communicated 14 November 2025 as the firm deadline)
LEGACY_REGISTRATION_DEADLINE = date(2025, 11, 14)

# 30-day registration window for new hires from Oct 2025 onwards
NEW_HIRE_DEADLINE_DAYS = 30


def is_legacy_foreign_worker(date_of_joining):
    """Return True if the employee was hired before the EPF mandatory date.

    Legacy workers (hired before Oct 1, 2025) were not required to be EPF
    members at the time of joining, so their registration deadline was a
    fixed date (Nov 14, 2025) rather than 30 days from hire.

    Args:
        date_of_joining: date or string, employee's date of joining.

    Returns:
        bool: True if hired before October 2025.
    """
    if date_of_joining is None:
        return False
    doj = getdate(date_of_joining)
    return doj < EPF_FW_MANDATORY_DATE


def get_registration_deadline(date_of_joining):
    """Return the EPF i-Akaun registration deadline for a foreign worker.

    - Legacy workers (joined before Oct 2025): fixed deadline Nov 14, 2025
    - New hires (joined Oct 2025 onwards): 30 calendar days from Date of Joining

    Args:
        date_of_joining: date or string, employee's date of joining.

    Returns:
        date: The registration deadline.
    """
    doj = getdate(date_of_joining)
    if doj < EPF_FW_MANDATORY_DATE:
        return LEGACY_REGISTRATION_DEADLINE
    from datetime import timedelta
    return doj + timedelta(days=NEW_HIRE_DEADLINE_DAYS)


def is_registration_overdue(employee_doc, today_date=None):
    """Return True if the EPF registration deadline has passed without confirmation.

    Args:
        employee_doc: dict-like with keys:
            - custom_is_foreign_worker (int/bool)
            - custom_is_domestic_servant (int/bool)
            - custom_epf_iakaun_registration_confirmed (int/bool)
            - date_of_joining (date/str)
        today_date: date to use as "today" (defaults to date.today()).

    Returns:
        bool: True if overdue (foreign worker, not domestic servant, not confirmed,
              deadline has passed).
    """
    if today_date is None:
        today_date = date.today()

    if not employee_doc.get("custom_is_foreign_worker"):
        return False
    if employee_doc.get("custom_is_domestic_servant"):
        return False
    if employee_doc.get("custom_epf_iakaun_registration_confirmed"):
        return False

    doj = employee_doc.get("date_of_joining")
    if not doj:
        return False

    deadline = get_registration_deadline(doj)
    return today_date > deadline


def get_employees_needing_registration(today_date=None):
    """Return list of active foreign employees who need EPF i-Akaun registration.

    Includes employees whose registration deadline has not yet passed (pending)
    AND those who are already overdue. Excludes domestic servants.

    Args:
        today_date: date to use as "today" (defaults to date.today()).

    Returns:
        list of dicts with employee details.
    """
    if today_date is None:
        today_date = date.today()

    # Only check from EPF mandatory date onwards
    employees = frappe.get_all(
        "Employee",
        filters={
            "status": "Active",
            "custom_is_foreign_worker": 1,
        },
        fields=[
            "name",
            "employee_name",
            "company",
            "date_of_joining",
            "custom_is_domestic_servant",
            "custom_epf_iakaun_registration_confirmed",
            "custom_epf_iakaun_registration_date",
        ],
    )

    result = []
    for emp in employees:
        # Exclude domestic servants
        if emp.get("custom_is_domestic_servant"):
            continue
        # Confirmed — skip
        if emp.get("custom_epf_iakaun_registration_confirmed"):
            continue
        # Legacy workers: only include if mandatory date has passed
        doj = emp.get("date_of_joining")
        if not doj:
            continue
        doj_date = getdate(doj)
        # Only applies from Oct 2025 — no alerts for hires after mandatory date
        # unless mandatory date has been reached
        if doj_date >= EPF_FW_MANDATORY_DATE and today_date < EPF_FW_MANDATORY_DATE:
            continue
        if doj_date < EPF_FW_MANDATORY_DATE and today_date < EPF_FW_MANDATORY_DATE:
            continue

        deadline = get_registration_deadline(doj)
        emp["registration_deadline"] = deadline
        emp["is_overdue"] = today_date > deadline
        emp["days_remaining"] = (deadline - today_date).days if not emp["is_overdue"] else 0
        emp["days_overdue"] = (today_date - deadline).days if emp["is_overdue"] else 0
        result.append(emp)

    return result


def check_foreign_worker_iakaun_deadlines(today_date=None):
    """Daily scheduled job: check EPF i-Akaun registration deadlines.

    Scans all active foreign workers (excluding domestic servants).
    Sends a high-priority compliance alert to HR Managers for any employee
    whose 30-day registration window has elapsed without confirmation.

    Args:
        today_date: date override for testing (defaults to date.today()).
    """
    if today_date is None:
        today_date = date.today()

    # If mandatory date not yet reached, no alerts needed
    if today_date < EPF_FW_MANDATORY_DATE:
        return

    overdue_employees = [
        emp for emp in get_employees_needing_registration(today_date)
        if emp["is_overdue"]
    ]

    if not overdue_employees:
        return

    # Group by company for combined alerts
    company_overdue = {}
    for emp in overdue_employees:
        company = emp["company"]
        company_overdue.setdefault(company, []).append(emp)

    for company_name, employees in company_overdue.items():
        try:
            _send_overdue_alert(company_name, employees, today_date)
        except Exception:
            frappe.log_error(
                frappe.get_traceback(),
                f"EPF i-Akaun Alert Failed: {company_name}",
            )


def _get_hr_managers(company_name=None):
    """Return list of enabled HR Manager email addresses."""
    hr_managers = frappe.get_all(
        "Has Role",
        filters={"role": "HR Manager"},
        fields=["parent"],
        ignore_permissions=True,
    )
    emails = []
    for u in hr_managers:
        user_email = frappe.db.get_value("User", {"name": u.parent, "enabled": 1}, "email")
        if user_email:
            emails.append(user_email)
    return emails


def _send_overdue_alert(company_name, employees, today_date):
    """Send EPF i-Akaun overdue registration alert to HR Managers."""
    recipients = _get_hr_managers(company_name)
    if not recipients:
        return

    count = len(employees)
    subject = (
        f"[HIGH PRIORITY] {count} Foreign Worker(s) — EPF i-Akaun Registration Overdue"
        f" — {company_name}"
    )

    rows = ""
    for emp in employees:
        deadline_str = str(emp["registration_deadline"])
        overdue_days = emp["days_overdue"]
        is_legacy = is_legacy_foreign_worker(emp["date_of_joining"])
        deadline_type = "Legacy (14 Nov 2025)" if is_legacy else f"30 days from hire"
        rows += (
            f"<tr>"
            f"<td>{emp['name']}</td>"
            f"<td>{emp['employee_name']}</td>"
            f"<td>{emp.get('date_of_joining', '')}</td>"
            f"<td>{deadline_str} ({deadline_type})</td>"
            f"<td style='color:red;'><b>{overdue_days} days</b></td>"
            f"</tr>"
        )

    message = f"""
<p>Dear HR Manager,</p>
<p>This is an automated compliance alert from the LHDN Payroll Integration system.</p>
<h3 style="color:red;">&#9888; EPF i-Akaun Registration OVERDUE</h3>
<p>The following foreign workers in <b>{company_name}</b> have not had their
EPF i-Akaun registration confirmed within the mandatory 30-day window:</p>
<table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;">
  <tr style="background:#f0f0f0;">
    <th>Employee ID</th>
    <th>Name</th>
    <th>Date of Joining</th>
    <th>Registration Deadline</th>
    <th>Days Overdue</th>
  </tr>
  {rows}
</table>
<p><b>Action Required:</b></p>
<ol>
  <li>Log in to <a href="https://i-akaun.kwsp.gov.my/">EPF i-Akaun Employer Portal</a>
      and verify/complete registration for each employee above.</li>
  <li>Once confirmed, tick <b>"EPF i-Akaun Registration Confirmed"</b> on the Employee
      record and enter the confirmation date.</li>
</ol>
<p><b>Failure to register foreign workers in EPF i-Akaun may result in employer
penalties under the EPF Act 1991.</b></p>
<hr/>
<p style="color:grey;font-size:12px;"><i>
  This is an automated message from LHDN Payroll Integration (US-166).
  EPF mandatory for foreign workers effective 1 October 2025.
  Reference: <a href="https://www.kwsp.gov.my/en/employer/responsibilities/non-malaysian-citizen-employees">
  KWSP — Non-Malaysian Citizen Employees</a>
</i></p>
"""

    frappe.sendmail(
        recipients=recipients,
        subject=subject,
        message=message,
        delayed=False,
    )
