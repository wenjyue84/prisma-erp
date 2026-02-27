"""LHDN Developer Tools page — whitelisted backend methods.

All methods require System Manager role. Called from lhdn_dev_tools.js via frappe.call.
"""
import time

import frappe
import requests

from lhdn_payroll_integration.services import (
    consolidation_service,
    retention_service,
    status_poller,
)
from lhdn_payroll_integration.services.exemption_filter import (
    IN_SCOPE_WORKER_TYPES,
    should_submit_to_lhdn,
)


def _assert_system_manager():
    """Raise PermissionError if the current user is not a System Manager."""
    if "System Manager" not in frappe.get_roles():
        frappe.throw(
            "LHDN Developer Tools: System Manager role required.",
            frappe.PermissionError,
        )


@frappe.whitelist()
def get_system_status():
    """Return a snapshot of LHDN system health for the first active company.

    Returns:
        dict: {company, company_tin, client_id_set, sandbox_url, integration_type,
               scheduler_last_sync, queue_depth}
    """
    _assert_system_manager()

    company_name = frappe.db.get_value("Company", {"is_group": 0}, "name")
    if not company_name:
        return {"error": "No company found"}

    company = frappe.db.get_value(
        "Company",
        company_name,
        [
            "custom_company_tin_number",
            "custom_client_id",
            "custom_sandbox_url",
            "custom_integration_type",
        ],
        as_dict=True,
    ) or {}

    # Last scheduler heartbeat from Scheduled Job Log
    scheduler_last_sync = frappe.db.get_value(
        "Scheduled Job Log",
        {"status": "Complete"},
        "creation",
        order_by="creation desc",
    )

    # Pending submissions depth
    ss_pending = frappe.db.count("Salary Slip", {"custom_lhdn_status": "Pending"})
    ec_pending = frappe.db.count("Expense Claim", {"custom_lhdn_status": "Pending"})
    queue_depth = (ss_pending or 0) + (ec_pending or 0)

    return {
        "company": company_name,
        "company_tin": company.get("custom_company_tin_number") or "",
        "client_id_set": bool(company.get("custom_client_id")),
        "sandbox_url": company.get("custom_sandbox_url") or "",
        "integration_type": company.get("custom_integration_type") or "",
        "scheduler_last_sync": str(scheduler_last_sync) if scheduler_last_sync else "—",
        "queue_depth": queue_depth,
    }


@frappe.whitelist()
def test_lhdn_connection():
    """POST to the LHDN token endpoint with company credentials and return the result.

    Returns:
        dict: {http_status, elapsed_ms, error_detail}
    """
    _assert_system_manager()

    company_name = frappe.db.get_value("Company", {"is_group": 0}, "name")
    if not company_name:
        return {"http_status": None, "elapsed_ms": None, "error_detail": "No company found"}

    company = frappe.get_doc("Company", company_name)
    base_url = (company.custom_sandbox_url or "").rstrip("/")
    client_id = company.custom_client_id or ""
    client_secret = company.custom_client_secret or ""

    token_url = f"{base_url}/connect/token"
    payload = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": "InvoicingAPI",
    }

    try:
        t0 = time.time()
        response = requests.post(token_url, data=payload, timeout=10)
        elapsed_ms = round((time.time() - t0) * 1000)
        error_detail = ""
        if not response.ok:
            try:
                error_detail = response.json().get("error_description") or response.text[:200]
            except Exception:
                error_detail = response.text[:200]
        return {
            "http_status": response.status_code,
            "elapsed_ms": elapsed_ms,
            "error_detail": error_detail,
        }
    except requests.exceptions.Timeout:
        return {"http_status": None, "elapsed_ms": None, "error_detail": "Request timed out"}
    except Exception as exc:
        return {"http_status": None, "elapsed_ms": None, "error_detail": str(exc)}


@frappe.whitelist()
def run_status_poller():
    """Manually trigger the LHDN status poller for pending documents.

    Returns:
        dict: {success, output}
    """
    _assert_system_manager()
    try:
        status_poller.poll_pending_documents()
        return {"success": True, "output": "Status poller completed successfully."}
    except Exception as exc:
        return {"success": False, "output": str(exc)}


@frappe.whitelist()
def run_monthly_consolidation():
    """Manually trigger the monthly LHDN consolidation service.

    Returns:
        dict: {success, output}
    """
    _assert_system_manager()
    try:
        consolidation_service.run_monthly_consolidation()
        return {"success": True, "output": "Monthly consolidation completed successfully."}
    except Exception as exc:
        return {"success": False, "output": str(exc)}


@frappe.whitelist()
def run_yearly_retention():
    """Manually trigger the yearly LHDN data retention archival.

    Returns:
        dict: {success, output}
    """
    _assert_system_manager()
    try:
        retention_service.run_retention_archival()
        return {"success": True, "output": "Retention archival completed successfully."}
    except Exception as exc:
        return {"success": False, "output": str(exc)}


