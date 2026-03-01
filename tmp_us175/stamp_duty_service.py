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
import frappe
from frappe.utils import getdate, add_days, today, date_diff, nowdate

# Statutory constants
STAMP_DUTY_AMOUNT = 10.0          # RM10 fixed per contract
EXEMPTION_THRESHOLD = 3000.0      # RM3,000/month from 2026 Finance Bill
STAMPING_DEADLINE_DAYS = 30       # Must stamp within 30 days of signing
SAS_EFFECTIVE_DATE = "2026-01-01" # e-Duti Setem SAS mandatory from 1 Jan 2026

# Late penalty brackets (post-2026 grace year)
PENALTY_BRACKET_1 = (31, 90)      # 31-90 days late
PENALTY_BRACKET_1_FIXED = 50.0    # RM50 fixed
PENALTY_BRACKET_1_PCT = 0.10      # 10% of duty
PENALTY_BRACKET_2 = 91            # >90 days late
PENALTY_BRACKET_2_FIXED = 100.0   # RM100 fixed
PENALTY_BRACKET_2_PCT = 0.20      # 20% of duty


def is_stamp_duty_exempt(gross_monthly_salary):
    """Return True if the contract is exempt from stamp duty.

    Exemption: gross monthly salary at time of signing <= RM3,000/month.
    Effective from 1 January 2026 per Finance Bill 2025 (raised from RM300).

    Args:
        gross_monthly_salary (float): Gross monthly salary at time of contract signing.

    Returns:
        bool: True if exempt, False if stamp duty applies.
    """
    return float(gross_monthly_salary or 0) <= EXEMPTION_THRESHOLD


def get_days_since_signing(contract_date):
    """Return days elapsed since the contract signing date.

    Args:
        contract_date: Date string or date object for contract signing.

    Returns:
        int: Number of days since signing. 0 if contract_date is None or future.
    """
    if not contract_date:
        return 0
    delta = date_diff(today(), getdate(contract_date))
    return max(0, delta)


def is_stamping_overdue(contract_date, stamping_date=None, stamp_reference=None):
    """Return True if the contract requires stamping and the 30-day window has passed.

    A contract is overdue if:
    - It has a signing date
    - No stamping reference number has been provided
    - No stamping date has been set
    - More than 30 days have elapsed since signing

    Args:
        contract_date: Date of contract signing.
        stamping_date: Date when the contract was stamped (if any).
        stamp_reference: e-Duti Setem reference number (if any).

    Returns:
        bool: True if overdue.
    """
    if not contract_date:
        return False
    # Already stamped
    if stamp_reference or stamping_date:
        return False
    days = get_days_since_signing(contract_date)
    return days > STAMPING_DEADLINE_DAYS


def calculate_late_penalty(days_late):
    """Calculate late stamping penalty per LHDN schedule.

    Note: 2026 is a grace year — penalties not imposed for late stamping
    submitted 1 January – 31 December 2026.

    Args:
        days_late (int): Number of days late beyond the 30-day window.

    Returns:
        float: Penalty amount in MYR (0 if within grace period or within deadline).
    """
    if days_late <= 0:
        return 0.0
    if PENALTY_BRACKET_1[0] <= days_late <= PENALTY_BRACKET_1[1]:
        return max(PENALTY_BRACKET_1_FIXED, STAMP_DUTY_AMOUNT * PENALTY_BRACKET_1_PCT)
    if days_late > PENALTY_BRACKET_1[1]:
        return max(PENALTY_BRACKET_2_FIXED, STAMP_DUTY_AMOUNT * PENALTY_BRACKET_2_PCT)
    return 0.0


