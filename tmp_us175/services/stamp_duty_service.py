"""Stamp Duty Compliance Service — US-175.

Tracks employment contract stamp duty compliance under the Stamp Duty
Self-Assessment System (SAS) effective 1 January 2026.

Key rules:
- Employment contracts must be stamped within 30 days of signing via e-Duti Setem (MyTax portal).
- Fixed stamp duty: RM10 per contract (Item 4, First Schedule, Stamp Act 1949).
- Exemption threshold: RM3,000/month gross salary (raised from RM300 by Finance Bill 2025, eff. 1 Jan 2026).
- 2026 grace year: LHDN will not impose penalties on late applications in 2026.
- Late penalty after grace year: 31-90 days = RM50 or 10% (whichever higher); >90 days = RM100 or 20%.
"""

from datetime import date, datetime, timedelta

import frappe
from frappe import _

STAMP_DUTY_SAS_EFFECTIVE_DATE = date(2026, 1, 1)
EXEMPTION_THRESHOLD = 3000.0  # RM/month gross salary
STAMPING_WINDOW_DAYS = 30
STAMP_DUTY_AMOUNT = 10.0  # RM fixed


def _parse_date(d):
    """Parse date from string or return date object."""
    if d is None:
        return None
    if isinstance(d, (date, datetime)):
        return d if isinstance(d, date) and not isinstance(d, datetime) else d.date()
    try:
        return datetime.strptime(str(d), "%Y-%m-%d").date()
    except ValueError:
        return None


def get_pending_stamp_records():
    """Return list of LHDN Contract Stamp Duty records that require stamping.

    Criteria:
    - stamp_duty_exempt is NOT set (salary > RM3,000)
    - eduti_stamp_reference is blank (not yet stamped)
    - Ordered by days_overdue descending (most urgent first)

    Returns list of dicts with employee details and deadline info.
    """
    records = frappe.get_all(
        "LHDN Contract Stamp Duty",
        filters={
            "stamp_duty_exempt": 0,
            "eduti_stamp_reference": ["in", ["", None]],
        },
        fields=[
            "name",
            "employee",
            "employee_name",
            "company",
            "department",
            "contract_signing_date",
            "gross_monthly_salary",
            "stamp_duty_exempt",
            "eduti_stamp_reference",
            "contract_stamping_date",
            "stamping_deadline",
            "days_overdue",
            "compliance_status",
        ],
        order_by="days_overdue desc",
    )

    # Convert date objects to strings for JSON serialization
    result = []
    for r in records:
        result.append({
            "name": r.name,
            "employee": r.employee,
            "employee_name": r.employee_name,
            "company": r.company or "",
            "department": r.department or "",
            "contract_signing_date": str(r.contract_signing_date) if r.contract_signing_date else "",
            "gross_monthly_salary": float(r.gross_monthly_salary or 0),
            "stamp_duty_exempt": r.stamp_duty_exempt or 0,
            "eduti_stamp_reference": r.eduti_stamp_reference or "",
            "contract_stamping_date": str(r.contract_stamping_date) if r.contract_stamping_date else "",
            "stamping_deadline": str(r.stamping_deadline) if r.stamping_deadline else "",
            "days_overdue": r.days_overdue or 0,
            "compliance_status": r.compliance_status or "Pending (within 30 days)",
        })
    return result


def send_stamp_duty_alerts():
    """Daily scheduled task — US-175.

    Sends email alerts to HR Managers for employees whose employment contracts
    have passed the 30-day stamping deadline without an e-Duti Setem reference.
    Only processes contracts where gross salary > RM3,000/month (non-exempt).
    """
    today = date.today()
    pending = get_pending_stamp_records()

    # Filter to only those that are now overdue (deadline passed)
    overdue = [e for e in pending if (e.get("days_overdue") or 0) >= 0]

    if not overdue:
        return

    # Group by company
    by_company = {}
    for emp in overdue:
        company = emp["company"] or "Unknown"
        by_company.setdefault(company, []).append(emp)

    for company, employees in by_company.items():
        _send_company_alert(company, employees, today)


def _send_company_alert(company, employees, today):
    """Send a stamp duty overdue alert email for a company's employees."""
    # Find HR Manager email recipients
    hr_managers = frappe.get_all(
        "User",
        filters={"enabled": 1},
        fields=["email", "full_name"],
    )

    # Filter to users with HR Manager role
    recipients = []
    for user in hr_managers:
        user_roles = frappe.get_roles(user.email)
        if "HR Manager" in user_roles or "System Manager" in user_roles:
            recipients.append(user.email)

    if not recipients:
        frappe.logger().warning(
            f"[StampDuty] No HR Manager found for company {company} — alert not sent."
        )
        return

    # Build email body
    rows_html = ""
    for emp in employees:
        rows_html += f"""
        <tr>
            <td>{emp['employee']}</td>
            <td>{emp['employee_name']}</td>
            <td>{emp['contract_signing_date']}</td>
            <td>RM {emp['gross_monthly_salary']:,.2f}</td>
            <td>{emp['stamping_deadline']}</td>
            <td>{emp['days_overdue']} days</td>
            <td>{emp['compliance_status']}</td>
        </tr>"""

    subject = f"[Stamp Duty Alert] {len(employees)} Employment Contract(s) Require e-Duti Setem Stamping — {company}"

    message = f"""
    <p>Dear HR Manager,</p>
    <p>The following employment contracts for <strong>{company}</strong> have exceeded the
    30-day stamping window under the Stamp Duty Self-Assessment System (SAS) effective
    1 January 2026. Please stamp these contracts via the
    <a href="https://mytax.hasil.gov.my">e-Duti Setem portal on MyTax</a> and update the
    e-Duti Setem Stamp Reference in the LHDN Contract Stamp Duty record.</p>

    <table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;font-size:13px;">
        <thead>
            <tr style="background:#f0f0f0;">
                <th>Employee ID</th>
                <th>Employee Name</th>
                <th>Contract Date</th>
                <th>Monthly Salary</th>
                <th>30-Day Deadline</th>
                <th>Days Overdue</th>
                <th>Status</th>
            </tr>
        </thead>
        <tbody>{rows_html}
        </tbody>
    </table>

    <p><strong>Stamp Duty Details:</strong></p>
    <ul>
        <li>Fixed stamp duty: <strong>RM10 per contract</strong> (Item 4, First Schedule, Stamp Act 1949)</li>
        <li>Exemption: Employees earning ≤ RM3,000/month are exempt (Finance Bill 2025, eff. 1 Jan 2026)</li>
        <li>2026 Grace Year: LHDN will not impose penalties for late stamping in 2026, but compliance is still required</li>
        <li>Post-grace penalties: 31–90 days overdue = RM50 or 10% (higher); &gt;90 days = RM100 or 20% (higher)</li>
    </ul>

    <p>This alert was generated on {today.strftime('%d %B %Y')} by the LHDN Payroll Integration system.</p>
    """

    frappe.sendmail(
        recipients=recipients,
        subject=subject,
        message=message,
        now=True,
    )

    frappe.logger().info(
        f"[StampDuty] Alert sent for {len(employees)} employee(s) in {company} to {recipients}"
    )
