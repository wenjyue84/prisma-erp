"""LHDN submission service — handles on_submit hooks for Salary Slip and Expense Claim.

Calls the exemption filter to determine if a document should be submitted to LHDN.
If exempt, sets status to 'Exempt'. If in scope, validates and enqueues for async processing.
Background jobs build UBL XML, POST to LHDN MyInvois API, and write the response back.
"""
import json

import frappe
import requests

from lhdn_payroll_integration.services.exemption_filter import should_submit_to_lhdn
from lhdn_payroll_integration.services.payload_builder import (
    build_salary_slip_xml,
    build_expense_claim_xml,
    prepare_submission_wrapper,
)
from lhdn_payroll_integration.utils.validation import validate_document_name_length

SUBMISSION_ENDPOINT = "/api/v1.0/documentsubmissions"


def _format_rejection_errors(error):
    """Parse LHDN 202 rejection error into human-readable text.

    For immediate rejections in the 202 response's rejectedDocuments array.
    Input shape: {code, message, details: [{code, message, target}]}

    Args:
        error: The error dict from a rejected document.

    Returns:
        str: Formatted error text with header, error lines, and raw JSON.
    """
    details = error.get("details", [])

    if not details:
        return "LHDN returned Invalid status with no error details"

    lines = []
    lines.append(f"LHDN Validation Failed \u2014 {len(details)} error(s)\n")

    for detail in details:
        code = detail.get("code", "UNKNOWN")
        field = detail.get("target", "unknown")
        message = detail.get("message", "No message")
        lines.append(f"[{code}] {field}: {message}")

    lines.append("\n---RAW JSON---")
    lines.append(json.dumps(error, indent=2))

    return "\n".join(lines)


def get_access_token(company_name):
    """Get LHDN MyInvois API bearer token for the given company.

    Checks for a cached token on the Company doc. Returns the cached token
    only if more than 5 minutes remain until expiry. If expiry is within
    5 minutes (or no expiry is set for an empty cache), delegates to
    myinvois_erpgulf's taxpayerlogin module to refresh.

    Exceptions are logged via frappe.log_error() rather than silently
    swallowed; empty string is returned on failure.

    Args:
        company_name: The Company name to fetch token for.

    Returns:
        str: Bearer token string, or empty string on failure.
    """
    company = frappe.get_doc("Company", company_name)
    if company.custom_bearer_token:
        expires_at = company.custom_token_expires_at
        if expires_at:
            now = frappe.utils.now_datetime()
            time_remaining = (expires_at - now).total_seconds()
            if time_remaining > 300:  # more than 5 minutes remaining
                return company.custom_bearer_token
        else:
            # No expiry timestamp set — trust the cached token
            return company.custom_bearer_token
    try:
        from myinvois_erpgulf.myinvois_erpgulf.taxpayerlogin import (
            get_access_token as _get_token,
        )
        return _get_token(company_name)
    except Exception:
        frappe.log_error(
            title=f"LHDN Token Error: {company_name}",
            message=frappe.get_traceback(),
        )
        return ""


def _get_submission_url(company):
    """Build the LHDN document submission URL from Company config.

    Args:
        company: The Company Frappe document.

    Returns:
        str: Full submission endpoint URL.
    """
    if company.custom_integration_type == "Sandbox":
        base_url = company.custom_sandbox_url
    else:
        base_url = company.custom_production_url
    return f"{base_url.rstrip('/')}{SUBMISSION_ENDPOINT}"


def _write_response_to_doc(doctype, docname, response):
    """Parse LHDN 202 response and update the Frappe document.

    On acceptedDocuments: sets custom_lhdn_status='Submitted' and stores UUID.
    On rejectedDocuments: sets custom_lhdn_status='Invalid' and logs error.

    Args:
        doctype: The Frappe doctype (e.g. 'Salary Slip').
        docname: The document name.
        response: The requests Response object.
    """
    data = response.json()

    accepted = data.get("acceptedDocuments", [])
    rejected = data.get("rejectedDocuments", [])

    if accepted:
        doc_data = accepted[0]
        frappe.db.set_value(doctype, docname, "custom_lhdn_status", "Submitted")
        frappe.db.set_value(doctype, docname, "custom_lhdn_uuid", doc_data.get("uuid", ""))
    elif rejected:
        doc_data = rejected[0]
        error_info = doc_data.get("error", {})
        error_msg = _format_rejection_errors(error_info)
        frappe.db.set_value(doctype, docname, "custom_lhdn_status", "Invalid")
        frappe.db.set_value(doctype, docname, "custom_error_log", error_msg)


