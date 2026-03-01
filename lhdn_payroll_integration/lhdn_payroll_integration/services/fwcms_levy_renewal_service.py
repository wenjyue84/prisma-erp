"""FWCMS Foreign Worker Annual Levy Renewal Tracking Service (US-207).

Tracks per-employee annual levy renewal expiry dates via the FWCMS portal,
sends multi-tier advance alerts (90/60/30/14 days), and provides a dashboard
widget showing non-compliant workers.

Key rules:
- Foreign worker levies are paid annually via FWCMS (https://www.fwcms.gov.my)
- Expiry is per individual worker, tied to PLKS/permit period
- Sector-based rates: Manufacturing/Construction/Services = RM1,850/year;
  Plantation/Agriculture = RM640/year
- Employer pays levy — cannot deduct from employee salary
- Multi-tier levy increase of RM300-500 under deliberation — rates configurable
"""

import frappe
from frappe.utils import getdate, today, date_diff, add_days


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: FWCMS levy sectors and their annual rates (MYR)
SECTOR_RATES = {
    "Manufacturing": 1850,
    "Construction": 1850,
    "Services": 1850,
    "Plantation": 640,
    "Agriculture": 640,
}

#: Valid sector values
VALID_SECTORS = list(SECTOR_RATES.keys())

#: Alert tier thresholds (days before expiry)
ALERT_TIERS = [90, 60, 30]

#: Critical escalation threshold (days before expiry, requires receipt)
CRITICAL_ALERT_DAYS = 14

#: Default PLKS renewal duration in days (365 = 1 year)
DEFAULT_RENEWAL_DAYS = 365


# ---------------------------------------------------------------------------
# Sector rate helpers
# ---------------------------------------------------------------------------

def get_sector_rate(sector):
    """Return annual levy rate (MYR) for the given sector.

    Args:
        sector (str): One of the VALID_SECTORS values.

    Returns:
        int: Annual levy rate in MYR.

    Raises:
        ValueError: If sector is not recognised.
    """
    if not sector or sector not in SECTOR_RATES:
        raise ValueError(
            f"Invalid sector '{sector}'. Must be one of: {', '.join(VALID_SECTORS)}"
        )
    return SECTOR_RATES[sector]


def get_all_sector_rates():
    """Return the full sector → rate mapping (copy).

    Returns:
        dict: {sector_name: annual_rate_myr}
    """
    return dict(SECTOR_RATES)


# ---------------------------------------------------------------------------
# Expiry & days-remaining helpers
# ---------------------------------------------------------------------------

def get_days_until_expiry(expiry_date, reference_date=None):
    """Return number of days until levy expiry.

    Args:
        expiry_date (str | date): The FWCMS levy expiry date.
        reference_date (str | date | None): Reference date (defaults to today).

    Returns:
        int: Days remaining (negative = already expired).
    """
    if not expiry_date:
        return None
    ref = getdate(reference_date) if reference_date else getdate(today())
    return date_diff(getdate(expiry_date), ref)


def is_levy_expired(expiry_date, reference_date=None):
    """Return True if the levy expiry date is in the past.

    Args:
        expiry_date (str | date): The FWCMS levy expiry date.
        reference_date (str | date | None): Reference date (defaults to today).

    Returns:
        bool: True if expired.
    """
    days = get_days_until_expiry(expiry_date, reference_date)
    if days is None:
        return False
    return days < 0


# ---------------------------------------------------------------------------
# Alert classification
# ---------------------------------------------------------------------------

def classify_alert_tier(expiry_date, reference_date=None):
    """Classify a worker's levy expiry into an alert tier.

    Args:
        expiry_date (str | date): The FWCMS levy expiry date.
        reference_date (str | date | None): Reference date (defaults to today).

    Returns:
        str | None: One of 'expired', 'critical_14', 'alert_30', 'alert_60',
                     'alert_90', or None (no alert needed).
    """
    days = get_days_until_expiry(expiry_date, reference_date)
    if days is None:
        return None
    if days < 0:
        return "expired"
    if days <= CRITICAL_ALERT_DAYS:
        return "critical_14"
    if days <= 30:
        return "alert_30"
    if days <= 60:
        return "alert_60"
    if days <= 90:
        return "alert_90"
    return None


def needs_critical_escalation(expiry_date, has_renewal_receipt, reference_date=None):
    """Return True if worker needs critical escalation (≤14 days, no receipt).

    Args:
        expiry_date (str | date): The FWCMS levy expiry date.
        has_renewal_receipt (bool): Whether a renewal receipt has been recorded.
        reference_date (str | date | None): Reference date (defaults to today).

    Returns:
        bool: True if critical escalation is needed.
    """
    days = get_days_until_expiry(expiry_date, reference_date)
    if days is None:
        return False
    return days <= CRITICAL_ALERT_DAYS and not has_renewal_receipt


# ---------------------------------------------------------------------------
# Renewal recording
# ---------------------------------------------------------------------------

def validate_renewal_record(payment_date, receipt_reference, sector):
    """Validate renewal record fields.

    Args:
        payment_date (str | date): Date of levy payment.
        receipt_reference (str): FWCMS receipt reference number.
        sector (str): Levy sector.

    Returns:
        list[str]: List of validation error messages (empty = valid).
    """
    errors = []
    if not payment_date:
        errors.append("Payment date is required")
    if not receipt_reference or not str(receipt_reference).strip():
        errors.append("Receipt reference is required")
    if not sector or sector not in SECTOR_RATES:
        errors.append(
            f"Invalid sector. Must be one of: {', '.join(VALID_SECTORS)}"
        )
    return errors


