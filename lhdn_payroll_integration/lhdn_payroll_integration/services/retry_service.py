"""Exponential backoff retry service for LHDN submissions.

Retries failed LHDN API calls with exponential backoff:
wait_seconds = min(2**retry_count * 60, 3600), capped at 5 retries.
On the 6th failure (count >= 5), marks document as Invalid.
"""
import frappe

MAX_RETRIES = 5

PROCESS_METHODS = {
    "Salary Slip": "lhdn_payroll_integration.services.submission_service.process_salary_slip",
    "Expense Claim": "lhdn_payroll_integration.services.submission_service.process_expense_claim",
}


def schedule_retry(doctype, docname, error):
    """Schedule a retry for a failed LHDN submission with exponential backoff.

    Increments custom_retry_count. If under max retries, enqueues the
    appropriate process function with a computed delay. If max retries
    exceeded, sets custom_lhdn_status to 'Invalid'.

    Args:
        doctype: The Frappe doctype (e.g. 'Salary Slip', 'Expense Claim').
        docname: The document name.
        error: Error description string from the failed attempt.
    """
    doc = frappe.get_doc(doctype, docname)
    current_count = doc.custom_retry_count or 0
    new_count = current_count + 1

    doc.db_set("custom_retry_count", new_count, update_modified=False)

    if new_count > MAX_RETRIES:
        doc.db_set("custom_lhdn_status", "Invalid", update_modified=False)
        doc.db_set(
            "custom_error_log",
            "Max retries exceeded \u2014 manual intervention required",
            update_modified=False,
        )
        return

    wait_seconds = min(2 ** new_count * 60, 3600)
    process_method = PROCESS_METHODS.get(doctype)

    frappe.enqueue(
        method=process_method,
        docname=docname,
        queue="long",
        timeout=300,
        enqueue_after_timeout=wait_seconds,
    )
