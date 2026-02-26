"""LHDN status poller — polls pending documents for status updates.

Queries both Salary Slip and Expense Claim for documents with
custom_lhdn_status='Submitted', fetches their current status from the
LHDN API using the stored custom_lhdn_uuid, and updates the document
to 'Valid' (Status 2) or 'Invalid' (Status 3).

Processes in batches of 100 per doctype to avoid timeouts.
Individual document errors are caught and logged without aborting the batch.
"""
import json

import frappe
import requests

from lhdn_payroll_integration.services.submission_service import get_access_token

DOCUMENT_DETAILS_ENDPOINT = "/api/v1.0/documents/{uuid}/details"

DOCTYPES_TO_POLL = ["Salary Slip", "Expense Claim"]

# Map LHDN API status strings to ERPNext custom_lhdn_status values
LHDN_STATUS_MAP = {
    "valid": "Valid",
    "invalid": "Invalid",
    "submitted": "Submitted",
    "cancelled": "Cancelled",
}


def _get_base_url():
    """Get the LHDN API base URL from default Company configuration.

    Returns:
        str: Base URL (sandbox or production).
    """
    default_company = frappe.defaults.get_defaults().get("company")
    if not default_company:
        return ""
    company = frappe.get_doc("Company", default_company)
    if company.custom_integration_type == "Sandbox":
        return company.custom_sandbox_url or ""
    return company.custom_production_url or ""


def _poll_single_document(doctype, doc, token, base_url):
    """Poll the LHDN API for a single document's status and update accordingly.

    Args:
        doctype: The Frappe doctype (e.g. 'Salary Slip').
        doc: A frappe._dict with name, custom_lhdn_uuid, custom_lhdn_status.
        token: Bearer token string.
        base_url: LHDN API base URL.
    """
    uuid = doc.get("custom_lhdn_uuid")
    if not uuid:
        return

    url = f"{base_url.rstrip('/')}{DOCUMENT_DETAILS_ENDPOINT.format(uuid=uuid)}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    response = requests.get(url, headers=headers)
    data = response.json()

    lhdn_status = data.get("status", "").lower()
    erp_status = LHDN_STATUS_MAP.get(lhdn_status)

    if erp_status == "Valid":
        frappe.db.set_value(doctype, doc.name, "custom_lhdn_status", "Valid")
        validated_dt = data.get("dateTimeValidated", "")
        frappe.db.set_value(doctype, doc.name, "custom_lhdn_validated_datetime", validated_dt)
    elif erp_status == "Invalid":
        frappe.db.set_value(doctype, doc.name, "custom_lhdn_status", "Invalid")
        validation_results = data.get("validationResults", {})
        error_msg = json.dumps(validation_results) if isinstance(validation_results, dict) else str(validation_results)
        frappe.db.set_value(doctype, doc.name, "custom_error_log", error_msg)


def poll_pending_documents():
    """Poll LHDN API for status updates on all pending documents.

    Queries both Salary Slip and Expense Claim for documents with
    custom_lhdn_status='Submitted' and a non-empty custom_lhdn_uuid.
    Fetches each document's current status from the LHDN API and
    updates accordingly.

    Processes max 100 documents per doctype per run.
    Individual document errors are caught and logged.
    """
    token = get_access_token()

    for doctype in DOCTYPES_TO_POLL:
        documents = frappe.get_all(
            doctype,
            filters={
                "custom_lhdn_status": "Submitted",
                "custom_lhdn_uuid": ["!=", ""],
            },
            fields=["name", "custom_lhdn_uuid", "custom_lhdn_status"],
            limit_page_length=100,
        )

        for doc in documents:
            if not doc.get("custom_lhdn_uuid"):
                continue
            try:
                _poll_single_document(doctype, doc, token, "")
            except Exception:
                frappe.log_error(
                    title=f"Status Poller: Error polling {doctype} {doc.name}",
                    message=frappe.get_traceback(),
                )
