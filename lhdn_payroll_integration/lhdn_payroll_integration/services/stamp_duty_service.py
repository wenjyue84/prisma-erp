"""Stamp Duty Compliance Service for Employment Contracts.

From 1 January 2026, the Stamp Duty Self-Assessment System (SAS) mandates
that all employment contracts be stamped within 30 days of signing via the
e-Duti Setem portal on MyTax (mytax.hasil.gov.my).

Fixed duty: RM10 per contract under Item 4, First Schedule, Stamp Act 1949.
Exemption: contracts where gross monthly salary <= RM3,000/month (Finance Bill 2025).

Late penalties (post-2026 grace year):
  31-90 days: RM50 or 10% whichever higher
  >90 days: RM100 or 20% whichever higher

US-175: Track Employment Contract Stamp Duty Compliance via e-Duti Setem MyTax
"""
from datetime import date, timedelta

import frappe

# Statutory constants
STAMP_DUTY_AMOUNT = 10.0                           # RM10 fixed per contract
EXEMPTION_THRESHOLD = 3000.0                       # RM3,000/month from Finance Bill 2025
STAMPING_WINDOW_DAYS = 30                          # Must stamp within 30 days of signing
STAMP_DUTY_SAS_EFFECTIVE_DATE = date(2026, 1, 1)  # e-Duti Setem SAS mandatory from 1 Jan 2026

# Late penalty brackets (post-2026 grace year)
_PENALTY_BRACKET_1 = (31, 90)       # 31-90 days late
_PENALTY_BRACKET_1_FIXED = 50.0     # RM50 fixed
_PENALTY_BRACKET_1_PCT = 0.10       # 10% of duty
_PENALTY_BRACKET_2_START = 91       # >90 days late
_PENALTY_BRACKET_2_FIXED = 100.0    # RM100 fixed
_PENALTY_BRACKET_2_PCT = 0.20       # 20% of duty


def _parse_date(value):
    """Parse a date value to a Python date object.

    Args:
        value: str ("YYYY-MM-DD"), date, datetime, or None.

    Returns:
        date | None
    """
    if value is None:
        return None
    if isinstance(value, date):
        return value
    if hasattr(value, "date"):
        return value.date()
    # string
    try:
        from frappe.utils import getdate
        d = getdate(str(value))
        return d
    except Exception:
        return None


def is_stamp_duty_exempt(gross_monthly_salary):
    """Return True if the contract is exempt from stamp duty.

    Exemption: gross monthly salary at time of signing <= RM3,000/month.
    Effective from 1 January 2026 per Finance Bill 2025 (raised from RM300).

    Args:
        gross_monthly_salary (float): Gross monthly salary at time of signing.

    Returns:
        bool
    """
    return float(gross_monthly_salary or 0) <= EXEMPTION_THRESHOLD


def calculate_late_penalty(days_overdue):
    """Calculate late stamping penalty per LHDN schedule.

    Note: 2026 is a grace year — penalties not imposed for late stamping
    submitted 1 January – 31 December 2026.

    Args:
        days_overdue (int): Days overdue beyond the STAMPING_WINDOW_DAYS window.

    Returns:
        float: Penalty amount in MYR.
    """
    if days_overdue <= 0:
        return 0.0
    if _PENALTY_BRACKET_1[0] <= days_overdue <= _PENALTY_BRACKET_1[1]:
        return max(_PENALTY_BRACKET_1_FIXED, STAMP_DUTY_AMOUNT * _PENALTY_BRACKET_1_PCT)
    if days_overdue >= _PENALTY_BRACKET_2_START:
        return max(_PENALTY_BRACKET_2_FIXED, STAMP_DUTY_AMOUNT * _PENALTY_BRACKET_2_PCT)
    return 0.0


def _compliance_status(days_overdue, stamp_exempt, stamped):
    """Return a human-readable compliance status string."""
    if stamp_exempt:
        return "Exempt"
    if stamped:
        return "Stamped"
    if days_overdue > 0:
        return f"Overdue ({days_overdue} days)"
    return "Pending"


