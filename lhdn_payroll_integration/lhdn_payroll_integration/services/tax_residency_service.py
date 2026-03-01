"""Mid-Year Tax Residency Status Change Workflow (US-176).

Handles the workflow when an employee's tax residency status changes mid-year:
  - Resident → Non-Resident: flat 30% PCB for all subsequent months; TP1 reliefs suspended
  - Non-Resident → Resident: progressive PCB rates restored; TP1 reliefs reinstated

Key regulatory references:
  - ITA 1967 Section 7: 182-day physical presence rule for residency
  - LHDN PCB Specification 2025: non-resident flat 30% on ALL employment income
  - No personal reliefs apply to non-resident employees (TP1 suspended)

Public API:
  - change_residency_status(employee_name, new_status, effective_date, changed_by)
  - get_pcb_multiplier_for_residency(employee_doc_or_dict, payroll_month_date)
  - suspend_tp1_reliefs_for_year(employee_name, tax_year)
  - reinstate_tp1_reliefs_for_year(employee_name, tax_year)
  - get_residency_change_warning(old_status, new_status)
"""

from datetime import date

import frappe
from frappe.utils import getdate, today

# Valid residency status options (must match the custom field options exactly)
RESIDENCY_STATUS_RESIDENT = "Resident"
RESIDENCY_STATUS_NON_RESIDENT = "Non-Resident"
RESIDENCY_STATUS_PENDING = "Pending Determination"

VALID_STATUSES = (
    RESIDENCY_STATUS_RESIDENT,
    RESIDENCY_STATUS_NON_RESIDENT,
    RESIDENCY_STATUS_PENDING,
)

# Non-resident flat PCB rate (ITA 1967, no Schedule A brackets apply)
NON_RESIDENT_PCB_RATE = 0.30


def change_residency_status(
    employee_name: str,
    new_status: str,
    effective_date,
    changed_by: str = None,
) -> dict:
    """Change an employee's tax residency status with full audit trail and side effects.

    Side effects:
      - Updates ``custom_tax_residency_status`` and ``custom_tax_residency_effective_date``
        on the Employee record.
      - Creates a PCB Change Log entry (change_type="Residency Status Change").
      - If ``new_status`` is Non-Resident: suspends TP1 reliefs for the effective year.
      - If ``new_status`` is Resident: reinstates TP1 reliefs for the effective year.

    Args:
        employee_name: Frappe name of the Employee document.
        new_status: One of VALID_STATUSES.
        effective_date: date or date-string; the month from which the new PCB rate applies.
        changed_by: User making the change (defaults to frappe.session.user).

    Returns:
        dict with keys:
          - "warning" (str): user-facing warning message (may be empty)
          - "old_status" (str): previous residency status
          - "new_status" (str): new residency status
          - "effective_date" (date): parsed effective date

    Raises:
        frappe.ValidationError: if new_status is not in VALID_STATUSES.
        frappe.DoesNotExistError: if employee_name does not exist.
    """
    if new_status not in VALID_STATUSES:
        frappe.throw(
            f"Invalid tax residency status '{new_status}'. "
            f"Must be one of: {', '.join(VALID_STATUSES)}",
            frappe.ValidationError,
        )

    if changed_by is None:
        changed_by = frappe.session.user

    effective_date = getdate(effective_date)
    tax_year = effective_date.year

    employee_doc = frappe.get_doc("Employee", employee_name)
    old_status = getattr(employee_doc, "custom_tax_residency_status", "") or RESIDENCY_STATUS_RESIDENT

    # Update the Employee record
    employee_doc.custom_tax_residency_status = new_status
    employee_doc.custom_tax_residency_effective_date = effective_date
    employee_doc.save(ignore_permissions=True)

    # Create PCB audit log entry
    _log_residency_change(
        employee_name=employee_name,
        employee_doc=employee_doc,
        old_status=old_status,
        new_status=new_status,
        effective_date=effective_date,
        changed_by=changed_by,
    )

    # Side effects based on status direction
    if new_status == RESIDENCY_STATUS_NON_RESIDENT:
        suspend_tp1_reliefs_for_year(employee_name, tax_year)
    elif new_status == RESIDENCY_STATUS_RESIDENT and old_status == RESIDENCY_STATUS_NON_RESIDENT:
        reinstate_tp1_reliefs_for_year(employee_name, tax_year)

    warning = get_residency_change_warning(old_status, new_status)

    return {
        "warning": warning,
        "old_status": old_status,
        "new_status": new_status,
        "effective_date": effective_date,
    }


