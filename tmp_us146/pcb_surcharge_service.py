"""PCB Late Payment Surcharge Service — US-146.

Section 107C(9) of the Income Tax Act 1967:
If an employer fails to remit PCB/MTD by the 15th of the following month,
LHDN imposes a 10% surcharge on the outstanding amount.

This module provides:
  - compute_pcb_due_date(month, year): Returns the 15th of the following month
  - compute_surcharge(pcb_amount): Returns 10% flat surcharge
  - check_and_flag_overdue_submissions(): Scans CP39 logs and flags overdue ones
  - send_pcb_deadline_alerts(): Sends email alerts 5 working days before due date
"""
from datetime import date, timedelta

import frappe
from frappe.utils import add_days, get_url_to_form, today

# LHDN Public Holidays — Malaysian national holidays (approximate, configurable via HRMS)
_MYS_PUBLIC_HOLIDAYS = set()  # populated lazily from ERPNext Holiday List

# Surcharge rate per Section 107C(9) ITA 1967
PCB_SURCHARGE_RATE = 0.10  # 10%

# Advance alert: 5 working days before due date
ALERT_DAYS_BEFORE = 5


def _get_malaysia_holidays(year):
    """Fetch Malaysian public holidays from ERPNext Holiday List for the given year."""
    holidays = set()
    try:
        lists = frappe.get_all(
            "Holiday List",
            filters={"country": "Malaysia"},
            fields=["name"],
        )
        for hl in lists:
            rows = frappe.get_all(
                "Holiday",
                filters={"parent": hl["name"]},
                fields=["holiday_date"],
            )
            for r in rows:
                if r["holiday_date"] and r["holiday_date"].year == year:
                    holidays.add(r["holiday_date"])
    except Exception:
        pass
    return holidays


def _next_working_day(d, holidays):
    """Advance date past weekends and public holidays."""
    while d.weekday() >= 5 or d in holidays:  # 5=Sat, 6=Sun
        d += timedelta(days=1)
    return d


def _add_working_days(start_date, n_days, holidays):
    """Add n_days working days (skip weekends and public holidays)."""
    d = start_date
    added = 0
    while added < n_days:
        d += timedelta(days=1)
        if d.weekday() < 5 and d not in holidays:  # Mon-Fri, not holiday
            added += 1
    return d


def compute_pcb_due_date(month, year):
    """Compute PCB payment due date = 15th of the month after payroll month.

    Per ITA Section 107C(1), PCB must be remitted by the 15th of the
    following month. LHDN does not officially grant grace for weekends/holidays,
    but this function also returns the raw 15th date for reference.

    Args:
        month (int): Payroll month (1-12)
        year (int): Payroll year (4-digit)

    Returns:
        date: The 15th of the month following (month, year)
    """
    month = int(month)
    year = int(year)
    if month == 12:
        due_month, due_year = 1, year + 1
    else:
        due_month, due_year = month + 1, year
    return date(due_year, due_month, 15)


def compute_surcharge(pcb_amount):
    """Compute 10% surcharge on outstanding PCB amount per Section 107C(9).

    Args:
        pcb_amount (float): Outstanding PCB/MTD amount (RM)

    Returns:
        float: Surcharge amount (RM), rounded to 2 decimal places
    """
    return round(float(pcb_amount) * PCB_SURCHARGE_RATE, 2)


def check_and_flag_overdue_submissions():
    """Scan all 'Submitted' (unpaid) CP39 logs and mark overdue ones.

    For each submission where:
      - status is 'Submitted' or 'Pending' (i.e., not 'Paid')
      - pcb_payment_due_date is before today

    Sets:
      - is_late = 1
      - status = 'Overdue'
      - estimated_surcharge = total_pcb_amount * 10%

    Returns:
        list[str]: Names of records flagged as overdue
    """
    today_date = date.fromisoformat(today())
    overdue_records = []

    logs = frappe.get_all(
        "LHDN CP39 Submission Log",
        filters={"status": ["in", ["Submitted", "Pending"]]},
        fields=["name", "pcb_payment_due_date", "total_pcb_amount", "is_late"],
    )

    for log in logs:
        due = log.get("pcb_payment_due_date")
        if not due:
            continue
        if isinstance(due, str):
            due = date.fromisoformat(due)

        if due < today_date and not log.get("is_late"):
            pcb_amt = float(log.get("total_pcb_amount") or 0)
            surcharge = compute_surcharge(pcb_amt)

            frappe.db.set_value(
                "LHDN CP39 Submission Log",
                log["name"],
                {
                    "is_late": 1,
                    "status": "Overdue",
                    "estimated_surcharge": surcharge,
                },
            )
            overdue_records.append(log["name"])

    if overdue_records:
        frappe.db.commit()

    return overdue_records


