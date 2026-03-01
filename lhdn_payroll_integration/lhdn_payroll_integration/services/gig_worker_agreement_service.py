"""Gig Workers Act 2025 — Service Agreement Compliance Tracker (US-180).

Implements the mandatory service agreement compliance tracking for platform
providers under the Gig Workers Act 2025 (Act 872).

Key rules:
- Platform providers must sign written service agreements with each gig worker
  containing 7 specific mandatory terms per the Act.
- Payment processing must be linked to a validated service agreement record.
- Expired agreements block new payment cycles.
- Service agreement records must be retained for minimum 7 years for MOHR inspection.
- 30-day advance alert before any service agreement expiry.

Mandatory Service Agreement Terms (Section 30 of Act 872):
  1. Parties to the agreement (platform provider and gig worker identities)
  2. Period of the agreement (start date, end date or indefinite)
  3. Description of services to be provided
  4. Obligations of both parties
  5. Rate of earnings (per task, per hour, per day, etc.)
  6. Payment method and frequency
  7. Entitled benefits (SOCSO/SEIA coverage, insurance, etc.)
"""

import frappe
from frappe.utils import getdate, nowdate, add_days, date_diff


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Employment type string used for gig/platform workers
GIG_WORKER_EMPLOYMENT_TYPE = "Gig / Platform Worker"

#: Minimum retention period in years for MOHR inspection
MOHR_RETENTION_YEARS = 7

#: Days before expiry to raise renewal alert
EXPIRY_ALERT_DAYS = 30

#: Maximum suspension days before inquiry (Act 872 S.35)
MAX_SUSPENSION_DAYS = 14

#: Complaint window for grievance mechanism (days)
GRIEVANCE_COMPLAINT_WINDOW_DAYS = 30

#: The 7 mandatory terms required by Act 872 Section 30
MANDATORY_AGREEMENT_TERMS = [
    "parties",
    "period",
    "services_description",
    "obligations",
    "earnings_rate",
    "payment_method",
    "entitled_benefits",
]

#: Agreement status values
STATUS_VALID = "Valid"
STATUS_EXPIRED = "Expired"
STATUS_MISSING = "Missing"
STATUS_PENDING_RENEWAL = "Pending Renewal"


# ---------------------------------------------------------------------------
# Agreement validation
# ---------------------------------------------------------------------------

def validate_agreement_terms(agreement: dict) -> dict:
    """Validate that a service agreement contains all 7 mandatory terms.

    Args:
        agreement: Dict representing the agreement with keys matching
            ``MANDATORY_AGREEMENT_TERMS``.

    Returns:
        dict with keys:
            ``valid``   — True if all 7 mandatory terms are present and non-empty
            ``missing`` — list of missing/empty term keys
            ``present`` — list of present term keys
    """
    missing = []
    present = []

    for term in MANDATORY_AGREEMENT_TERMS:
        value = agreement.get(term)
        if value and str(value).strip():
            present.append(term)
        else:
            missing.append(term)

    return {
        "valid": len(missing) == 0,
        "missing": missing,
        "present": present,
    }


def get_agreement_status(agreement: dict, as_of_date=None) -> str:
    """Determine the current status of a service agreement.

    Args:
        agreement: Dict with at least ``end_date`` and ``start_date`` keys.
        as_of_date: Date to check against; defaults to today.

    Returns:
        One of: STATUS_VALID, STATUS_EXPIRED, STATUS_PENDING_RENEWAL
    """
    check_date = getdate(as_of_date or nowdate())

    start_date = agreement.get("start_date")
    end_date = agreement.get("end_date")

    # No end date means indefinite agreement — always valid if started
    if not end_date:
        if start_date and getdate(start_date) > check_date:
            return STATUS_PENDING_RENEWAL
        return STATUS_VALID

    end_dt = getdate(end_date)

    if check_date > end_dt:
        return STATUS_EXPIRED

    # Within expiry alert window
    days_remaining = date_diff(end_dt, check_date)
    if days_remaining <= EXPIRY_ALERT_DAYS:
        return STATUS_PENDING_RENEWAL

    return STATUS_VALID