def get_contracts_pending_stamping(company=None, as_of_date=None):
    """Return list of employment contracts pending stamping.

    Queries 'LHDN Employment Contract Stamp Duty' DocType.
    Includes contracts that:
    - Are not stamp duty exempt
    - Have no e-Duti Setem reference number
    - Contract signing date is on or after SAS effective date (2026-01-01)

    Args:
        company (str, optional): Filter by company.
        as_of_date (str, optional): Check status as of this date (defaults to today).

    Returns:
        list[dict]: Each dict has employee, employee_name, contract_date,
                    gross_salary, days_elapsed, is_overdue, days_overdue, penalty_est.
    """
    as_of = getdate(as_of_date) if as_of_date else getdate(today())
    filters = {
        "stamp_duty_exempt": 0,
        "eduti_setem_reference": ["in", ["", None]],
        "contract_signing_date": ["is", "set"],
    }
    if company:
        filters["company"] = company

    records = frappe.get_all(
        "LHDN Employment Contract Stamp Duty",
        filters=filters,
        fields=[
            "name",
            "employee",
            "employee_name",
            "company",
            "contract_signing_date",
            "gross_salary_at_signing",
            "stamp_duty_exempt",
            "eduti_setem_reference",
            "contract_stamping_date",
        ],
    )

    results = []
    for rec in records:
        contract_date = rec.get("contract_signing_date")
        if not contract_date:
            continue
        # Only track contracts signed on/after SAS effective date
        if getdate(contract_date) < getdate(SAS_EFFECTIVE_DATE):
            # Pre-2026 contracts: flagged compliant if stamped before 31 Dec 2025
            stamping_date = rec.get("contract_stamping_date")
            if stamping_date and getdate(stamping_date) <= getdate("2025-12-31"):
                continue  # compliant — stamped in time
        days_elapsed = date_diff(as_of, getdate(contract_date))
        days_overdue = max(0, days_elapsed - STAMPING_DEADLINE_DAYS)
        is_overdue = days_elapsed > STAMPING_DEADLINE_DAYS
        results.append(
            {
                "employee": rec["employee"],
                "employee_name": rec.get("employee_name") or rec["employee"],
                "company": rec["company"],
                "contract_date": contract_date,
                "gross_salary": rec.get("gross_salary_at_signing") or 0,
                "days_elapsed": days_elapsed,
                "is_overdue": is_overdue,
                "days_overdue": days_overdue,
                "penalty_est": calculate_late_penalty(days_overdue),
            }
        )
    results.sort(key=lambda r: r["days_overdue"], reverse=True)
    return results


def send_stamping_alerts(company=None):
    """Send compliance alert to HR Manager for contracts overdue for stamping.

    Alert is sent for each contract that has exceeded the 30-day stamping window
    and has no e-Duti Setem reference.

    Args:
        company (str, optional): Restrict to this company.
    """
    overdue = [r for r in get_contracts_pending_stamping(company=company) if r["is_overdue"]]
    if not overdue:
        return

    # Find HR Manager users to notify
    hr_users = frappe.get_all(
        "Has Role",
        filters={"role": "HR Manager", "parenttype": "User"},
        fields=["parent as user"],
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
            f" has an employment contract signed on {entry['contract_date']} "
            f"that has <strong>not been stamped</strong> via e-Duti Setem (MyTax).</p>"
            f"<p>Days overdue: <strong>{entry['days_overdue']}</strong></p>"
            f"<p>Gross salary at signing: RM {entry['gross_salary']:,.2f}/month</p>"
            f"<p>Stamp duty payable: RM {STAMP_DUTY_AMOUNT:.2f} (fixed, Item 4, First Schedule, Stamp Act 1949)</p>"
            f"<p>Estimated late penalty: RM {entry['penalty_est']:.2f} (waived during 2026 grace year)</p>"
            f"<p>Please stamp the contract immediately via "
            f"<a href='https://mytax.hasil.gov.my'>mytax.hasil.gov.my</a> "
            f"(e-Duti Setem portal) and update the LHDN Employment Contract Stamp Duty record.</p>"
        )
        for hr_user in hr_users:
            frappe.sendmail(
                recipients=[hr_user["user"]],
                subject=subject,
                message=message,
                delayed=False,
            )

    frappe.logger().info(
        f"[stamp_duty_service] Sent stamping alerts for {len(overdue)} overdue contracts."
    )


def set_stamp_duty_exempt_flag(employee_doc):
    """Auto-set stamp duty exemption flag based on gross salary at signing.

    Called from before_save on LHDN Employment Contract Stamp Duty documents,
    or can be called with any object having custom_gross_salary_at_signing.

    Args:
        employee_doc: Object with custom_gross_salary_at_signing attribute.
    """
    salary = employee_doc.get("custom_gross_salary_at_signing") or 0
    employee_doc.custom_stamp_duty_exempt = 1 if is_stamp_duty_exempt(salary) else 0