def get_pending_stamp_records(company=None, as_of_date=None):
    """Return list of employment contracts pending or overdue for stamping.

    Queries the 'LHDN Contract Stamp Duty' DocType. Returns all records
    that are not exempt and do not have an e-Duti Setem reference.

    Args:
        company (str, optional): Filter by company.
        as_of_date (date | str, optional): Evaluate compliance as of this date.

    Returns:
        list[dict]: Each dict has:
            name, employee, employee_name, company, department,
            contract_signing_date, gross_monthly_salary, stamp_duty_exempt,
            eduti_stamp_reference, contract_stamping_date,
            stamping_deadline, days_overdue, compliance_status.
    """
    as_of = _parse_date(as_of_date) or date.today()

    filters = {}
    if company:
        filters["company"] = company

    records = frappe.get_all(
        "LHDN Contract Stamp Duty",
        filters=filters,
        fields=[
            "name",
            "employee",
            "employee_name",
            "company",
            "contract_signing_date",
            "gross_monthly_salary",
            "stamp_duty_exempt",
            "eduti_stamp_reference",
            "contract_stamping_date",
        ],
    )

    results = []
    for rec in records:
        contract_date = _parse_date(rec.get("contract_signing_date"))
        if not contract_date:
            continue

        stamp_exempt = bool(rec.get("stamp_duty_exempt"))
        stamped = bool(rec.get("eduti_stamp_reference") or rec.get("contract_stamping_date"))
        stamping_deadline = contract_date + timedelta(days=STAMPING_WINDOW_DAYS)

        if stamp_exempt or stamped:
            days_overdue = 0
        else:
            elapsed = (as_of - contract_date).days
            days_overdue = max(0, elapsed - STAMPING_WINDOW_DAYS)

        results.append(
            {
                "name": rec["name"],
                "employee": rec["employee"],
                "employee_name": rec.get("employee_name") or rec["employee"],
                "company": rec["company"],
                "department": "",
                "contract_signing_date": str(contract_date),
                "gross_monthly_salary": rec.get("gross_monthly_salary") or 0,
                "stamp_duty_exempt": int(stamp_exempt),
                "eduti_stamp_reference": rec.get("eduti_stamp_reference") or "",
                "contract_stamping_date": str(rec.get("contract_stamping_date") or ""),
                "stamping_deadline": str(stamping_deadline),
                "days_overdue": days_overdue,
                "compliance_status": _compliance_status(days_overdue, stamp_exempt, stamped),
            }
        )

    results.sort(key=lambda r: r["days_overdue"], reverse=True)
    return results


def send_stamp_duty_alerts(company=None):
    """Send compliance alert to HR Manager for contracts overdue for stamping.

    Iterates all pending stamp records and sends an email for each overdue
    contract to users with the HR Manager role.

    Args:
        company (str, optional): Restrict to this company.
    """
    pending = get_pending_stamp_records(company=company)
    overdue = [r for r in pending if r["days_overdue"] > 0]
    if not overdue:
        return

    # Find HR Manager email addresses
    hr_users = frappe.get_all(
        "Has Role",
        filters={"role": "HR Manager", "parenttype": "User"},
        fields=["parent as email", "parent as full_name"],
    )
    if not hr_users:
        return

    for entry in overdue:
        subject = (
            f"[Stamp Duty Alert] Contract for {entry['employee_name']} overdue "
            f"by {entry['days_overdue']} days"
        )
        message = (
            f"<p>Employee <strong>{entry['employee_name']}</strong> ({entry['employee']})"
            f" has an employment contract signed on {entry['contract_signing_date']} "
            f"that has <strong>not been stamped</strong> via e-Duti Setem (MyTax).</p>"
            f"<p>Stamping deadline was: <strong>{entry['stamping_deadline']}</strong></p>"
            f"<p>Days overdue: <strong>{entry['days_overdue']}</strong></p>"
            f"<p>Gross salary at signing: RM {entry['gross_monthly_salary']:,.2f}/month</p>"
            f"<p>Stamp duty payable: RM {STAMP_DUTY_AMOUNT:.2f} (fixed, Item 4, "
            f"First Schedule, Stamp Act 1949)</p>"
            f"<p>Please stamp the contract immediately via "
            f"<a href='https://mytax.hasil.gov.my'>mytax.hasil.gov.my</a> "
            f"(e-Duti Setem portal) and update the LHDN Contract Stamp Duty record.</p>"
        )
        frappe.sendmail(
            recipients=[u["email"] for u in hr_users],
            subject=subject,
            message=message,
            delayed=False,
        )

    frappe.logger().info(
        f"[stamp_duty_service] Sent stamping alerts for {len(overdue)} overdue contracts."
    )