# ---------------------------------------------------------------------------
# Payment eligibility
# ---------------------------------------------------------------------------

def check_payment_eligibility(employee_name: str, as_of_date=None) -> dict:
    """Check if a gig worker is eligible for payment processing.

    Payment is blocked if:
    - No service agreement exists for the worker
    - The service agreement is expired
    - The service agreement is missing mandatory terms

    Args:
        employee_name: Employee DocType name/ID.
        as_of_date: Date for status check; defaults to today.

    Returns:
        dict with keys:
            ``eligible``  — True if payment can proceed
            ``reason``    — Human-readable reason if blocked
            ``status``    — Agreement status string
            ``agreement`` — Agreement name if found, else None
    """
    check_date = getdate(as_of_date or nowdate())

    # Look for the most recent service agreement for this employee
    agreement = _get_active_agreement(employee_name, check_date)

    if not agreement:
        return {
            "eligible": False,
            "reason": "No service agreement found for this gig worker",
            "status": STATUS_MISSING,
            "agreement": None,
        }

    status = get_agreement_status(agreement, check_date)

    if status == STATUS_EXPIRED:
        return {
            "eligible": False,
            "reason": f"Service agreement {agreement.get('name', '')} has expired",
            "status": STATUS_EXPIRED,
            "agreement": agreement.get("name"),
        }

    # Validate mandatory terms
    validation = validate_agreement_terms(agreement)
    if not validation["valid"]:
        missing_str = ", ".join(validation["missing"])
        return {
            "eligible": False,
            "reason": f"Service agreement missing mandatory terms: {missing_str}",
            "status": status,
            "agreement": agreement.get("name"),
        }

    return {
        "eligible": True,
        "reason": "",
        "status": status,
        "agreement": agreement.get("name"),
    }


def _get_active_agreement(employee_name: str, as_of_date=None) -> dict | None:
    """Fetch the most recent service agreement for the employee.

    Looks for a Gig Worker Service Agreement DocType linked to the employee.
    Falls back to None if DocType doesn't exist or no record found.

    Args:
        employee_name: Employee name/ID.
        as_of_date: Reference date for filtering.

    Returns:
        dict with agreement fields, or None.
    """
    check_date = getdate(as_of_date or nowdate())

    try:
        if not frappe.db.exists("DocType", "Gig Worker Service Agreement"):
            return None
    except Exception:
        return None

    try:
        agreements = frappe.get_all(
            "Gig Worker Service Agreement",
            filters={
                "employee": employee_name,
                "start_date": ["<=", str(check_date)],
                "docstatus": ["<", 2],  # Not cancelled
            },
            fields=[
                "name", "employee", "start_date", "end_date",
                "parties", "period", "services_description", "obligations",
                "earnings_rate", "payment_method", "entitled_benefits",
            ],
            order_by="start_date desc",
            limit_page_length=1,
        )
    except Exception:
        return None

    return agreements[0] if agreements else None


# ---------------------------------------------------------------------------
# Expiry alerts
# ---------------------------------------------------------------------------