def calculate_next_expiry(payment_date, plks_duration_days=None):
    """Calculate the next levy expiry date from payment date.

    Args:
        payment_date (str | date): Date of levy payment.
        plks_duration_days (int | None): PLKS permit duration in days.
            Defaults to DEFAULT_RENEWAL_DAYS (365).

    Returns:
        date: Next expiry date.
    """
    duration = plks_duration_days or DEFAULT_RENEWAL_DAYS
    return getdate(add_days(getdate(payment_date), duration))


def record_levy_renewal(employee_id, payment_date, receipt_reference, sector,
                        plks_duration_days=None):
    """Record a levy renewal for a foreign worker.

    Validates inputs, updates the Employee record with new payment/expiry dates,
    receipt reference, and sector.

    Args:
        employee_id (str): Employee ID.
        payment_date (str | date): Date of levy payment.
        receipt_reference (str): FWCMS receipt reference number.
        sector (str): Levy sector.
        plks_duration_days (int | None): PLKS permit duration in days.

    Returns:
        dict: {employee, payment_date, expiry_date, receipt_reference, sector, rate}

    Raises:
        frappe.ValidationError: If validation fails.
    """
    errors = validate_renewal_record(payment_date, receipt_reference, sector)
    if errors:
        frappe.throw("; ".join(errors), frappe.ValidationError)

    next_expiry = calculate_next_expiry(payment_date, plks_duration_days)
    rate = get_sector_rate(sector)

    frappe.db.set_value("Employee", employee_id, {
        "custom_fwcms_levy_payment_date": getdate(payment_date),
        "custom_fwcms_levy_expiry_date": next_expiry,
        "custom_fwcms_receipt_reference": str(receipt_reference).strip(),
        "custom_fwcms_levy_sector": sector,
    })

    return {
        "employee": employee_id,
        "payment_date": getdate(payment_date),
        "expiry_date": next_expiry,
        "receipt_reference": str(receipt_reference).strip(),
        "sector": sector,
        "rate": rate,
    }


# ---------------------------------------------------------------------------
# Dashboard widget data
# ---------------------------------------------------------------------------

def get_noncompliant_workers_summary(company=None, reference_date=None):
    """Return dashboard widget data: workers grouped by expiry urgency.

    Args:
        company (str | None): Filter by company (optional).
        reference_date (str | date | None): Reference date (defaults to today).

    Returns:
        dict: {
            'expired': [employee_dicts],
            'expiring_30': [employee_dicts],
            'expiring_60': [employee_dicts],
            'counts': {'expired': N, 'expiring_30': N, 'expiring_60': N}
        }
    """
    ref = getdate(reference_date) if reference_date else getdate(today())

    filters = {
        "custom_is_foreign_worker": 1,
        "status": "Active",
        "custom_fwcms_levy_expiry_date": ["is", "set"],
    }
    if company:
        filters["company"] = company

    workers = frappe.db.get_all(
        "Employee",
        filters=filters,
        fields=[
            "name as employee",
            "employee_name",
            "company",
            "custom_fwcms_levy_expiry_date as expiry_date",
            "custom_fwcms_levy_sector as sector",
            "custom_fwcms_receipt_reference as receipt_reference",
        ],
    )

    expired = []
    expiring_30 = []
    expiring_60 = []

    for w in workers:
        days = date_diff(getdate(w["expiry_date"]), ref)
        w["days_remaining"] = days
        if days < 0:
            expired.append(w)
        elif days <= 30:
            expiring_30.append(w)
        elif days <= 60:
            expiring_60.append(w)

    # Sort each bucket by urgency (fewest days first)
    expired.sort(key=lambda x: x["days_remaining"])
    expiring_30.sort(key=lambda x: x["days_remaining"])
    expiring_60.sort(key=lambda x: x["days_remaining"])

    return {
        "expired": expired,
        "expiring_30": expiring_30,
        "expiring_60": expiring_60,
        "counts": {
            "expired": len(expired),
            "expiring_30": len(expiring_30),
            "expiring_60": len(expiring_60),
        },
    }


# ---------------------------------------------------------------------------
# Alert generation (scheduler task)
# ---------------------------------------------------------------------------

def get_workers_needing_alerts(company=None, reference_date=None):
    """Return foreign workers needing levy renewal alerts.

    Args:
        company (str | None): Filter by company.
        reference_date (str | date | None): Reference date (defaults to today).

    Returns:
        list[dict]: Workers with alert tier classification.
    """
    ref = getdate(reference_date) if reference_date else getdate(today())

    filters = {
        "custom_is_foreign_worker": 1,
        "status": "Active",
        "custom_fwcms_levy_expiry_date": ["is", "set"],
    }
    if company:
        filters["company"] = company

    workers = frappe.db.get_all(
        "Employee",
        filters=filters,
        fields=[
            "name as employee",
            "employee_name",
            "company",
            "custom_fwcms_levy_expiry_date as expiry_date",
            "custom_fwcms_levy_sector as sector",
            "custom_fwcms_receipt_reference as receipt_reference",
        ],
    )

    results = []
    for w in workers:
        tier = classify_alert_tier(w["expiry_date"], ref)
        if tier:
            w["alert_tier"] = tier
            w["days_remaining"] = date_diff(getdate(w["expiry_date"]), ref)
            has_receipt = bool(w.get("receipt_reference"))
            w["needs_critical_escalation"] = (
                tier == "critical_14" and not has_receipt
            )
            results.append(w)

    results.sort(key=lambda x: x["days_remaining"])
    return results
