"""EP Category Internship Obligation Tracker — US-204.

Tracks internship quota obligations for companies employing foreign nationals
on Employment Passes (EP) per the TalentCorp/MOHR 1:3 Internship Policy.

Policy rules (mandatory from 1 January 2026; pilot extended to 31 March 2026):
  - EP Cat I:   3 intern placements required per EP holder
  - EP Cat II:  2 intern placements required per EP holder
  - EP Cat III: 1 intern placement required per EP holder
  - Total quota capped at 2% of company headcount
  - Minimum internship duration: 10 weeks
  - Minimum stipend: RM 600/month for degree/master/DLKM level
                     RM 500/month for diploma/SKM/certificate level
  - Renewal alert triggered 60 days before EP expiry when quota unfulfilled

Non-compliance does not cancel existing EPs but adversely impacts renewal.
"""
import frappe
from frappe.utils import getdate, nowdate, add_days, date_diff


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Quota multipliers per EP category (TalentCorp/MOHR policy)
QUOTA_PER_EP_CAT = {
    "Cat I": 3,
    "Cat II": 2,
    "Cat III": 1,
}

#: Headcount cap: total internship slots cannot exceed 2% of headcount
HEADCOUNT_CAP_RATE = 0.02

#: Minimum stipend by qualification level (RM/month)
STIPEND_MIN = {
    "Degree": 600.0,
    "Master": 600.0,
    "DLKM": 600.0,
    "Diploma": 500.0,
    "SKM": 500.0,
    "Certificate": 500.0,
}

#: Higher-level qualifications
HIGHER_LEVEL_QUALS = {"Degree", "Master", "DLKM"}

#: Lower-level qualifications
LOWER_LEVEL_QUALS = {"Diploma", "SKM", "Certificate"}

#: Alert window before EP expiry (days)
EP_RENEWAL_ALERT_DAYS = 60

#: Minimum internship duration in weeks
MIN_INTERNSHIP_WEEKS = 10


# ---------------------------------------------------------------------------
# Quota computation
# ---------------------------------------------------------------------------

def compute_internship_quota(company: str) -> dict:
    """Calculate the total internship slots required for *company*.

    Sums quota per active EP holder (Cat I × 3 + Cat II × 2 + Cat III × 1),
    then caps at 2% of total employee headcount.

    Args:
        company: Company name to filter EP holders.

    Returns:
        dict with keys:
            ``raw_required``        — sum before headcount cap
            ``headcount``           — total active employees
            ``headcount_cap``       — 2% of headcount (rounded down, min 1 if any EP)
            ``effective_required``  — min(raw_required, headcount_cap)
            ``ep_breakdown``        — {cat: count} for each EP category
    """
    # Total headcount for headcount cap
    total_employees = frappe.db.count(
        "Employee", {"company": company, "status": "Active"}
    )

    # EP holders per category
    ep_breakdown = {}
    raw_required = 0
    for cat, multiplier in QUOTA_PER_EP_CAT.items():
        count = frappe.db.count(
            "Employee",
            {
                "company": company,
                "status": "Active",
                "custom_ep_category": cat,
            },
        )
        ep_breakdown[cat] = count
        raw_required += count * multiplier

    # Headcount cap (floor to int, minimum 1 if there are any EPs)
    headcount_cap = int(total_employees * HEADCOUNT_CAP_RATE)
    if raw_required > 0 and headcount_cap < 1:
        headcount_cap = 1

    effective_required = min(raw_required, headcount_cap) if headcount_cap > 0 else raw_required

    return {
        "raw_required": raw_required,
        "headcount": total_employees,
        "headcount_cap": headcount_cap,
        "effective_required": effective_required,
        "ep_breakdown": ep_breakdown,
    }


# ---------------------------------------------------------------------------
# Stipend validation
# ---------------------------------------------------------------------------

