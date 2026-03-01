"""Salary Slip validate hook — warn when employee TIN is missing (US-227).

LHDN e-PCB Plus advisory: employer must ensure all employees have a TIN
entered in the payroll system before CP39 upload. Missing TIN causes the
entire batch to be rejected.

This hook raises a non-blocking msgprint warning (orange) during Salary Slip
save/validation if the linked employee has no TIN stored in custom_employee_tin
(or the legacy custom_lhdn_tin field).

This is intentionally a WARNING, not a hard block, so payroll processing is
not disrupted if the TIN has not yet been collected.
"""

import frappe


def warn_missing_employee_tin(doc, method=None):
    """Warn (non-blocking) when Salary Slip employee has no TIN set.

    Triggered on Salary Slip validate event.

    Checks custom_employee_tin first, falls back to custom_lhdn_tin for
    backward compatibility. Shows a single orange msgprint if TIN is missing.

    Args:
        doc: Salary Slip document instance.
        method (str): Hook method name (unused).
    """
    employee_id = doc.employee
    if not employee_id:
        return

    tin = frappe.db.get_value(
        "Employee",
        employee_id,
        ["custom_employee_tin", "custom_lhdn_tin"],
        as_dict=True,
    )

    if not tin:
        return

    effective_tin = (tin.get("custom_employee_tin") or "").strip() or (
        tin.get("custom_lhdn_tin") or ""
    ).strip()

    if not effective_tin:
        frappe.msgprint(
            msg=(
                f"Employee <b>{doc.employee_name} ({employee_id})</b> has no TIN "
                f"(custom_employee_tin) set. The CP39 / e-PCB Plus monthly file "
                f"requires a valid TIN for every employee — missing TIN will cause "
                f"the batch upload to be rejected by LHDN. "
                f"Please update the employee record before CP39 export."
            ),
            title="Missing Employee TIN — e-PCB Plus Warning",
            indicator="orange",
        )
