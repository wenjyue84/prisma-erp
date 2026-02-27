"""Exemption filter service for LHDN payroll integration.

Determines whether a Salary Slip or Expense Claim should be submitted
to LHDN as a self-billed e-Invoice.

Worker type gate:
- Employee (contract of service) = always exempt per LHDN FAQ
- Contractor / Director = in-scope when self-billed flag is set

Director sub-classification (US-020):
- Director Fee  (board service)     → classification code 036
- Director Salary (executive role)  → classification code 004
"""
import frappe

# Only these worker types are in-scope for self-billed e-Invoice
IN_SCOPE_WORKER_TYPES = frozenset({"Contractor", "Director"})

# Default LHDN classification codes by worker type
_WORKER_TYPE_CLASSIFICATION = {
    "Contractor": "037",
    "Director": "036",  # default for Director Fee; Director Salary overrides to 004
}

# Director payment type → classification code override
_DIRECTOR_PAYMENT_TYPE_CLASSIFICATION = {
    "Director Fee": "036",
    "Director Salary": "004",
}


def get_default_classification_code(worker_type: str, employee=None) -> str:
    """Return the default LHDN classification code for a worker type.

    For Directors, inspects ``employee.custom_director_payment_type`` to
    distinguish between Director Fee (036) and Director Salary (004).

    Args:
        worker_type: 'Employee', 'Contractor', 'Director', or other.
        employee: Optional Frappe Employee document.  When provided and
                  worker_type is 'Director', the payment type field is
                  consulted for a more specific code.

    Returns:
        Classification code string, e.g. '036', '004', '037', '022'.
    """
    if worker_type == "Director" and employee is not None:
        payment_type = getattr(employee, "custom_director_payment_type", "") or ""
        if payment_type in _DIRECTOR_PAYMENT_TYPE_CLASSIFICATION:
            return _DIRECTOR_PAYMENT_TYPE_CLASSIFICATION[payment_type]
    return _WORKER_TYPE_CLASSIFICATION.get(worker_type, "022")


def should_submit_to_lhdn(doctype: str, doc) -> bool:
    """Check if a document should be submitted to LHDN.

    Args:
        doctype: "Salary Slip" or "Expense Claim"
        doc: The Frappe document object

    Returns:
        True if the document should be submitted to LHDN, False otherwise.
    """
    employee = frappe.get_doc("Employee", doc.employee)

    # Worker type gate: only Contractor/Director are in-scope
    worker_type = getattr(employee, "custom_worker_type", "") or ""
    if worker_type not in IN_SCOPE_WORKER_TYPES:
        return False

    if doctype == "Salary Slip":
        if not employee.custom_requires_self_billed_invoice:
            return False
        if doc.net_pay <= 0:
            return False
        return True

    if doctype == "Expense Claim":
        category = getattr(doc, "custom_expense_category", None)
        if category in ("Overseas - Exempt", "Employee Receipt Provided"):
            return False
        if category == "Self-Billed Required" and employee.custom_requires_self_billed_invoice:
            return True
        return False

    return False