def send_pcb_deadline_alerts():
    """Send email alerts to HR Managers 5 working days before PCB due date.

    Scans CP39 logs where:
      - status is 'Submitted' or 'Pending'
      - alert date (due_date - 5 working days) == today

    Sends one email per HR Manager per record.

    Returns:
        int: Number of alerts sent
    """
    today_date = date.fromisoformat(today())
    holidays = _get_malaysia_holidays(today_date.year)
    alerts_sent = 0

    logs = frappe.get_all(
        "LHDN CP39 Submission Log",
        filters={"status": ["in", ["Submitted", "Pending"]], "is_late": 0},
        fields=["name", "company", "month", "year", "pcb_payment_due_date", "total_pcb_amount"],
    )

    for log in logs:
        due = log.get("pcb_payment_due_date")
        if not due:
            continue
        if isinstance(due, str):
            due = date.fromisoformat(due)

        # Compute the alert date: 5 working days before due date (counting backwards)
        alert_date = _subtract_working_days(due, ALERT_DAYS_BEFORE, holidays)

        if alert_date != today_date:
            continue

        # Find HR Manager email recipients
        hr_managers = _get_hr_manager_emails(log["company"])
        if not hr_managers:
            continue

        pcb_amount = float(log.get("total_pcb_amount") or 0)
        record_url = get_url_to_form("LHDN CP39 Submission Log", log["name"])

        subject = (
            f"[URGENT] PCB Remittance Due {due.strftime('%d %b %Y')} — "
            f"{log['company']} ({log['month']}/{log['year']})"
        )
        message = f"""
<p>Dear HR Manager,</p>

<p>This is a reminder that <strong>PCB/MTD remittance</strong> for the period
<strong>{log['month']}/{log['year']}</strong> is due on
<strong>{due.strftime('%d %B %Y')}</strong>.</p>

<table border="1" cellpadding="6" cellspacing="0">
  <tr><th align="left">Company</th><td>{log['company']}</td></tr>
  <tr><th align="left">Payroll Period</th><td>{log['month']}/{log['year']}</td></tr>
  <tr><th align="left">Total PCB Due (RM)</th><td>{pcb_amount:,.2f}</td></tr>
  <tr><th align="left">Payment Due Date</th><td>{due.strftime('%d %B %Y')}</td></tr>
</table>

<p><strong>⚠ Important:</strong> Failure to remit by the due date will incur a
<strong>10% surcharge</strong> on the outstanding amount (Section 107C(9) ITA 1967).
Estimated surcharge if late: <strong>RM {compute_surcharge(pcb_amount):,.2f}</strong></p>

<p><a href="{record_url}">View CP39 Submission Record</a></p>

<p>Please ensure payment is made before the due date.</p>
<p>Regards,<br>LHDN Payroll Integration — Automated Alert</p>
        """

        for email in hr_managers:
            try:
                frappe.sendmail(
                    recipients=[email],
                    subject=subject,
                    message=message,
                    delayed=False,
                )
                alerts_sent += 1
            except Exception:
                pass

    return alerts_sent


def _subtract_working_days(d, n_days, holidays):
    """Subtract n working days from date d."""
    current = d
    subtracted = 0
    while subtracted < n_days:
        current -= timedelta(days=1)
        if current.weekday() < 5 and current not in holidays:
            subtracted += 1
    return current


def _get_hr_manager_emails(company):
    """Get email addresses of users with HR Manager role for this company."""
    emails = []
    try:
        hr_users = frappe.get_all(
            "Has Role",
            filters={"role": "HR Manager", "parenttype": "User"},
            fields=["parent"],
        )
        for u in hr_users:
            user = frappe.get_doc("User", u["parent"])
            if user.email and user.enabled:
                emails.append(user.email)
    except Exception:
        pass
    return list(set(emails))


def record_late_payment(log_name, payment_date, actual_surcharge=None):
    """Record that HR has made a (late) PCB payment.

    Sets pcb_payment_date, is_late (if after due date), estimated_surcharge,
    and optionally actual_surcharge_assessed. Updates status to 'Paid'.

    Args:
        log_name (str): Name of LHDN CP39 Submission Log record
        payment_date (date|str): Date of actual payment
        actual_surcharge (float|None): LHDN-assessed surcharge if known

    Returns:
        dict: Updated fields
    """
    if isinstance(payment_date, str):
        payment_date = date.fromisoformat(payment_date)

    log = frappe.get_doc("LHDN CP39 Submission Log", log_name)
    due = log.pcb_payment_due_date
    if isinstance(due, str):
        due = date.fromisoformat(due)

    is_late = due and (payment_date > due)
    pcb_amount = float(log.total_pcb_amount or 0)
    estimated = compute_surcharge(pcb_amount) if is_late else 0.0

    update = {
        "pcb_payment_date": payment_date.isoformat(),
        "is_late": 1 if is_late else 0,
        "estimated_surcharge": estimated,
        "status": "Paid",
    }
    if actual_surcharge is not None:
        update["actual_surcharge_assessed"] = float(actual_surcharge)

    frappe.db.set_value("LHDN CP39 Submission Log", log_name, update)
    frappe.db.commit()
    return update
