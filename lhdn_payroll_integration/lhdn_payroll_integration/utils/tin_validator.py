"""LHDN TIN validation API integration (US-021).

Provides synchronous TIN validation against the LHDN MyInvois API before
submission. Called from enqueue_salary_slip_submission() to catch invalid TINs
early — before they reach the async job — and from a whitelisted endpoint
callable from the Employee form button.
"""

import frappe
import requests

TIN_VALIDATE_ENDPOINT = "/api/v1.0/taxpayer/validate/{tin}/{idType}/{idValue}"

# Map from Frappe id_type values to LHDN API schemeID strings
_ID_TYPE_MAP = {
    "NRIC": "NRIC",
    "Passport": "PASSPORT",
    "BRN": "BRN",
    "Army ID": "ARMY",
}


def _get_base_url(company):
    """Get the LHDN base URL from the company config.

    Args:
        company: The Company Frappe document.

    Returns:
        str: The LHDN base URL (sandbox or production).
    """
    if company.custom_integration_type == "Sandbox":
        return (company.custom_sandbox_url or "").rstrip("/")
    return (company.custom_production_url or "").rstrip("/")


def get_access_token(company_name):
    """Thin wrapper around submission_service.get_access_token.

    Defined at module level so tests can patch
    ``lhdn_payroll_integration.utils.tin_validator.get_access_token``.
    Uses a lazy import to avoid a circular dependency between
    tin_validator and submission_service.

    Args:
        company_name: The Company name.

    Returns:
        str: Bearer token, or empty string on failure.
    """
    from lhdn_payroll_integration.services.submission_service import (
        get_access_token as _get,
    )
    return _get(company_name)


def validate_tin_with_lhdn(company_name, tin, id_type, id_value):
    """Call the LHDN TIN validation API and return (is_valid, error_msg).

    Makes a synchronous GET request to:
        GET {base_url}/api/v1.0/taxpayer/validate/{tin}/{idType}/{idValue}

    Uses the company's bearer token for authorization. If the token fetch
    fails or the API returns an unexpected error, logs the error and treats
    the TIN as invalid (fail-safe).

    Args:
        company_name: The Company name to get base URL and bearer token from.
        tin: The TIN string to validate.
        id_type: The Frappe id_type (e.g. 'NRIC', 'Passport', 'BRN').
        id_value: The ID value corresponding to id_type.

    Returns:
        tuple[bool, str]: (is_valid, error_message).
            is_valid is True when the API returns HTTP 200.
            error_message is empty on success, or a description on failure.
    """
    lhdn_id_type = _ID_TYPE_MAP.get(id_type, id_type)

    try:
        company = frappe.get_doc("Company", company_name)
        base_url = _get_base_url(company)
        if not base_url:
            return False, f"LHDN base URL not configured for company '{company_name}'"

        token = get_access_token(company_name)  # module-level wrapper (patchable)
        if not token:
            return False, f"Could not obtain LHDN bearer token for company '{company_name}'"

        url = (
            f"{base_url}/api/v1.0/taxpayer/validate"
            f"/{tin}/{lhdn_id_type}/{id_value}"
        )
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(url, headers=headers, timeout=15)

        if response.status_code == 200:
            return True, ""
        else:
            try:
                data = response.json()
                msg = data.get("message") or data.get("error") or response.text[:300]
            except Exception:
                msg = response.text[:300]
            return False, f"TIN validation failed (HTTP {response.status_code}): {msg}"

    except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
        frappe.log_error(
            title="LHDN TIN Validation Timeout",
            message=str(exc),
        )
        return False, f"TIN validation timed out: {exc}"
    except Exception:
        frappe.log_error(
            title="LHDN TIN Validation Error",
            message=frappe.get_traceback(),
        )
        return False, "TIN validation encountered an unexpected error. See error log."


@frappe.whitelist()
def validate_employee_tin(employee_name):
    """Whitelist-callable TIN validation for the Employee form button.

    Reads the employee's custom_tin, custom_id_type, and custom_id_value fields
    and calls the LHDN validation API. Uses the employee's company to resolve
    the API credentials and base URL.

    Args:
        employee_name: The Employee document name.

    Returns:
        dict: {"valid": bool, "message": str}
    """
    employee = frappe.get_doc("Employee", employee_name)
    tin = employee.get("custom_tin") or ""
    id_type = employee.get("custom_id_type") or ""
    id_value = employee.get("custom_id_value") or ""
    company_name = employee.get("company") or frappe.defaults.get_user_default("company") or ""

    if not tin:
        return {"valid": False, "message": "Employee has no TIN configured."}
    if not id_type:
        return {"valid": False, "message": "Employee has no ID type configured."}
    if not id_value:
        return {"valid": False, "message": "Employee has no ID value configured."}
    if not company_name:
        return {"valid": False, "message": "Could not determine company for this employee."}

    is_valid, error_msg = validate_tin_with_lhdn(company_name, tin, id_type, id_value)
    if is_valid:
        return {"valid": True, "message": f"TIN '{tin}' is valid."}
    return {"valid": False, "message": error_msg}