def validate_intern_stipend(qualification_level: str, monthly_stipend: float) -> dict:
    """Validate that the intern stipend meets the TalentCorp minimum.

    Args:
        qualification_level: One of Degree / Master / DLKM / Diploma / SKM / Certificate.
        monthly_stipend:     Proposed monthly stipend in RM.

    Returns:
        dict with keys:
            ``valid``          — True if stipend >= minimum
            ``min_required``   — minimum RM amount for this level
            ``shortfall``      — 0 if valid, otherwise (min_required - monthly_stipend)
            ``message``        — human-readable result
    """
    min_req = STIPEND_MIN.get(qualification_level)
    if min_req is None:
        return {
            "valid": False,
            "min_required": 0.0,
            "shortfall": 0.0,
            "message": f"Unknown qualification level: {qualification_level}",
        }

    stipend = float(monthly_stipend or 0)
    valid = stipend >= min_req
    shortfall = max(0.0, min_req - stipend)

    return {
        "valid": valid,
        "min_required": min_req,
        "shortfall": round(shortfall, 2),
        "message": (
            f"Stipend RM {stipend:.2f} meets minimum RM {min_req:.2f} for {qualification_level}"
            if valid
            else f"Stipend RM {stipend:.2f} below minimum RM {min_req:.2f} for {qualification_level} (shortfall: RM {shortfall:.2f})"
        ),
    }


# ---------------------------------------------------------------------------
# Compliance summary
# ---------------------------------------------------------------------------

def get_compliance_summary(company: str, year: int) -> dict:
    """Return quota vs fulfilled internship placement summary for *company*.

    Args:
        company: Company name.
        year:    Reporting year (e.g. 2026).

    Returns:
        dict with keys:
            ``quota_required``  — effective internship slots required
            ``fulfilled``       — completed placements in the year
            ``gap``             — max(0, quota_required - fulfilled)
            ``compliant``       — True when gap == 0
            ``ep_breakdown``    — EP category breakdown from compute_internship_quota
    """
    quota_info = compute_internship_quota(company)
    quota_required = quota_info["effective_required"]

    # Count Internship Placement records with status="Completed" for this year/company
    year_start = f"{year}-01-01"
    year_end = f"{year}-12-31"

    fulfilled = frappe.db.count(
        "Internship Placement",
        {
            "company": company,
            "status": "Completed",
            "end_date": ("between", [year_start, year_end]),
        },
    )

    gap = max(0, quota_required - fulfilled)
    return {
        "quota_required": quota_required,
        "fulfilled": fulfilled,
        "gap": gap,
        "compliant": gap == 0,
        "ep_breakdown": quota_info["ep_breakdown"],
    }


# ---------------------------------------------------------------------------
# EP renewal alerts
# ---------------------------------------------------------------------------

def check_ep_renewal_alerts(company: str, as_of_date=None) -> list:
    """Return EP holders whose renewal is within 60 days and quota is not met.

    Args:
        company:     Company name.
        as_of_date:  Date to check from (defaults to today).

    Returns:
        List of dicts: {employee, employee_name, ep_expiry_date, days_remaining,
                        quota_gap, message}
    """
    check_date = getdate(as_of_date or nowdate())
    alert_cutoff = add_days(check_date, EP_RENEWAL_ALERT_DAYS)

    # Fetch EP holders expiring within alert window
    ep_holders = frappe.get_all(
        "Employee",
        filters={
            "company": company,
            "status": "Active",
            "custom_ep_category": ("in", list(QUOTA_PER_EP_CAT.keys())),
            "custom_ep_expiry_date": ("between", [str(check_date), str(alert_cutoff)]),
        },
        fields=["name", "employee_name", "custom_ep_category", "custom_ep_expiry_date"],
    )

    alerts = []
    current_year = check_date.year

    # Get company-level compliance for this year
    summary = get_compliance_summary(company, current_year)
    gap = summary["gap"]

    for emp in ep_holders:
        if gap <= 0:
            break  # Quota fully met — no alerts needed
        expiry = getdate(emp["custom_ep_expiry_date"])
        days_remaining = date_diff(expiry, check_date)
        alerts.append(
            {
                "employee": emp["name"],
                "employee_name": emp["employee_name"],
                "ep_category": emp["custom_ep_category"],
                "ep_expiry_date": str(emp["custom_ep_expiry_date"]),
                "days_remaining": days_remaining,
                "quota_gap": gap,
                "message": (
                    f"{emp['employee_name']} EP expires in {days_remaining} days "
                    f"({emp['custom_ep_expiry_date']}). "
                    f"Internship quota unfulfilled: {gap} placement(s) outstanding."
                ),
            }
        )

    return alerts
