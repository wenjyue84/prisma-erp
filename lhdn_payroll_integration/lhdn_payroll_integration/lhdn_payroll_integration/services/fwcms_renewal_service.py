"""FWCMS Foreign Worker Annual Levy Renewal Expiry Tracking Service (US-207).

Tracks FWCMS (Foreign Worker Centralised Management System) annual levy renewal
expiry dates per employee, calculates sector-specific levy rates, and sends
advance expiry alerts to HR.

Ref: FWCMS — https://www.imi.gov.my
"""
import datetime

import frappe

# ---------------------------------------------------------------------------
# Sector levy rate constants
# ---------------------------------------------------------------------------

FWCMS_SECTOR_RATES = {
    "Manufacturing": 1850,
    "Construction": 1850,
    "Services": 1850,
    "Plantation": 640,
    "Agriculture": 640,
}

# Alert thresholds (days before expiry)
ALERT_DAYS = (90, 60, 30)
CRITICAL_ALERT_DAYS = 14


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_levy_rate_for_sector(sector: str) -> int:
    """Return the annual FWCMS levy rate (RM) for the given sector.

    Unknown sectors default to the highest rate (RM1,850) as a conservative assumption.

    Args:
        sector: FWCMS sector name (e.g. 'Manufacturing', 'Plantation').

    Returns:
        int: Annual levy amount in RM.
    """
    if not sector:
        return 1850
    return FWCMS_SECTOR_RATES.get(sector, 1850)


def get_expiry_status(expiry_date, today=None) -> str:
    """Return the expiry status for a levy expiry date.

    Args:
        expiry_date: Date of levy expiry (date object or ISO string).
        today: Reference date (defaults to today).

    Returns:
        str: One of 'expired', 'critical', 'expiring_30', 'expiring_60', 'expiring_90', 'ok'.
    """
    if today is None:
        today = datetime.date.today()
    if isinstance(expiry_date, str):
        expiry_date = datetime.date.fromisoformat(expiry_date[:10])
    if isinstance(today, str):
        today = datetime.date.fromisoformat(today[:10])

    days_left = (expiry_date - today).days

    if days_left < 0:
        return "expired"
    if days_left <= CRITICAL_ALERT_DAYS:
        return "critical"
    if days_left <= 30:
        return "expiring_30"
    if days_left <= 60:
        return "expiring_60"
    if days_left <= 90:
        return "expiring_90"
    return "ok"


def check_fwcms_levy_expiry_alerts(today=None):
    """Daily scheduler task: send alerts for workers with upcoming levy expiry.

    Creates Frappe Notification Log entries for HR Manager / HR User at
    90, 60, 30-day thresholds and a critical alert at 14 days if receipt
    is not recorded.

    Args:
        today: Reference date (defaults to today). Used for testing.
    """
    if today is None:
        today = datetime.date.today()
    if isinstance(today, str):
        today = datetime.date.fromisoformat(today[:10])

    try:
        employees = frappe.db.sql(
            """
            SELECT name, employee_name,
                   custom_fwcms_levy_expiry_date,
                   custom_fw_levy_receipt_ref,
                   custom_fwcms_sector
            FROM `tabEmployee`
            WHERE custom_fwcms_levy_expiry_date IS NOT NULL
              AND status = 'Active'
            """,
            as_dict=True,
        )

        for emp in employees:
            expiry = emp.get("custom_fwcms_levy_expiry_date")
            if not expiry:
                continue

            status = get_expiry_status(expiry, today)
            if status not in ("expired", "critical", "expiring_30", "expiring_60", "expiring_90"):
                continue

            receipt = emp.get("custom_fw_levy_receipt_ref")
            if status == "expired" and not receipt:
                _notify_hr(emp, "FWCMS Levy EXPIRED", f"Levy expired for {emp['employee_name']}.")
            elif status == "critical" and not receipt:
                days_left = (
                    datetime.date.fromisoformat(str(expiry)[:10]) - today
                ).days
                _notify_hr(
                    emp,
                    "FWCMS Levy Critical — No Receipt",
                    f"Levy expires in {days_left} day(s) for {emp['employee_name']} and no receipt recorded.",
                )
            elif status in ("expiring_30", "expiring_60", "expiring_90"):
                days_left = (
                    datetime.date.fromisoformat(str(expiry)[:10]) - today
                ).days
                _notify_hr(
                    emp,
                    "FWCMS Levy Expiry Alert",
                    f"Levy expires in {days_left} day(s) for {emp['employee_name']}.",
                )

        frappe.db.commit()
    except Exception as exc:
        frappe.log_error(f"check_fwcms_levy_expiry_alerts failed: {exc}", "FWCMS Levy Alert")


