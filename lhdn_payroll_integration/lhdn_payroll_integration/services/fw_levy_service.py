"""Foreign Worker Levy Alert Service.

Daily scheduler: detect foreign workers with levy overdue or due within 30 days
and create a Frappe notification/alert.

US-070: Foreign Worker Levy Tracking.
US-095: Multi-Tier Levy Model (MTLM) rate calculation.
"""
import frappe
from frappe.utils import flt, getdate, today, add_days


OVERDUE_WINDOW_DAYS = 30

# MTLM_TIERS: {tier_name: (ratio_low, ratio_high, annual_levy_myr)}
# Effective January 2025 per Multi-Tier Levy Model.
# dependency_ratio = foreign_headcount / (local_headcount + foreign_headcount)
MTLM_TIERS = {
    "Tier 1": (0.0, 0.15, 410),
    "Tier 2": (0.15, 0.30, 1230),
    "Tier 3": (0.30, 1.0, 2500),
}


def calculate_fw_levy_tier(local_headcount, foreign_headcount, sector=None):
    """Return (tier_name, annual_levy_per_worker) based on MTLM dependency ratio.

    Args:
        local_headcount (int): Number of local (Malaysian) employees.
        foreign_headcount (int): Number of foreign workers.
        sector (str | None): Reserved for future sector-specific rates. Unused now.

    Returns:
        tuple: (tier_name: str, annual_levy_myr: int)
    """
    total = int(local_headcount or 0) + int(foreign_headcount or 0)
    if total == 0 or int(foreign_headcount or 0) == 0:
        return "Tier 1", MTLM_TIERS["Tier 1"][2]

    ratio = int(foreign_headcount) / total

    for tier_name, (low, high, rate) in MTLM_TIERS.items():
        if low <= ratio < high:
            return tier_name, rate

    # ratio >= 1.0 (all foreign) — falls into Tier 3
    return "Tier 3", MTLM_TIERS["Tier 3"][2]


def _get_overdue_employees(threshold_date):
    """Return list of foreign workers with levy due on or before threshold_date."""
    return frappe.db.sql(
        """
        SELECT
            name AS employee,
            employee_name,
            company,
            custom_fw_levy_due_date AS levy_due_date,
            custom_fw_levy_rate AS levy_rate
        FROM `tabEmployee`
        WHERE custom_is_foreign_worker = 1
          AND status = 'Active'
          AND custom_fw_levy_due_date IS NOT NULL
          AND custom_fw_levy_due_date <= %(threshold)s
        ORDER BY custom_fw_levy_due_date ASC
        """,
        {"threshold": threshold_date},
        as_dict=True,
    )


def check_overdue_fw_levy():
    """Daily scheduler task: notify HR Manager about overdue / due-soon FW levies."""
    threshold_date = add_days(today(), OVERDUE_WINDOW_DAYS)

    employees = _get_overdue_employees(threshold_date)

    if not employees:
        return

    today_date = getdate(today())
    overdue = [e for e in employees if getdate(e["levy_due_date"]) < today_date]
    due_soon = [e for e in employees if getdate(e["levy_due_date"]) >= today_date]

    lines = []
    if overdue:
        lines.append(f"<b>Overdue ({len(overdue)}):</b>")
        for e in overdue:
            lines.append(
                f"  - {e['employee_name']} ({e['employee']}) — due {e['levy_due_date']}"
                f" — MYR {flt(e['levy_rate'], 2):,.2f}"
            )

    if due_soon:
        lines.append(f"<b>Due within {OVERDUE_WINDOW_DAYS} days ({len(due_soon)}):</b>")
        for e in due_soon:
            lines.append(
                f"  - {e['employee_name']} ({e['employee']}) — due {e['levy_due_date']}"
                f" — MYR {flt(e['levy_rate'], 2):,.2f}"
            )

    message = (
        "Foreign Worker Levy Alert<br><br>"
        + "<br>".join(lines)
    )

    # Send system notification to HR Manager role
    try:
        frappe.sendmail(
            recipients=_get_hr_manager_emails(),
            subject="[LHDN Payroll] Foreign Worker Levy Overdue / Due Soon",
            message=message,
            delayed=False,
        )
    except Exception:
        pass  # Non-critical — log only

    frappe.logger(__name__).info(
        f"[FW Levy Alert] {len(overdue)} overdue, {len(due_soon)} due within "
        f"{OVERDUE_WINDOW_DAYS} days"
    )


def _get_hr_manager_emails():
    """Return list of email addresses for HR Manager role users."""
    users = frappe.db.sql(
        """
        SELECT DISTINCT u.email
        FROM `tabUser` u
        JOIN `tabHas Role` hr ON hr.parent = u.name
        WHERE hr.role = 'HR Manager'
          AND u.enabled = 1
          AND u.email IS NOT NULL
          AND u.email != ''
        """,
        as_dict=True,
    )
    return [u["email"] for u in users]


def is_levy_overdue_or_due_soon(levy_due_date, days=OVERDUE_WINDOW_DAYS):
    """Return True if levy_due_date is today or earlier, or within `days` days.

    Used by dashboard alert and tests.
    """
    if not levy_due_date:
        return False
    due = getdate(levy_due_date)
    threshold = getdate(add_days(today(), days))
    return due <= threshold
