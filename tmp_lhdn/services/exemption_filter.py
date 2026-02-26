"""Exemption filter service for LHDN payroll integration.

Determines whether a Salary Slip or Expense Claim should be submitted
to LHDN as a self-billed e-Invoice.
"""
import frappe


def should_submit_to_lhdn(doctype: str, doc) -> bool:
    """Check if a document should be submitted to LHDN.

    Args:
        doctype: "Salary Slip" or "Expense Claim"
        doc: The Frappe document object

    Returns:
        True if the document should be submitted to LHDN, False otherwise.
    """
    employee = frappe.get_doc("Employee", doc.employee)

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