def _notify_hr(emp: dict, subject: str, message: str):
    """Create a Notification Log for HR users."""
    hr_users = frappe.db.sql_list(
        """
        SELECT DISTINCT u.name
        FROM `tabUser` u
        INNER JOIN `tabHas Role` hr ON hr.parent = u.name
        WHERE hr.role IN ('HR Manager', 'HR User', 'System Manager')
          AND u.enabled = 1
        """
    )
    if not hr_users:
        hr_users = ["Administrator"]

    for user in hr_users:
        frappe.get_doc(
            {
                "doctype": "Notification Log",
                "for_user": user,
                "type": "Alert",
                "document_type": "Employee",
                "document_name": emp.get("name"),
                "subject": subject,
                "email_content": message,
            }
        ).insert(ignore_permissions=True)


def record_fwcms_renewal(employee: str, payment_date, receipt_ref: str, sector: str = None):
    """Record a FWCMS levy renewal for an employee.

    Sets the payment date, auto-calculates expiry (payment + 365 days),
    and records the receipt reference.

    Args:
        employee: Employee document name.
        payment_date: Date of levy payment (date or ISO string).
        receipt_ref: FWCMS receipt reference number.
        sector: FWCMS sector (optional; updates field if provided).

    Raises:
        frappe.ValidationError: If receipt_ref is blank.
    """
    if not receipt_ref or not receipt_ref.strip():
        frappe.throw("Receipt reference is required to record FWCMS renewal.")

    if isinstance(payment_date, str):
        payment_date = datetime.date.fromisoformat(payment_date[:10])

    expiry_date = payment_date + datetime.timedelta(days=365)

    doc = frappe.get_doc("Employee", employee)
    doc.custom_fwcms_levy_payment_date = payment_date
    doc.custom_fwcms_levy_expiry_date = expiry_date
    doc.custom_fw_levy_receipt_ref = receipt_ref.strip()
    if sector:
        doc.custom_fwcms_sector = sector
    doc.save(ignore_permissions=True)
    frappe.db.commit()

    return {
        "employee": employee,
        "payment_date": str(payment_date),
        "expiry_date": str(expiry_date),
        "receipt_ref": receipt_ref.strip(),
    }


def get_expiring_workers_dashboard(today=None) -> dict:
    """Return a dashboard summary of workers by levy expiry status.

    Returns:
        dict with keys: expired, critical, expiring_30, expiring_60
        Each value is a list of dicts with employee details.
    """
    if today is None:
        today = datetime.date.today()
    if isinstance(today, str):
        today = datetime.date.fromisoformat(today[:10])

    result = {
        "expired": [],
        "critical": [],
        "expiring_30": [],
        "expiring_60": [],
    }

    try:
        employees = frappe.db.sql(
            """
            SELECT name, employee_name,
                   custom_fwcms_levy_expiry_date,
                   custom_fw_levy_receipt_ref,
                   custom_fwcms_sector
            FROM `tabEmployee`
            WHERE custom_fwcms_levy_expiry_date IS NOT NULL
              AND status = 'Active'
            """,
            as_dict=True,
        )

        for emp in employees:
            expiry = emp.get("custom_fwcms_levy_expiry_date")
            if not expiry:
                continue
            status = get_expiry_status(expiry, today)
            if status in result:
                result[status].append(
                    {
                        "employee": emp["name"],
                        "employee_name": emp["employee_name"],
                        "expiry_date": str(expiry),
                        "sector": emp.get("custom_fwcms_sector", ""),
                        "receipt_ref": emp.get("custom_fw_levy_receipt_ref", ""),
                    }
                )
    except Exception as exc:
        frappe.log_error(f"get_expiring_workers_dashboard failed: {exc}", "FWCMS Dashboard")

    return result
