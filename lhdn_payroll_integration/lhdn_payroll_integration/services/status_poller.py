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


def _format_error_log(response):
    """Parse LHDN document details error response into human-readable text.

    For Status 3 (Invalid) responses from the document details endpoint.
    Input shape: {status, validationResults: {status, validationSteps: [
        {status, name, error: {propertyName, errorCode, error, innerError}}
    ]}}

    Args:
        response: The LHDN document details JSON dict.

    Returns:
        str: Formatted error text with header, error lines, and raw JSON.
    """
    validation_results = response.get("validationResults", {})
    steps = validation_results.get("validationSteps", [])

    if not steps:
        return "LHDN returned Invalid status with no error details"

    lines = []
    lines.append(f"LHDN Validation Failed \u2014 {len(steps)} error(s)\n")

    for step in steps:
        error = step.get("error", {})
        code = error.get("errorCode", "UNKNOWN")
        field = error.get("propertyName", "unknown")
        message = error.get("error", "No message")
        lines.append(f"[{code}] {field}: {message}")

    lines.append("\n---RAW JSON---")
    lines.append(json.dumps(response, indent=2))

    return "\n".join(lines)


def _get_base_url(company_name=None):
    """Get the LHDN API base URL from Company configuration.

    Args:
        company_name: The Company name to look up. Falls back to the site
            default company when not provided.

    Returns:
        str: Base URL (sandbox or production), or "" if not configured.
    """
    if not company_name:
        company_name = frappe.defaults.get_defaults().get("company")
    if not company_name:
        return ""
    company = frappe.get_doc("Company", company_name)
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
        error_msg = _format_error_log(data)
        frappe.db.set_value(doctype, doc.name, "custom_error_log", error_msg)


def poll_pending_documents():
    """Poll LHDN API for status updates on all pending documents.

    Queries both Salary Slip and Expense Claim for documents with
    custom_lhdn_status='Submitted' and a non-empty custom_lhdn_uuid.
    Fetches each document's current status from the LHDN API and
    updates accordingly.

    The base URL and token are resolved per document using the document's
    own Company, so multi-company setups are handled correctly.

    Processes max 100 documents per doctype per run.
    Individual document errors are caught and logged.
    """
    for doctype in DOCTYPES_TO_POLL:
        documents = frappe.get_all(
            doctype,
            filters={
                "custom_lhdn_status": "Submitted",
                "custom_lhdn_uuid": ["!=", ""],
            },
            fields=["name", "custom_lhdn_uuid", "custom_lhdn_status", "company"],
            limit_page_length=100,
        )

        for doc in documents:
            if not doc.get("custom_lhdn_uuid"):
                continue
            company_name = doc.get("company")
            token = get_access_token(company_name) if company_name else ""
            base_url = _get_base_url(company_name)
            try:
                _poll_single_document(doctype, doc, token, base_url)
            except Exception:
                frappe.log_error(
                    title=f"Status Poller: Error polling {doctype} {doc.name}",
                    message=frappe.get_traceback(),
                )
