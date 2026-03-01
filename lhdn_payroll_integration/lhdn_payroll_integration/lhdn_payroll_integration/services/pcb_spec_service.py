"""PCB Specification Version Management Service (US-231).

Manages the active PCB Specification year stored in LHDN Payroll Settings,
provides version-aware helpers for the PCB calculation engine, and handles
the annual January update prompt.

LHDN publishes 'Spesifikasi Kaedah Pengiraan Berkomputer PCB' each year.
This service:
  - Retrieves the active spec year from LHDN Payroll Settings
  - Supplies the correct LHDN PDF URL per spec year
  - Provides a changelog of changed parameters between spec versions
  - Exposes get_pcb_spec_version_label() for payroll audit trail logging
  - Runs check_january_spec_alert() as a daily scheduler task

Ref:
  2025 spec: https://www.hasil.gov.my/media/mdahzjwi/spesifikasi-kaedah-pengiraan-berkomputer-pcb-2025.pdf
  2026 spec: https://www.hasil.gov.my/media/arvlrzh5/spesifikasi-kaedah-pengiraan-berkomputer-pcb-2026.pdf
"""
import datetime

import frappe

# ---------------------------------------------------------------------------
# Static data — spec URLs and changelogs
# ---------------------------------------------------------------------------

_SPEC_URLS = {
    2024: "",
    2025: "https://www.hasil.gov.my/media/mdahzjwi/spesifikasi-kaedah-pengiraan-berkomputer-pcb-2025.pdf",
    2026: "https://www.hasil.gov.my/media/arvlrzh5/spesifikasi-kaedah-pengiraan-berkomputer-pcb-2026.pdf",
}

# Changes between consecutive PCB specification years.
# Key: (from_year, to_year) — always from lower to higher year.
_SPEC_CHANGELOG = {
    (2024, 2025): [
        "Schedule 1 tax bands updated: new 30% tier for chargeable income exceeding RM2 million",
        "Band RM35,001–RM50,000: 8% → 6%",
        "Band RM50,001–RM70,000: 13% → 11%",
        "Band RM70,001–RM100,000: 21% → 19%",
        "Band RM100,001–RM250,000: 24% → 25%",
        "Band RM250,001–RM400,000 introduced at 26%",
        "Band RM400,001–RM2,000,000: 25% → 28%",
        "Band above RM2,000,000: 26% → 30% (new top rate)",
        "OKU disability relief updated: RM7,000 (self), RM6,000 (spouse)",
        "Food waste composting machine relief: RM2,500 permanent cap added to TP1",
        "TP1 form items revised per 2025 specification",
    ],
    (2025, 2026): [
        "No change to MTD Schedule D annualisation formula",
        "TP1 deduction items amended for YA2026 per Budget 2026",
        "New domestic tourism attraction expenses relief (RM1,000 cap) for YA2026",
        "Permanent RM3,000 childcare relief for JKM-registered transit childcare facilities",
        "Children's learning disability diagnostic relief increased to RM4,000",
        "TP1(1/2026) form format issued with Budget 2026 relief line items",
        "Senior Citizen employee double deduction extended to YA2030 (Budget 2026)",
        "OKU employee double deduction for remuneration extended to YA2030 (Budget 2026)",
    ],
}

_DEFAULT_SPEC_YEAR = 2025


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_active_pcb_spec_version() -> int:
    """Return the active PCB Specification year from LHDN Payroll Settings.

    Falls back to ``_DEFAULT_SPEC_YEAR`` (2025) if settings are not configured
    or the DocType does not exist yet.

    Returns:
        int: Active specification year, e.g. 2025 or 2026.
    """
    try:
        version_str = frappe.db.get_single_value(
            "LHDN Payroll Settings", "pcb_specification_version"
        )
        if version_str:
            return int(version_str)
    except Exception:
        pass
    return _DEFAULT_SPEC_YEAR


def get_spec_url_for_version(year: int) -> str:
    """Return the LHDN official PDF URL for the given specification year.

    Args:
        year: Specification year (e.g. 2025 or 2026).

    Returns:
        str: URL string, or empty string if unknown.
    """
    return _SPEC_URLS.get(int(year), "")


def get_spec_changelog(from_year: int, to_year: int) -> list:
    """Return the list of changed parameters between two spec years.

    Only consecutive year pairs are currently supported.  If the pair is
    not in the changelog, returns an empty list.

    Args:
        from_year: Earlier specification year.
        to_year:   Later specification year.

    Returns:
        list[str]: Human-readable changelog items.
    """
    key = (int(from_year), int(to_year))
    return list(_SPEC_CHANGELOG.get(key, []))


def get_pcb_spec_version_label(year: int = None) -> str:
    """Return the audit trail label for the given (or active) spec year.

    This string is embedded in Salary Slip payroll audit records to
    identify which PCB specification was used at computation time.

    Args:
        year: Specification year.  Defaults to ``get_active_pcb_spec_version()``.

    Returns:
        str: e.g. "2025 Spec Compliant" or "2026 Spec Compliant".
    """
    if year is None:
        year = get_active_pcb_spec_version()
    return f"{year} Spec Compliant"


# ---------------------------------------------------------------------------
# Scheduler task
# ---------------------------------------------------------------------------


def check_january_spec_alert():
    """Daily scheduler task: remind HR to verify LHDN spec update in January.

    Fires every day but only acts in January.  Creates a Frappe
    Notification Log entry for HR Manager / HR User / System Manager roles
    prompting them to check whether LHDN has published a new PCB specification
    for the current assessment year.

    Acceptance Criteria 5 (US-231):
        A warning is shown in January each year prompting HR to verify whether
        LHDN has published an updated specification for the new assessment year.
    """
    today = datetime.date.today()
    if today.month != 1:
        return

    current_year = today.year
    active_version = get_active_pcb_spec_version()

    # Only alert if the active spec is for last year (i.e. might be out of date)
    if active_version >= current_year:
        return

    subject = f"PCB Specification Annual Check — Verify YA{current_year} Update"
    message = (
        f"January Reminder: LHDN may have published a new PCB Computerised Calculation "
        f"Method Specification for YA{current_year}. "
        f"Current active version: <b>{active_version}</b>.<br>"
        f"Please verify at https://www.hasil.gov.my and update "
        f"<b>LHDN Payroll Settings &rarr; Active PCB Specification Year</b> "
        f"if a new specification has been published."
    )

    try:
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
            if frappe.db.exists(
                "Notification Log",
                {
                    "for_user": user,
                    "subject": subject,
                    "creation": [">=", frappe.utils.add_days(frappe.utils.nowdate(), -30)],
                },
            ):
                continue  # Already notified this month

            frappe.get_doc(
                {
                    "doctype": "Notification Log",
                    "for_user": user,
                    "type": "Alert",
                    "document_type": "LHDN Payroll Settings",
                    "document_name": "LHDN Payroll Settings",
                    "subject": subject,
                    "email_content": message,
                }
            ).insert(ignore_permissions=True)

        frappe.db.commit()

    except Exception as exc:
        frappe.log_error(
            f"check_january_spec_alert failed: {exc}", "PCB Spec Alert"
        )