@frappe.whitelist()
def check_exemption(employee, salary_slip=None):
    """Check whether an employee/salary slip is in scope for LHDN submission.

    Args:
        employee: Employee document name.
        salary_slip: Optional Salary Slip document name. If omitted, a minimal
                     mock document is used to test the worker-type gate only.

    Returns:
        dict: {in_scope, reason}
    """
    _assert_system_manager()

    emp_doc = frappe.get_doc("Employee", employee)
    worker_type = getattr(emp_doc, "custom_worker_type", "") or ""

    if worker_type not in IN_SCOPE_WORKER_TYPES:
        return {
            "in_scope": False,
            "reason": f"Worker type '{worker_type}' is not in-scope ({', '.join(sorted(IN_SCOPE_WORKER_TYPES))} only).",
        }

    if salary_slip:
        doc = frappe.get_doc("Salary Slip", salary_slip)
        result = should_submit_to_lhdn("Salary Slip", doc)
        return {
            "in_scope": result,
            "reason": "Passed all exemption checks." if result else "Exempted by salary slip rules (net_pay <= 0 or self-billed flag not set).",
        }

    return {
        "in_scope": True,
        "reason": f"Worker type '{worker_type}' is in-scope. No salary slip provided — provide one for full check.",
    }


@frappe.whitelist()
def get_recent_submissions(status_filter=None):
    """Return the 20 most recent LHDN submissions across Salary Slip and Expense Claim.

    Args:
        status_filter: Optional LHDN status string to filter by (e.g. 'Invalid').

    Returns:
        list of dicts: {doctype, name, employee, posting_date,
                        custom_lhdn_status, custom_lhdn_uuid, custom_error_log}
    """
    _assert_system_manager()

    filters = {}
    if status_filter:
        filters["custom_lhdn_status"] = status_filter

    fields = ["name", "employee", "posting_date", "custom_lhdn_status", "custom_lhdn_uuid", "custom_error_log"]

    salary_slips = frappe.get_all(
        "Salary Slip",
        filters=filters,
        fields=fields,
        order_by="posting_date desc",
        limit=20,
    )
    for row in salary_slips:
        row["doctype"] = "Salary Slip"

    expense_claims = frappe.get_all(
        "Expense Claim",
        filters=filters,
        fields=["name", "employee", "posting_date", "custom_lhdn_status", "custom_lhdn_uuid", "custom_error_log"],
        order_by="posting_date desc",
        limit=20,
    )
    for row in expense_claims:
        row["doctype"] = "Expense Claim"

    combined = salary_slips + expense_claims
    combined.sort(key=lambda r: r.get("posting_date") or "", reverse=True)
    return combined[:20]


@frappe.whitelist()
def retrieve_lhdn_document(docname, doctype="Salary Slip"):
    """Retrieve the validated XML stored on the LHDN portal for a given document.

    Calls GET {base_url}/api/v1.0/documents/{uuid}/raw using company credentials,
    then stores the response XML in custom_lhdn_raw_document on the document.

    Args:
        docname: Document name (Salary Slip or Expense Claim).
        doctype: DocType of the document. Defaults to 'Salary Slip'.

    Returns:
        dict: {success, raw_xml, error_detail}
    """
    _assert_system_manager()

    # Get the document and its LHDN UUID
    doc = frappe.get_doc(doctype, docname)
    uuid = getattr(doc, "custom_lhdn_uuid", None)
    if not uuid:
        return {
            "success": False,
            "raw_xml": None,
            "error_detail": "Document has no LHDN UUID. Submit to LHDN first.",
        }

    # Get company credentials
    company_name = frappe.db.get_value("Company", {"is_group": 0}, "name")
    if not company_name:
        return {"success": False, "raw_xml": None, "error_detail": "No company found"}

    company = frappe.get_doc("Company", company_name)
    base_url = (company.custom_sandbox_url or "").rstrip("/")
    client_id = company.custom_client_id or ""
    client_secret = company.custom_client_secret or ""

    # Obtain access token
    token_url = f"{base_url}/connect/token"
    token_payload = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": "InvoicingAPI",
    }

    try:
        token_response = requests.post(token_url, data=token_payload, timeout=10)
        if not token_response.ok:
            return {
                "success": False,
                "raw_xml": None,
                "error_detail": f"Token request failed: HTTP {token_response.status_code}",
            }
        access_token = token_response.json().get("access_token", "")

        # Retrieve the raw document XML from LHDN portal
        raw_url = f"{base_url}/api/v1.0/documents/{uuid}/raw"
        headers = {"Authorization": f"Bearer {access_token}"}
        raw_response = requests.get(raw_url, headers=headers, timeout=10)

        if not raw_response.ok:
            return {
                "success": False,
                "raw_xml": None,
                "error_detail": f"LHDN retrieve failed: HTTP {raw_response.status_code}",
            }

        raw_xml = raw_response.text

        # Persist the retrieved XML onto the document field
        frappe.db.set_value(doctype, docname, "custom_lhdn_raw_document", raw_xml)

        return {"success": True, "raw_xml": raw_xml, "error_detail": ""}

    except requests.exceptions.Timeout:
        return {"success": False, "raw_xml": None, "error_detail": "Request timed out"}
    except Exception as exc:
        return {"success": False, "raw_xml": None, "error_detail": str(exc)}