def get_expiring_agreements(company=None, days_ahead=None) -> list:
    """Get service agreements expiring within the alert window.

    Args:
        company: Optional company filter.
        days_ahead: Days to look ahead; defaults to EXPIRY_ALERT_DAYS (30).

    Returns:
        List of dicts with agreement details and days_remaining.
    """
    days = days_ahead if days_ahead is not None else EXPIRY_ALERT_DAYS
    today = getdate(nowdate())
    cutoff = add_days(today, days)

    try:
        if not frappe.db.exists("DocType", "Gig Worker Service Agreement"):
            return []
    except Exception:
        return []

    filters = {
        "end_date": ["between", [str(today), str(cutoff)]],
        "docstatus": ["<", 2],
    }

    if company:
        filters["company"] = company

    try:
        agreements = frappe.get_all(
            "Gig Worker Service Agreement",
            filters=filters,
            fields=["name", "employee", "employee_name", "start_date", "end_date", "company"],
            order_by="end_date asc",
        )
    except Exception:
        return []

    results = []
    for agr in agreements:
        days_remaining = date_diff(getdate(agr["end_date"]), today)
        results.append({
            "agreement": agr["name"],
            "employee": agr["employee"],
            "employee_name": agr.get("employee_name", ""),
            "end_date": str(agr["end_date"]),
            "days_remaining": days_remaining,
            "company": agr.get("company", ""),
        })

    return results


# ---------------------------------------------------------------------------
# Compliance report
# ---------------------------------------------------------------------------

def generate_compliance_report(company=None, as_of_date=None) -> dict:
    """Generate a compliance report for all active gig workers.

    Lists every active gig worker and their service agreement status:
    Valid, Expired, Missing, or Pending Renewal.

    Args:
        company: Optional company filter.
        as_of_date: Reference date; defaults to today.

    Returns:
        dict with keys:
            ``total_workers``  — count of active gig workers
            ``valid``          — count with valid agreements
            ``expired``        — count with expired agreements
            ``missing``        — count with no agreement
            ``pending_renewal``— count within renewal window
            ``workers``        — list of per-worker detail dicts
    """
    check_date = getdate(as_of_date or nowdate())

    workers = _get_active_gig_workers(company)

    report = {
        "total_workers": len(workers),
        "valid": 0,
        "expired": 0,
        "missing": 0,
        "pending_renewal": 0,
        "workers": [],
    }

    for worker in workers:
        emp_name = worker.get("name") or worker.get("employee")
        result = check_payment_eligibility(emp_name, check_date)

        status = result["status"]
        if status == STATUS_VALID:
            report["valid"] += 1
        elif status == STATUS_EXPIRED:
            report["expired"] += 1
        elif status == STATUS_MISSING:
            report["missing"] += 1
        elif status == STATUS_PENDING_RENEWAL:
            report["pending_renewal"] += 1

        report["workers"].append({
            "employee": emp_name,
            "employee_name": worker.get("employee_name", ""),
            "status": status,
            "eligible_for_payment": result["eligible"],
            "agreement": result["agreement"],
            "reason": result["reason"],
        })

    return report


def _get_active_gig_workers(company=None) -> list:
    """Fetch all active gig/platform workers.

    Args:
        company: Optional company filter.

    Returns:
        List of dicts with employee info.
    """
    filters = {
        "custom_employment_type": GIG_WORKER_EMPLOYMENT_TYPE,
        "status": "Active",
    }
    if company:
        filters["company"] = company

    try:
        return frappe.get_all(
            "Employee",
            filters=filters,
            fields=["name", "employee_name", "company"],
        )
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Retention compliance
# ---------------------------------------------------------------------------

