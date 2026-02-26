"""LHDN submission service — handles on_submit hooks for Salary Slip and Expense Claim.

Calls the exemption filter to determine if a document should be submitted to LHDN.
If exempt, sets status to 'Exempt'. If in scope, validates and enqueues for async processing.
"""
import frappe
from lhdn_payroll_integration.services.exemption_filter import should_submit_to_lhdn
from lhdn_payroll_integration.utils.validation import validate_document_name_length


def enqueue_salary_slip_submission(doc, method):
    """on_submit hook for Salary Slip.

    Args:
        doc: The Salary Slip document.
        method: The hook method name (e.g. 'on_submit').
    """
    if not should_submit_to_lhdn("Salary Slip", doc):
        frappe.db.set_value("Salary Slip", doc.name, "custom_lhdn_status", "Exempt")
        return

    validate_document_name_length(doc.name)

    frappe.db.set_value("Salary Slip", doc.name, "custom_lhdn_status", "Pending")
    frappe.enqueue(
        method="lhdn_payroll_integration.services.submission_service.process_salary_slip",
        docname=doc.name,
        queue="short",
        timeout=300,
        enqueue_after_commit=True,
    )


def enqueue_expense_claim_submission(doc, method):
    """on_submit hook for Expense Claim.

    Args:
        doc: The Expense Claim document.
        method: The hook method name (e.g. 'on_submit').
    """
    if not should_submit_to_lhdn("Expense Claim", doc):
        frappe.db.set_value("Expense Claim", doc.name, "custom_lhdn_status", "Exempt")
        return

    validate_document_name_length(doc.name)

    frappe.db.set_value("Expense Claim", doc.name, "custom_lhdn_status", "Pending")
    frappe.enqueue(
        method="lhdn_payroll_integration.services.submission_service.process_expense_claim",
        docname=doc.name,
        queue="short",
        timeout=300,
        enqueue_after_commit=True,
    )


def process_salary_slip(docname):
    """Background job to process a Salary Slip for LHDN submission.

    Args:
        docname: The Salary Slip document name.
    """
    pass


def process_expense_claim(docname):
    """Background job to process an Expense Claim for LHDN submission.

    Args:
        docname: The Expense Claim document name.
    """
    pass
