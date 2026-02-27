"""LHDN TIN validation utility — calls GET /api/v1.0/taxpayer/validate/{tin}/{idType}/{idValue}.

Validates an employee's TIN against the LHDN MyInvois API before submission,
preventing costly 400/422 rejections caused by incorrect TIN values.
"""

import frappe
import requests

# Map Frappe ID type values to LHDN API schemeID codes
_ID_TYPE_MAP = {
    "NRIC": "NRIC",
    "Passport": "PASSPORT",
    "BRN": "BRN",
    "Army ID": "ARMY",
}

TIN_VALIDATION_ENDPOINT = "/api/v1.0/taxpayer/validate"


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


def _get_base_url(company_name):
    """Get the LHDN API base URL from the Company doc.

    Args:
        company_name: The Company document name.

    Returns:
        str: The base URL without trailing slash.
    """
    company = frappe.get_doc("Company", company_name)
    if getattr(company, "custom_integration_type", "") == "Sandbox":
        return (getattr(company, "custom_sandbox_url", "") or "").rstrip("/")
    return (getattr(company, "custom_production_url", "") or "").rstrip("/")


def validate_tin_with_lhdn(company_name, tin, id_type, id_value):
    """Validate a TIN against the LHDN MyInvois taxpayer validation API.

    Calls GET {base_url}/api/v1.0/taxpayer/validate/{tin}/{idType}/{idValue}.
    A 200 response means the TIN is valid; any other response is invalid.

    Args:
        company_name: Company name (for base URL and bearer token).
        tin: The TIN string to validate (e.g. 'IG12345678901').
        id_type: Frappe ID type ('NRIC', 'Passport', 'BRN', 'Army ID').
        id_value: The ID number corresponding to id_type (e.g. '960101014444').

    Returns:
        tuple: (is_valid: bool, error_msg: str or None)
            is_valid=True, error_msg=None when TIN is valid.
            is_valid=False, error_msg=str when TIN is invalid or request fails.
    """
    token = get_access_token(company_name)
    if not token:
        return False, f"Could not obtain LHDN access token for company '{company_name}'"

    lhdn_id_type = _ID_TYPE_MAP.get(id_type, id_type)
    base_url = _get_base_url(company_name)
    if not base_url:
        return False, f"LHDN base URL not configured for company '{company_name}'"

    url = f"{base_url}{TIN_VALIDATION_ENDPOINT}/{tin}/{lhdn_id_type}/{id_value}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code == 200:
            return True, None

        # Parse error message from response body when available
        try:
            err_data = response.json()
            err_msg = (
                err_data.get("message")
                or err_data.get("error")
                or response.text[:300]
            )
        except Exception:
            err_msg = response.text[:300] or f"HTTP {response.status_code}"

        return False, f"LHDN TIN validation failed (HTTP {response.status_code}): {err_msg}"

    except requests.exceptions.RequestException as exc:
        frappe.log_error(
            title="LHDN TIN Validation Request Error",
            message=str(exc),
        )
        return False, f"LHDN TIN validation request error: {exc}"


@frappe.whitelist()
def validate_employee_tin(employee_name):
    """Validate an employee's TIN against the LHDN API. Callable from Employee form button.

    Reads custom_lhdn_tin, custom_id_type, custom_id_value, and company from
    the Employee doc, then calls validate_tin_with_lhdn().

    Args:
        employee_name: The Employee document name.

    Returns:
        dict: {"valid": bool, "message": str}
    """
    employee = frappe.get_doc("Employee", employee_name)

    tin = getattr(employee, "custom_lhdn_tin", "") or ""
    id_type = getattr(employee, "custom_id_type", "") or ""
    id_value = getattr(employee, "custom_id_value", "") or ""
    company = getattr(employee, "company", "") or ""

    if not tin:
        return {"valid": False, "message": "Employee has no LHDN TIN set"}
    if not id_type:
        return {"valid": False, "message": "Employee has no ID Type set"}
    if not id_value:
        return {"valid": False, "message": "Employee has no ID Value set"}
    if not company:
        return {"valid": False, "message": "Employee has no Company set"}

    is_valid, err = validate_tin_with_lhdn(company, tin, id_type, id_value)
    if is_valid:
        return {"valid": True, "message": f"TIN '{tin}' is valid."}
    return {"valid": False, "message": err or "TIN validation failed"}
