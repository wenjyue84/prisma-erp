"""
US-092: LHDN MyInvois Webhook Callback Handler

Receives real-time document status push notifications from LHDN MyInvois.
Eliminates need for hourly polling by handling webhook callbacks directly.

Endpoint: POST /api/method/lhdn_payroll_integration.api.lhdn_webhook.receive_status_callback

Expected payload:
    {
        "company": "<Company name>",
        "document_id": "<LHDN UUID>",
        "status": "Valid" | "Invalid" | "Cancelled"
    }

Required header:
    X-LHDN-Signature: <HMAC-SHA256 hex digest of body using webhook secret>
"""

import hmac
import hashlib
import json

import frappe
from frappe import _


@frappe.whitelist(allow_guest=True)
def receive_status_callback():
    """
    Receive LHDN webhook status push notification.

    Validates X-LHDN-Signature HMAC-SHA256 before processing.
    Returns 401 if signature is invalid or webhook secret not configured.
    Updates the corresponding Salary Slip / Expense Claim custom_lhdn_status.
    """
    # Use frappe.local.request to avoid LocalProxy binding issues in tests
    request = getattr(frappe.local, "request", None)
    raw_body = request.get_data(as_text=True) if request else ""

    # Parse payload
    try:
        payload = json.loads(raw_body) if raw_body else {}
    except (json.JSONDecodeError, ValueError):
        frappe.response["http_status_code"] = 400
        return {"error": "Invalid JSON payload"}

    company = payload.get("company") or frappe.defaults.get_global_default("company")

    # Fetch webhook secret from Company
    webhook_secret = frappe.db.get_value(
        "Company", company, "custom_lhdn_webhook_secret"
    )
    if not webhook_secret:
        frappe.response["http_status_code"] = 401
        return {"error": "Webhook secret not configured"}

    # Validate HMAC-SHA256 signature
    received_sig = request.headers.get("X-LHDN-Signature", "") if request else ""
    if not _verify_signature(raw_body, webhook_secret, received_sig):
        frappe.response["http_status_code"] = 401
        return {"error": "Invalid signature"}

    # Extract required fields
    document_id = payload.get("document_id")
    status = payload.get("status")

    if not document_id or not status:
        frappe.response["http_status_code"] = 400
        return {"error": "Missing document_id or status"}

    # Update the document status
    _update_document_status(document_id, status)

    return {"status": "ok", "document_id": document_id, "updated_status": status}


def _verify_signature(body: str, secret: str, received_sig: str) -> bool:
    """
    Verify HMAC-SHA256 signature of the webhook payload.

    Args:
        body: Raw request body string.
        secret: Webhook secret from Company.custom_lhdn_webhook_secret.
        received_sig: Signature from X-LHDN-Signature header.

    Returns:
        True if signature matches, False otherwise.
    """
    if not received_sig:
        return False

    computed = hmac.new(
        secret.encode("utf-8"),
        body.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(computed, received_sig)


def _update_document_status(document_id: str, status: str) -> None:
    """
    Find and update the document with the given LHDN UUID.

    Searches Salary Slip and Expense Claim for custom_lhdn_uuid = document_id.
    Maps LHDN webhook status to internal custom_lhdn_status values.

    Args:
        document_id: LHDN UUID from the webhook payload.
        status: Status string from LHDN (e.g. "Valid", "Invalid", "Cancelled").
    """
    # Map LHDN webhook status to internal status values
    status_map = {
        "Valid": "Submitted",
        "Invalid": "Invalid",
        "Cancelled": "Cancelled",
    }
    internal_status = status_map.get(status, status)

    for doctype in ("Salary Slip", "Expense Claim"):
        docname = frappe.db.get_value(
            doctype, {"custom_lhdn_uuid": document_id}, "name"
        )
        if docname:
            frappe.db.set_value(doctype, docname, "custom_lhdn_status", internal_status)
            frappe.db.commit()
            return
