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


def get_access_token(company_name):
    """Get LHDN MyInvois API bearer token for the given company.

    Checks for a cached token on the Company doc first. If none,
    delegates to myinvois_erpgulf's taxpayerlogin module.

    Args:
        company_name: The Company name to fetch token for.

    Returns:
        str: Bearer token string.
    """
    company = frappe.get_doc("Company", company_name)
    if company.custom_bearer_token:
        return company.custom_bearer_token
    try:
        from myinvois_erpgulf.myinvois_erpgulf.taxpayerlogin import (
            get_access_token as _get_token,
        )
        return _get_token(company_name)
    except Exception:
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
        error_msg = json.dumps(error_info) if isinstance(error_info, dict) else str(error_info)
        frappe.db.set_value(doctype, docname, "custom_lhdn_status", "Invalid")
        frappe.db.set_value(doctype, docname, "custom_error_log", error_msg)


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