@frappe.whitelist()
def resubmit_to_lhdn(docname, doctype="Salary Slip"):
    """Reset LHDN status to Pending and re-enqueue a stuck Invalid submission.

    Only System Manager users may call this action. The document must currently
    have custom_lhdn_status of 'Invalid' or 'Submitted' (stuck / needs retry).

    Args:
        docname: The document name (e.g. 'Sal Slip/2026/00001').
        doctype: The Frappe doctype — 'Salary Slip' or 'Expense Claim'.

    Raises:
        frappe.PermissionError: If the current user lacks System Manager role.
        frappe.ValidationError: If the document's LHDN status is not Invalid or Submitted.
    """
    if "System Manager" not in frappe.get_roles():
        frappe.throw(
            "Only System Manager can resubmit documents to LHDN.",
            frappe.PermissionError,
        )

    doc = frappe.get_doc(doctype, docname)
    allowed_statuses = {"Invalid", "Submitted"}
    if doc.custom_lhdn_status not in allowed_statuses:
        frappe.throw(
            f"Cannot resubmit: LHDN Status is '{doc.custom_lhdn_status}'. "
            f"Only documents with status Invalid or Submitted can be resubmitted.",
            frappe.ValidationError,
        )

    frappe.db.set_value(doctype, docname, "custom_lhdn_status", "Pending")

    if doctype == "Salary Slip":
        method = "lhdn_payroll_integration.services.submission_service.process_salary_slip"
    else:
        method = "lhdn_payroll_integration.services.submission_service.process_expense_claim"

    frappe.enqueue(
        method=method,
        docname=docname,
        queue="short",
        timeout=300,
    )


def schedule_retry(doctype, docname, process_method):
    """Schedule a retry for a failed LHDN submission.

    Increments the retry count and re-enqueues the processing method.

    Args:
        doctype: The Frappe doctype.
        docname: The document name.
        process_method: The dotted path to the process function.
    """
    current_count = frappe.db.get_value(doctype, docname, "custom_retry_count") or 0
    frappe.db.set_value(doctype, docname, "custom_retry_count", current_count + 1)
    frappe.enqueue(
        method=process_method,
        docname=docname,
        queue="short",
        timeout=300,
    )


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

    Builds UBL XML, POSTs to LHDN MyInvois API, and writes the response.
    On 401: refreshes token and retries once.
    On Timeout/ConnectionError: schedules retry with exponential backoff.
    On other exceptions: sets status to Invalid with error log.

    Args:
        docname: The Salary Slip document name.
    """
    doc = frappe.get_doc("Salary Slip", docname)
    company_name = doc.company

    xml_string = build_salary_slip_xml(docname)
    submission_data = prepare_submission_wrapper(xml_string, docname)

    token = get_access_token(company_name)
    company = frappe.get_doc("Company", company_name)
    url = _get_submission_url(company)

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    try:
        response = requests.post(url, json=submission_data, headers=headers)

        if response.status_code == 401:
            token = get_access_token(company_name)
            headers["Authorization"] = f"Bearer {token}"
            response = requests.post(url, json=submission_data, headers=headers)

        _write_response_to_doc("Salary Slip", docname, response)

    except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
        schedule_retry(
            "Salary Slip",
            docname,
            "lhdn_payroll_integration.services.submission_service.process_salary_slip",
        )
    except Exception as e:
        frappe.db.set_value("Salary Slip", docname, "custom_lhdn_status", "Invalid")
        frappe.db.set_value("Salary Slip", docname, "custom_error_log", str(e))


def process_expense_claim(docname):
    """Background job to process an Expense Claim for LHDN submission.

    Builds UBL XML, POSTs to LHDN MyInvois API, and writes the response.
    On 401: refreshes token and retries once.
    On Timeout/ConnectionError: schedules retry with exponential backoff.
    On other exceptions: sets status to Invalid with error log.

    Args:
        docname: The Expense Claim document name.
    """
    doc = frappe.get_doc("Expense Claim", docname)
    company_name = doc.company

    xml_string = build_expense_claim_xml(docname)
    submission_data = prepare_submission_wrapper(xml_string, docname)

    token = get_access_token(company_name)
    company = frappe.get_doc("Company", company_name)
    url = _get_submission_url(company)

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    try:
        response = requests.post(url, json=submission_data, headers=headers)

        if response.status_code == 401:
            token = get_access_token(company_name)
            headers["Authorization"] = f"Bearer {token}"
            response = requests.post(url, json=submission_data, headers=headers)

        _write_response_to_doc("Expense Claim", docname, response)

    except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
        schedule_retry(
            "Expense Claim",
            docname,
            "lhdn_payroll_integration.services.submission_service.process_expense_claim",
        )
    except Exception as e:
        frappe.db.set_value("Expense Claim", docname, "custom_lhdn_status", "Invalid")
        frappe.db.set_value("Expense Claim", docname, "custom_error_log", str(e))
