"""LHDN cancellation service — handles on_cancel hooks for Salary Slip and Expense Claim.

Checks the 72-hour cancellation window from LHDN validation/submission time:
- If document was never submitted to LHDN (status not Valid/Submitted): allow native cancel.
- If within 72 hours: enqueue an async LHDN cancellation job.
- If past 72 hours: raise ValidationError directing user to issue a Credit Note.

process_lhdn_cancellation runs as an async background job:
- PUT to LHDN /documents/{uuid}/state with status='cancelled'
- On success: set custom_lhdn_status='Cancelled' and cancel the Frappe document
- On error: log the error, leave document unchanged
"""

import frappe
import requests


CANCELLATION_WINDOW_HOURS = 72
CANCELLATION_ENDPOINT = "/api/v1.0/documents/{uuid}/state"


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

    PUT {base_url}/api/v1.0/documents/{uuid}/state with status='cancelled'.
    On success: set custom_lhdn_status='Cancelled' and cancel the Frappe document.
    On error: log the error via frappe.log_error, leave document unchanged.

    Args:
        doctype: The Frappe doctype (e.g. 'Salary Slip').
        docname: The document name.
        uuid: The LHDN document UUID.
    """
    doc = frappe.get_doc(doctype, docname)
    company = frappe.get_doc("Company", doc.company)

    # Build API URL
    if company.custom_integration_type == "Sandbox":
        base_url = company.custom_sandbox_url
    else:
        base_url = company.custom_production_url

    url = f"{base_url.rstrip('/')}{CANCELLATION_ENDPOINT.format(uuid=uuid)}"

    # Get access token — prefer cached bearer token, fall back to taxpayer login
    token = getattr(company, "custom_bearer_token", "") or ""
    if not token:
        try:
            from myinvois_erpgulf.myinvois_erpgulf.taxpayerlogin import (
                get_access_token as _get_token,
            )
            token = _get_token(doc.company) or ""
        except Exception:
            pass

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    payload = {
        "status": "cancelled",
        "reason": "Correction required — see ERPNext document",
    }

    try:
        response = requests.put(url, json=payload, headers=headers)

        if response.status_code == 200:
            # LHDN accepted cancellation
            doc.db_set("custom_lhdn_status", "Cancelled", update_modified=False)
            doc.flags.ignore_permissions = True
            doc.cancel()
        else:
            # LHDN rejected cancellation — log error, leave document unchanged
            error_text = response.text
            frappe.log_error(
                message=f"LHDN cancellation failed for {doctype} {docname} (UUID: {uuid}). "
                        f"HTTP {response.status_code}: {error_text}",
                title=f"LHDN Cancellation Error: {docname}",
            )
    except Exception as e:
        frappe.log_error(
            message=f"LHDN cancellation exception for {doctype} {docname}: {str(e)}",
            title=f"LHDN Cancellation Error: {docname}",
        )
