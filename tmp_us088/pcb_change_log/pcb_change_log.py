"""PCB Change Log DocType controller.

Immutable audit log automatically created whenever a Salary Slip's PCB
component amount changes after initial save.

Created by US-088. Log entries are created via create_pcb_change_log()
called from the Salary Slip on_update doc event hook.
"""
import frappe
from frappe.model.document import Document


class PCBChangeLog(Document):
    pass


# PCB salary component names to detect
_PCB_COMPONENTS = frozenset({
    'Monthly Tax Deduction', 'PCB', 'Income Tax', 'Tax Deduction',
    'MTD', 'Potongan Cukai Berjadual',
})


def _get_pcb_amount(salary_slip_doc) -> float:
    """Extract total PCB deduction amount from a Salary Slip document."""
    total = 0.0
    for d in getattr(salary_slip_doc, 'deductions', []):
        if getattr(d, 'salary_component', '') in _PCB_COMPONENTS:
            total += float(getattr(d, 'amount', 0) or 0)
    return total


def create_pcb_change_log(
    salary_slip_doc,
    change_type: str = "Recalculation",
    old_pcb: float = 0.0,
    reason: str = "",
) -> None:
    """Create a PCB Change Log entry for a Salary Slip.

    Args:
        salary_slip_doc: The Salary Slip Frappe document.
        change_type: One of: TP1 Update, CP38 Applied, Category Change,
            Manual Override, Recalculation.
        old_pcb: PCB amount before the change.
        reason: Free-text reason for the change.
    """
    new_pcb = _get_pcb_amount(salary_slip_doc)

    end_date = getattr(salary_slip_doc, 'end_date', None) or getattr(salary_slip_doc, 'posting_date', None)
    payroll_period = str(end_date)[:7] if end_date else ""

    try:
        log = frappe.get_doc({
            'doctype': 'PCB Change Log',
            'employee': salary_slip_doc.employee,
            'payroll_period': payroll_period,
            'company': getattr(salary_slip_doc, 'company', ''),
            'salary_slip': salary_slip_doc.name,
            'change_type': change_type,
            'old_pcb_amount': old_pcb,
            'new_pcb_amount': new_pcb,
            'changed_by': frappe.session.user,
            'reason': reason,
        })
        log.insert(ignore_permissions=True)
        frappe.db.commit()
    except Exception as exc:
        frappe.log_error(f"Failed to create PCB Change Log: {exc}", "PCB Change Log")


def on_salary_slip_update(doc, method=None):
    """Salary Slip on_update hook: create PCB Change Log when PCB amount changes.

    Compares the current PCB amount with the before-save snapshot. Only creates
    a log entry when the PCB amount has actually changed.
    """
    try:
        before = doc.get_doc_before_save()
        if before is None:
            # New document — no before-save state
            return

        old_pcb = _get_pcb_amount(before)
        new_pcb = _get_pcb_amount(doc)

        if abs(new_pcb - old_pcb) < 0.01:
            # No meaningful change — skip log
            return

        create_pcb_change_log(
            doc,
            change_type="Recalculation",
            old_pcb=old_pcb,
            reason="PCB amount changed on Salary Slip update",
        )
    except Exception as exc:
        # Never let audit logging block payroll processing
        frappe.log_error(f"PCB Change Log hook error: {exc}", "PCB Change Log")