def check_retention_compliance(agreement_name: str) -> dict:
    """Check whether a service agreement meets the 7-year MOHR retention requirement.

    Args:
        agreement_name: Name of the Gig Worker Service Agreement document.

    Returns:
        dict with keys:
            ``compliant``       — True if retention period is met or still active
            ``retention_years`` — Required retention period (7)
            ``end_date``        — Agreement end date
            ``retention_until`` — Date until which the record must be retained
            ``can_archive``     — True if the record has passed the retention window
    """
    try:
        if not frappe.db.exists("DocType", "Gig Worker Service Agreement"):
            return {
                "compliant": False,
                "retention_years": MOHR_RETENTION_YEARS,
                "end_date": None,
                "retention_until": None,
                "can_archive": False,
                "reason": "Gig Worker Service Agreement DocType not found",
            }

        agreement = frappe.get_doc("Gig Worker Service Agreement", agreement_name)
    except Exception:
        return {
            "compliant": False,
            "retention_years": MOHR_RETENTION_YEARS,
            "end_date": None,
            "retention_until": None,
            "can_archive": False,
            "reason": f"Agreement {agreement_name} not found",
        }

    end_date = agreement.get("end_date")
    if not end_date:
        # Indefinite agreement — still active, retention is automatically met
        return {
            "compliant": True,
            "retention_years": MOHR_RETENTION_YEARS,
            "end_date": None,
            "retention_until": None,
            "can_archive": False,
            "reason": "Indefinite agreement — still active",
        }

    end_dt = getdate(end_date)
    retention_until = add_days(end_dt, MOHR_RETENTION_YEARS * 365)
    today = getdate(nowdate())
    can_archive = today > retention_until

    return {
        "compliant": True,
        "retention_years": MOHR_RETENTION_YEARS,
        "end_date": str(end_dt),
        "retention_until": str(retention_until),
        "can_archive": can_archive,
        "reason": "",
    }


# ---------------------------------------------------------------------------
# Grievance mechanism compliance
# ---------------------------------------------------------------------------

def check_grievance_window(complaint_date, as_of_date=None) -> dict:
    """Check if a gig worker complaint is within the 30-day grievance window.

    Per Act 872, contracting entities must establish internal grievance
    mechanisms with a 30-day window for worker complaints.

    Args:
        complaint_date: Date the complaint was filed.
        as_of_date: Current date for comparison; defaults to today.

    Returns:
        dict with keys:
            ``within_window``   — True if complaint is within 30 days
            ``days_elapsed``    — Days since complaint was filed
            ``days_remaining``  — Days remaining in the window (0 if expired)
            ``deadline``        — Last day of the complaint window
    """
    check_date = getdate(as_of_date or nowdate())
    complaint_dt = getdate(complaint_date)

    deadline = add_days(complaint_dt, GRIEVANCE_COMPLAINT_WINDOW_DAYS)
    days_elapsed = date_diff(check_date, complaint_dt)
    days_remaining = max(0, date_diff(deadline, check_date))

    return {
        "within_window": check_date <= deadline,
        "days_elapsed": days_elapsed,
        "days_remaining": days_remaining,
        "deadline": str(deadline),
    }


def check_suspension_compliance(suspension_start_date, inquiry_date=None, as_of_date=None) -> dict:
    """Check if a gig worker suspension complies with the 14-day maximum.

    Per Act 872, platform deactivation of gig workers requires adequate
    notice and hearing; maximum 14-day suspension before inquiry.

    Args:
        suspension_start_date: Date the suspension began.
        inquiry_date: Date the inquiry was conducted (None if not yet held).
        as_of_date: Current date; defaults to today.

    Returns:
        dict with keys:
            ``compliant``           — True if suspension is within 14 days or inquiry held
            ``suspension_days``     — Days of suspension so far
            ``max_days``            — Maximum allowed suspension (14)
            ``inquiry_required_by`` — Deadline for conducting inquiry
            ``inquiry_held``        — True if inquiry_date is provided
    """
    check_date = getdate(as_of_date or nowdate())
    start_dt = getdate(suspension_start_date)

    inquiry_deadline = add_days(start_dt, MAX_SUSPENSION_DAYS)
    suspension_days = date_diff(check_date, start_dt)

    inquiry_held = inquiry_date is not None
    if inquiry_held:
        inquiry_dt = getdate(inquiry_date)
        compliant = date_diff(inquiry_dt, start_dt) <= MAX_SUSPENSION_DAYS
    else:
        compliant = suspension_days <= MAX_SUSPENSION_DAYS

    return {
        "compliant": compliant,
        "suspension_days": suspension_days,
        "max_days": MAX_SUSPENSION_DAYS,
        "inquiry_required_by": str(inquiry_deadline),
        "inquiry_held": inquiry_held,
    }
