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
    build_consolidated_xml,
    prepare_submission_wrapper,
)
from lhdn_payroll_integration.utils.validation import validate_document_name_length
from lhdn_payroll_integration.utils.tin_validator import validate_tin_with_lhdn

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
            try:
                now = frappe.utils.now_datetime()
                time_remaining = (expires_at - now).total_seconds()
                if time_remaining > 300:  # more than 5 minutes remaining
                    return company.custom_bearer_token
                # Less than 5 min remaining — fall through to refresh
            except (TypeError, AttributeError):
                # Cannot compute remaining time — trust the cached token
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


def _send_failure_notification(doctype, docname, employee_name, error_msg, company):
    """Send email notification on LHDN submission failure.

    Sends to the address in custom_lhdn_failure_email on Company (if set),
    or falls back to all users with the HR Manager role.
    Errors are swallowed so notification failure never blocks the main flow.

    Args:
        doctype: The Frappe doctype (e.g. 'Salary Slip').
        docname: The document name.
        employee_name: Employee full name for the email body.
        error_msg: The error log text (first 500 chars will be included).
        company: Company name used to look up custom_lhdn_failure_email.
    """
    try:
        doc_url = frappe.utils.get_url(f"/app/{doctype.lower().replace(' ', '-')}/{docname}")
        subject = f"[LHDN] Submission Failed: {docname}"
        body = (
            f"<p>Document <strong>{docname}</strong> ({employee_name}) was rejected by LHDN.</p>"
            f"<p><strong>Error (first 500 chars):</strong></p>"
            f"<pre>{(error_msg or '')[:500]}</pre>"
            f"<p><a href='{doc_url}'>Open {docname}</a></p>"
        )

        # Determine recipients
        recipients = []
        if company:
            failure_email = frappe.db.get_value(
                "Company", company, "custom_lhdn_failure_email"
            )
            if failure_email:
                recipients = [failure_email]

        if not recipients:
            hr_manager_users = frappe.db.sql(
                """
                SELECT DISTINCT u.email
                FROM `tabUser` u
                JOIN `tabHas Role` r ON r.parent = u.name
                WHERE r.role = 'HR Manager'
                  AND u.enabled = 1
                  AND u.email IS NOT NULL
                  AND u.email != ''
                """,
                as_dict=True,
            )
            recipients = [row["email"] for row in hr_manager_users]

        if recipients:
            frappe.sendmail(recipients=recipients, subject=subject, message=body)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "LHDN failure notification error")


