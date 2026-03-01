"""Domestic servant EPF exclusion service (US-130).

KWSP (EPF) circular — October 2025:
Domestic servants (maids, cooks, cleaners, drivers, gardeners employed in a private
household) are excluded from the October 2025 foreign worker EPF mandatory contribution.

This module provides:
  - is_domestic_servant_epf_excluded(employee_name) — check exclusion flag
  - warn_domestic_servant_epf(doc, method) — before_submit hook on Salary Slip

Reference: KWSP mandatory-contribution page; EPF (Amendment) Act 2024.
"""
import frappe
from frappe.utils import flt


def is_domestic_servant_epf_excluded(employee_name):
    """Return True if employee is a foreign domestic servant exempt from EPF.

    Checks both is_foreign_worker and is_domestic_servant flags.
    Only foreign domestic servants are excluded (local employees are covered
    regardless of domestic role).

    Args:
        employee_name: str, Frappe Employee docname.

    Returns:
        bool: True if employee is a foreign domestic servant (EPF excluded).
    """
    result = frappe.db.get_value(
        "Employee",
        employee_name,
        ["custom_is_foreign_worker", "custom_is_domestic_servant"],
        as_dict=True,
    )
    if not result:
        return False
    return bool(result.get("custom_is_foreign_worker")) and bool(result.get("custom_is_domestic_servant"))


# EPF salary component names to check for accidental inclusion
_EPF_COMPONENT_KEYWORDS = {
    "EPF", "KWSP", "EPF Employee", "KWSP Employee",
    "EPF - Employer", "KWSP - Employer", "EPF Employer", "KWSP Employer",
    "EPF Employee (Foreign Worker)", "EPF Employer (Foreign Worker)",
}


def warn_domestic_servant_epf(doc, method=None):
    """Salary Slip before_submit hook: warn if EPF found for domestic servant.

    If the employee is flagged as a foreign domestic servant (EPF excluded),
    and the salary slip contains EPF deduction/earning components, log a
    frappe.msgprint warning so HR can correct before finalising.

    The warning does NOT block submission (non-blocking) — it is advisory.

    Args:
        doc: Salary Slip document.
        method: Hook method name (unused).
    """
    if not is_domestic_servant_epf_excluded(doc.employee):
        return

    # Collect EPF lines from deductions (and earnings as a safety net)
    epf_lines = []
    for detail in (doc.deductions or []):
        if detail.salary_component in _EPF_COMPONENT_KEYWORDS:
            epf_lines.append((detail.salary_component, flt(detail.amount, 2)))

    for detail in (doc.earnings or []):
        if detail.salary_component in _EPF_COMPONENT_KEYWORDS:
            epf_lines.append((detail.salary_component, flt(detail.amount, 2)))

    if epf_lines:
        lines_text = "\n".join(
            f"  - {comp}: RM {amt:,.2f}" for comp, amt in epf_lines
        )
        frappe.msgprint(
            msg=(
                f"<b>EPF Warning - Domestic Servant Exclusion</b><br><br>"
                f"Employee <b>{doc.employee_name}</b> ({doc.employee}) is flagged as a "
                f"foreign domestic servant and is <b>excluded</b> from EPF contributions "
                f"under the KWSP October 2025 circular.<br><br>"
                f"The following EPF components were found on this salary slip:<br>"
                f"<pre>{lines_text}</pre>"
                f"Please remove these EPF components before submitting."
            ),
            title="EPF - Domestic Servant Exemption Warning",
            indicator="orange",
        )
