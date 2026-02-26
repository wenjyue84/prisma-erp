"""LHDN cancellation service — handles on_cancel hooks for Salary Slip and Expense Claim.

Checks the 72-hour cancellation window from LHDN validation/submission time:
- If document was never submitted to LHDN (status not Valid/Submitted): allow native cancel.
- If within 72 hours: enqueue an async LHDN cancellation job.
- If past 72 hours: raise ValidationError directing user to issue a Credit Note.
"""

import frappe


CANCELLATION_WINDOW_HOURS = 72


def _get_reference_time(doc):
    """Get the reference datetime for the 72-hour window calculation.

    Prefers custom_lhdn_validated_datetime, falls back to
    custom_lhdn_submission_datetime.

    Args:
        doc: The Frappe document.

    Returns:
        datetime or None: The reference time, or None if neither field is set.
    """
    return doc.custom_lhdn_validated_datetime or doc.custom_lhdn_submission_datetime


def _handle_cancel(doc, method):
    """Core cancellation logic shared by Salary Slip and Expense Claim.

    Args:
        doc: The Frappe document being cancelled.
        method: The hook method name (e.g. 'on_cancel').
    """
    # If not submitted to LHDN, allow native cancellation
    if doc.custom_lhdn_status not in ("Valid", "Submitted"):
        return

    reference_time = _get_reference_time(doc)
    if not reference_time:
        return

    now = frappe.utils.now_datetime()
    hours_elapsed = (now - reference_time).total_seconds() / 3600

    if hours_elapsed <= CANCELLATION_WINDOW_HOURS:
        # Within window — enqueue async cancellation job
        frappe.enqueue(
            method="lhdn_payroll_integration.services.cancellation_service.process_lhdn_cancellation",
            doctype=doc.doctype,
            docname=doc.name,
            uuid=doc.custom_lhdn_uuid,
            queue="short",
            timeout=300,
            enqueue_after_commit=True,
        )
    else:
        # Past window — block with guidance
        frappe.throw(
            "This e-Invoice was validated more than 72 hours ago and cannot be "
            "directly cancelled. Please issue a Self-Billed Credit Note (type 12) "
            "to reverse this transaction.",
            frappe.ValidationError,
        )


def handle_salary_slip_cancel(doc, method):
    """on_cancel hook for Salary Slip.

    Args:
        doc: The Salary Slip document.
        method: The hook method name.
    """
    _handle_cancel(doc, method)


def handle_expense_claim_cancel(doc, method):
    """on_cancel hook for Expense Claim.

    Args:
        doc: The Expense Claim document.
        method: The hook method name.
    """
    _handle_cancel(doc, method)


def process_lhdn_cancellation(doctype, docname, uuid):
    """Background job to cancel an e-Invoice via LHDN MyInvois API.

    Stub — full implementation in US-017.

    Args:
        doctype: The Frappe doctype.
        docname: The document name.
        uuid: The LHDN document UUID.
    """
    pass