def _write_response_to_doc(doctype, docname, response):
    """Parse LHDN 202 response and update the Frappe document.

    On acceptedDocuments: sets custom_lhdn_status='Submitted' and stores UUID.
    On rejectedDocuments: sets custom_lhdn_status='Invalid', logs error,
    and sends failure email to HR Manager (US-022).

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

        # US-022: notify HR Manager of failure
        try:
            doc_fields = frappe.db.get_value(
                doctype,
                docname,
                ["employee_name", "company"],
                as_dict=True,
            ) or {}
        except Exception:
            doc_fields = {}
        _send_failure_notification(
            doctype,
            docname,
            doc_fields.get("employee_name", ""),
            error_msg,
            doc_fields.get("company", ""),
        )


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


@frappe.whitelist()
def bulk_enqueue_lhdn_submission(docnames, doctype="Salary Slip"):
    """Enqueue multiple documents for LHDN submission in bulk.

    Sets each document's custom_lhdn_status to 'Pending' and enqueues
    the appropriate processing method. Skips documents that are already
    Pending, Submitted, or Exempt. Returns a summary of success/failure counts.

    Args:
        docnames: JSON string or list of document names.
        doctype: 'Salary Slip' or 'Expense Claim'.

    Returns:
        dict with keys:
            - success (int): Number of documents enqueued.
            - failed (int): Number of documents that could not be enqueued.
            - errors (list): Error messages for failed documents.
    """
    if "HR Manager" not in frappe.get_roles() and "System Manager" not in frappe.get_roles():
        raise frappe.PermissionError(
            "Only HR Manager or System Manager can bulk submit to LHDN."
        )

    if isinstance(docnames, str):
        docnames = frappe.parse_json(docnames)

    if doctype == "Salary Slip":
        process_method = "lhdn_payroll_integration.services.submission_service.process_salary_slip"
    else:
        process_method = "lhdn_payroll_integration.services.submission_service.process_expense_claim"

    skip_statuses = {"Pending", "Submitted", "Exempt"}
    success = 0
    failed = 0
    errors = []

    for docname in docnames:
        try:
            current_status = frappe.db.get_value(doctype, docname, "custom_lhdn_status")
            if current_status in skip_statuses:
                errors.append(f"{docname}: already {current_status}")
                failed += 1
                continue

            frappe.db.set_value(doctype, docname, "custom_lhdn_status", "Pending")
            frappe.enqueue(
                method=process_method,
                docname=docname,
                queue="short",
                timeout=300,
                enqueue_after_commit=True,
            )
            success += 1
        except Exception as e:
            errors.append(f"{docname}: {str(e)}")
            failed += 1

    return {"success": success, "failed": failed, "errors": errors}


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

    # US-021: Validate employee TIN with LHDN API before enqueuing
    employee = frappe.get_doc("Employee", doc.employee)
    tin = getattr(employee, "custom_lhdn_tin", "") or ""
    id_type = getattr(employee, "custom_id_type", "") or ""
    id_value = getattr(employee, "custom_id_value", "") or ""

    if tin and id_type and id_value:
        is_valid, error_msg = validate_tin_with_lhdn(
            doc.company, tin, id_type, id_value
        )
        if not is_valid:
            frappe.db.set_value("Salary Slip", doc.name, "custom_lhdn_status", "Invalid")
            frappe.db.set_value("Salary Slip", doc.name, "custom_error_log", error_msg)
            return

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


def process_consolidated_batch(batch_docnames, target_month):
    """Submit a batch of Salary Slip documents as ONE consolidated XML to LHDN.

    Builds a single consolidated UBL XML for all batch_docnames, makes one HTTP
    POST, and logs the returned UUID for audit trail. This replaces the
    per-document loop for low-value salary slips during monthly consolidation.

    Note: Expense Claims are not supported here — build_consolidated_xml is
    Salary Slip-only.

    Args:
        batch_docnames: List of Salary Slip document names to consolidate.
        target_month: Month string in 'YYYY-MM' format (e.g. '2026-01').

    Returns:
        str: UUID returned by LHDN on success, empty string on failure.
    """
    if not batch_docnames:
        return ""

    xml_string = build_consolidated_xml(batch_docnames, target_month)
    code_number = f"CONSOL-{target_month}"
    submission_data = prepare_submission_wrapper(xml_string, code_number)

    first_doc = frappe.get_doc("Salary Slip", batch_docnames[0])
    token = get_access_token(first_doc.company)
    company = frappe.get_doc("Company", first_doc.company)
    url = _get_submission_url(company)

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    try:
        response = requests.post(url, json=submission_data, headers=headers)

        if response.status_code == 401:
            token = get_access_token(first_doc.company)
            headers["Authorization"] = f"Bearer {token}"
            response = requests.post(url, json=submission_data, headers=headers)

        data = response.json()
        accepted = data.get("acceptedDocuments", [])
        uuid = accepted[0].get("uuid", "") if accepted else ""

        frappe.log_error(
            message=(
                f"LHDN consolidated batch submitted: {len(batch_docnames)} Salary Slip(s) "
                f"for {target_month}. UUID: {uuid}. "
                f"Docs: {', '.join(batch_docnames)}"
            ),
            title="LHDN Consolidation Log",
        )
        return uuid

    except Exception as e:
        frappe.log_error(
            message=(
                f"LHDN consolidated batch submission failed for {target_month}: {e}. "
                f"Docs: {', '.join(batch_docnames)}"
            ),
            title="LHDN Consolidation Failed",
        )
        return ""


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