def get_pcb_multiplier_for_residency(employee_doc_or_dict, payroll_month_date=None) -> float | None:
    """Return 0.30 (30%) if employee is Non-Resident as of payroll_month_date, else None.

    When None is returned, the caller should use the standard progressive PCB
    calculation (no override).

    Args:
        employee_doc_or_dict: Employee Frappe doc or dict-like with:
            - custom_tax_residency_status (str)
            - custom_tax_residency_effective_date (date/str, optional)
        payroll_month_date: The payroll month (date or str). Defaults to today.

    Returns:
        float 0.30 if Non-Resident and effective date has passed, else None.
    """
    if payroll_month_date is None:
        payroll_month_date = date.today()
    else:
        payroll_month_date = getdate(payroll_month_date)

    status = (
        employee_doc_or_dict.get("custom_tax_residency_status")
        if hasattr(employee_doc_or_dict, "get")
        else getattr(employee_doc_or_dict, "custom_tax_residency_status", None)
    )

    if status != RESIDENCY_STATUS_NON_RESIDENT:
        return None

    # Check that the effective date has been reached
    effective_date_raw = (
        employee_doc_or_dict.get("custom_tax_residency_effective_date")
        if hasattr(employee_doc_or_dict, "get")
        else getattr(employee_doc_or_dict, "custom_tax_residency_effective_date", None)
    )

    if effective_date_raw:
        effective_date = getdate(effective_date_raw)
        if payroll_month_date < effective_date:
            return None  # Status not yet in effect for this payroll month

    return NON_RESIDENT_PCB_RATE


def suspend_tp1_reliefs_for_year(employee_name: str, tax_year: int) -> bool:
    """Mark the employee's TP1 Relief record for tax_year as suspended.

    Adds a ``custom_reliefs_suspended`` = 1 flag on the TP1 record.
    If no TP1 record exists for the year, returns False (nothing to suspend).

    Args:
        employee_name: Employee name.
        tax_year: Assessment year (int).

    Returns:
        True if a record was found and suspended, False otherwise.
    """
    existing = frappe.get_all(
        "Employee TP1 Relief",
        filters={"employee": employee_name, "tax_year": str(tax_year)},
        fields=["name", "custom_reliefs_suspended"],
        limit=1,
    )
    if not existing:
        return False

    tp1 = frappe.get_doc("Employee TP1 Relief", existing[0]["name"])
    tp1.custom_reliefs_suspended = 1
    tp1.save(ignore_permissions=True)
    return True


def reinstate_tp1_reliefs_for_year(employee_name: str, tax_year: int) -> bool:
    """Reinstate TP1 reliefs that were suspended due to Non-Resident status.

    Clears ``custom_reliefs_suspended`` on the TP1 record.
    If no TP1 record exists for the year, returns False.

    Args:
        employee_name: Employee name.
        tax_year: Assessment year (int).

    Returns:
        True if a record was found and reinstated, False otherwise.
    """
    existing = frappe.get_all(
        "Employee TP1 Relief",
        filters={"employee": employee_name, "tax_year": str(tax_year)},
        fields=["name", "custom_reliefs_suspended"],
        limit=1,
    )
    if not existing:
        return False

    tp1 = frappe.get_doc("Employee TP1 Relief", existing[0]["name"])
    tp1.custom_reliefs_suspended = 0
    tp1.save(ignore_permissions=True)
    return True


def get_residency_change_warning(old_status: str, new_status: str) -> str:
    """Return the appropriate user-facing warning message for a residency status change.

    Args:
        old_status: Previous residency status.
        new_status: New residency status.

    Returns:
        Warning message string (may be empty if no warning needed).
    """
    if new_status == RESIDENCY_STATUS_NON_RESIDENT:
        return (
            "Prior-month PCB for this year should be reviewed — non-resident rate is not "
            "retroactively applied by the employer; advise employee to seek LHDN guidance "
            "for year-end reconciliation. TP1 reliefs have been suspended for this assessment year."
        )
    elif new_status == RESIDENCY_STATUS_RESIDENT and old_status == RESIDENCY_STATUS_NON_RESIDENT:
        return (
            "TP1 reliefs have been reinstated from the effective date. Note: LHDN approval "
            "may be required for mid-year switch from Non-Resident back to Resident status. "
            "Please review with your tax advisor."
        )
    return ""


def _log_residency_change(
    employee_name: str,
    employee_doc,
    old_status: str,
    new_status: str,
    effective_date: date,
    changed_by: str,
) -> None:
    """Create a PCB Change Log entry for a residency status change."""
    payroll_period = str(effective_date)[:7]  # "YYYY-MM"
    reason = (
        f"Tax Residency Status changed from '{old_status}' to '{new_status}' "
        f"effective {effective_date}. Changed by: {changed_by}"
    )
    try:
        log = frappe.get_doc({
            "doctype": "PCB Change Log",
            "employee": employee_name,
            "payroll_period": payroll_period,
            "company": getattr(employee_doc, "company", ""),
            "salary_slip": "",
            "change_type": "Residency Status Change",
            "old_pcb_amount": 0.0,
            "new_pcb_amount": 0.0,
            "changed_by": changed_by,
            "reason": reason,
        })
        log.insert(ignore_permissions=True)
        frappe.db.commit()
    except Exception:
        frappe.log_error(
            frappe.get_traceback(),
            f"Residency Change PCB Log Failed: {employee_name}",
        )
