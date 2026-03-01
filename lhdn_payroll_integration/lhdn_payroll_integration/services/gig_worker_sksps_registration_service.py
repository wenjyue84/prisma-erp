"""Gig Workers Act 2025 — PERKESO SKSPS Auto-Registration Service (US-181).

Implements auto-registration of gig workers under PERKESO's Self-Employment
Social Security Scheme (SKSPS) via the ASSIST portal API, as required by the
Gig Workers Act 2025 (Act 872) and Self-Employment Social Security Act 2017
(Act 789).

Key rules:
- Platform providers must register each gig worker under SKSPS before any
  SKSPS/SEIA contribution can be deducted.
- Registration is via PERKESO ASSIST portal (assist.perkeso.gov.my).
- Registration status must be tracked: Pending → Active or Rejected.
- SKSPS contribution deduction is blocked until status is "Active".
- Failed registrations generate an HR task with error details.
- Bulk registration batch job available for onboarding waves.

Registration statuses:
  Pending   — API call submitted, awaiting PERKESO response
  Active    — Registration confirmed by PERKESO
  Rejected  — Registration rejected (error code stored)
  Not Registered — No registration attempt made yet
"""

import frappe
from frappe.utils import getdate, nowdate, now_datetime

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Registration status values
STATUS_NOT_REGISTERED = "Not Registered"
STATUS_PENDING = "Pending"
STATUS_ACTIVE = "Active"
STATUS_REJECTED = "Rejected"

#: PERKESO ASSIST API base URLs
ASSIST_SANDBOX_URL = "https://sandbox-assist.perkeso.gov.my/api/v1"
ASSIST_PRODUCTION_URL = "https://assist.perkeso.gov.my/api/v1"

#: SKSPS registration endpoint path
SKSPS_REGISTRATION_ENDPOINT = "/sksps/registration"

#: Bulk registration batch size limit
BULK_BATCH_SIZE = 50

#: PERKESO error codes with resolution steps
PERKESO_ERROR_CODES = {
    "ERR_DUPLICATE": "Worker already registered under SKSPS. Verify with PERKESO reference number.",
    "ERR_INVALID_IC": "Invalid IC/passport number. Verify the worker's identity document.",
    "ERR_INVALID_DOB": "Date of birth mismatch with PERKESO records. Confirm DOB with worker.",
    "ERR_UNDERAGE": "Worker is below minimum age for SKSPS. Minimum age is 15 years.",
    "ERR_OVERAGE": "Worker exceeds maximum age for SKSPS. Maximum age is 65 years.",
    "ERR_MISSING_FIELD": "Required field missing in registration payload. Check all mandatory fields.",
    "ERR_PLATFORM_NOT_REGISTERED": "Platform provider not registered with PERKESO. Complete employer registration first.",
    "ERR_SERVER": "PERKESO server error. Retry registration after 30 minutes.",
    "ERR_TIMEOUT": "Request timed out. Check network connectivity and retry.",
    "ERR_UNAUTHORIZED": "Invalid PERKESO API credentials. Verify client_id and client_secret.",
}

#: Required fields for SKSPS registration payload
REQUIRED_REGISTRATION_FIELDS = [
    "ic_passport_number",
    "full_name",
    "date_of_birth",
    "gender",
    "nationality",
    "address",
    "contact_number",
    "platform_provider_code",
]

#: Employment type for gig workers
GIG_WORKER_EMPLOYMENT_TYPE = "Gig / Platform Worker"

# Minimum / maximum age for SKSPS eligibility
SKSPS_MIN_AGE = 15
SKSPS_MAX_AGE = 65


# ---------------------------------------------------------------------------
# Registration payload builder
# ---------------------------------------------------------------------------

def build_registration_payload(employee_doc) -> dict:
    """Build the PERKESO ASSIST SKSPS registration payload from an Employee record.

    Args:
        employee_doc: Frappe Employee document (dict-like).

    Returns:
        dict with SKSPS registration fields.

    Raises:
        ValueError: If required fields are missing from the employee record.
    """
    ic_number = (
        employee_doc.get("custom_icpassport_number")
        or employee_doc.get("custom_customer_registrationicpassport_number")
        or ""
    )
    full_name = employee_doc.get("employee_name") or ""
    dob = employee_doc.get("date_of_birth") or ""
    gender = employee_doc.get("gender") or ""
    nationality = employee_doc.get("custom_nationality") or employee_doc.get("nationality") or ""
    address = _build_address_string(employee_doc)
    contact = employee_doc.get("cell_phone") or employee_doc.get("custom_contact_number") or ""
    company = employee_doc.get("company") or ""

    # Get platform provider code from Company settings
    platform_code = _get_platform_provider_code(company)

    payload = {
        "ic_passport_number": ic_number.strip(),
        "full_name": full_name.strip(),
        "date_of_birth": str(dob) if dob else "",
        "gender": gender.strip(),
        "nationality": nationality.strip(),
        "address": address.strip(),
        "contact_number": contact.strip(),
        "platform_provider_code": platform_code,
        "employee_id": employee_doc.get("name") or "",
        "company": company,
    }

    return payload


def validate_registration_payload(payload: dict) -> dict:
    """Validate that the registration payload contains all required fields.

    Args:
        payload: Dict with registration fields.

    Returns:
        dict with keys:
            ``valid``   — True if all required fields are present and non-empty
            ``missing`` — list of missing/empty field names
    """
    missing = []
    for field in REQUIRED_REGISTRATION_FIELDS:
        value = payload.get(field)
        if not value or not str(value).strip():
            missing.append(field)

    return {
        "valid": len(missing) == 0,
        "missing": missing,
    }


def _build_address_string(employee_doc) -> str:
    """Build a single-line address from Employee address fields."""
    parts = []
    for field in ["custom_address_line_1", "custom_address_line_2",
                   "custom_city", "custom_state", "custom_postcode"]:
        val = employee_doc.get(field)
        if val and str(val).strip():
            parts.append(str(val).strip())

    if parts:
        return ", ".join(parts)

    # Fallback to current_address field
    return (employee_doc.get("current_address") or "").strip()


def _get_platform_provider_code(company: str) -> str:
    """Get the PERKESO platform provider code from Company settings.

    Args:
        company: Company name.

    Returns:
        Platform provider code string, or empty string if not configured.
    """
    if not company:
        return ""
    try:
        code = frappe.db.get_value("Company", company, "custom_perkeso_platform_code")
        return str(code).strip() if code else ""
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Registration status management
# ---------------------------------------------------------------------------

def get_registration_status(employee_name: str) -> dict:
    """Get the current SKSPS registration status for a gig worker.

    Reads custom fields on the Employee record:
    - custom_sksps_registration_status
    - custom_sksps_reference_number
    - custom_sksps_registration_date

    Args:
        employee_name: Employee DocType name/ID.

    Returns:
        dict with keys:
            ``status``           — One of STATUS_NOT_REGISTERED/PENDING/ACTIVE/REJECTED
            ``reference_number`` — PERKESO SKSPS reference number (if any)
            ``registration_date``— Date of registration (if any)
            ``error_code``       — PERKESO error code (if rejected)
            ``error_message``    — Resolution steps (if rejected)
    """
    try:
        emp = frappe.db.get_value(
            "Employee",
            employee_name,
            [
                "custom_sksps_registration_status",
                "custom_sksps_reference_number",
                "custom_sksps_registration_date",
                "custom_sksps_error_code",
            ],
            as_dict=True,
        )
    except Exception:
        return {
            "status": STATUS_NOT_REGISTERED,
            "reference_number": "",
            "registration_date": None,
            "error_code": "",
            "error_message": "",
        }

    if not emp:
        return {
            "status": STATUS_NOT_REGISTERED,
            "reference_number": "",
            "registration_date": None,
            "error_code": "",
            "error_message": "",
        }

    status = emp.get("custom_sksps_registration_status") or STATUS_NOT_REGISTERED
    error_code = emp.get("custom_sksps_error_code") or ""
    error_message = PERKESO_ERROR_CODES.get(error_code, "")

    return {
        "status": status,
        "reference_number": emp.get("custom_sksps_reference_number") or "",
        "registration_date": emp.get("custom_sksps_registration_date"),
        "error_code": error_code,
        "error_message": error_message,
    }


def update_registration_status(
    employee_name: str,
    status: str,
    reference_number: str = "",
    error_code: str = "",
) -> None:
    """Update the SKSPS registration status on the Employee record.

    Args:
        employee_name: Employee name/ID.
        status: New status (STATUS_PENDING, STATUS_ACTIVE, STATUS_REJECTED).
        reference_number: PERKESO SKSPS reference number (for Active status).
        error_code: PERKESO error code (for Rejected status).
    """
    updates = {
        "custom_sksps_registration_status": status,
    }

    if reference_number:
        updates["custom_sksps_reference_number"] = reference_number

    if status == STATUS_ACTIVE and not updates.get("custom_sksps_registration_date"):
        updates["custom_sksps_registration_date"] = nowdate()

    if error_code:
        updates["custom_sksps_error_code"] = error_code

    frappe.db.set_value("Employee", employee_name, updates)


# ---------------------------------------------------------------------------
# SKSPS deduction eligibility
# ---------------------------------------------------------------------------

def is_sksps_deduction_allowed(employee_name: str) -> dict:
    """Check if SKSPS/SEIA contribution deduction is allowed for a gig worker.

    Deduction is blocked unless the worker's SKSPS registration status is Active.

    Args:
        employee_name: Employee name/ID.

    Returns:
        dict with keys:
            ``allowed`` — True if SKSPS deduction can proceed
            ``reason``  — Explanation if blocked
            ``status``  — Current registration status
    """
    reg = get_registration_status(employee_name)
    status = reg["status"]

    if status == STATUS_ACTIVE:
        return {
            "allowed": True,
            "reason": "",
            "status": status,
        }

    reasons = {
        STATUS_NOT_REGISTERED: "Gig worker is not registered under PERKESO SKSPS. Registration required before deduction.",
        STATUS_PENDING: "SKSPS registration is pending PERKESO approval. Deduction blocked until Active.",
        STATUS_REJECTED: f"SKSPS registration was rejected by PERKESO (error: {reg['error_code']}). Re-registration required.",
    }

    return {
        "allowed": False,
        "reason": reasons.get(status, f"SKSPS registration status is '{status}'. Must be Active for deduction."),
        "status": status,
    }


# ---------------------------------------------------------------------------
# PERKESO ASSIST API interaction
# ---------------------------------------------------------------------------

def submit_sksps_registration(employee_name: str, use_sandbox: bool = True) -> dict:
    """Submit SKSPS registration for a gig worker to PERKESO ASSIST API.

    This function:
    1. Builds the registration payload from the Employee record
    2. Validates required fields
    3. Calls the PERKESO ASSIST API
    4. Updates the Employee registration status based on the response
    5. Creates an HR task if registration fails

    Args:
        employee_name: Employee name/ID.
        use_sandbox: If True, use sandbox API URL; else production.

    Returns:
        dict with keys:
            ``success``          — True if registration was accepted
            ``status``           — New registration status
            ``reference_number`` — PERKESO reference (if successful)
            ``error_code``       — Error code (if failed)
            ``error_message``    — Resolution steps (if failed)
            ``payload``          — The submitted payload
    """
    # Load employee
    try:
        employee_doc = frappe.get_doc("Employee", employee_name)
    except Exception:
        return {
            "success": False,
            "status": STATUS_NOT_REGISTERED,
            "reference_number": "",
            "error_code": "ERR_MISSING_FIELD",
            "error_message": f"Employee {employee_name} not found",
            "payload": {},
        }

    # Build and validate payload
    payload = build_registration_payload(employee_doc)
    validation = validate_registration_payload(payload)

    if not validation["valid"]:
        missing_str = ", ".join(validation["missing"])
        _create_failed_registration_task(
            employee_name,
            employee_doc.get("employee_name", ""),
            "ERR_MISSING_FIELD",
            f"Missing required fields for SKSPS registration: {missing_str}",
            employee_doc.get("company", ""),
        )
        return {
            "success": False,
            "status": STATUS_NOT_REGISTERED,
            "reference_number": "",
            "error_code": "ERR_MISSING_FIELD",
            "error_message": f"Missing required fields: {missing_str}",
            "payload": payload,
        }

    # Set status to Pending before API call
    update_registration_status(employee_name, STATUS_PENDING)

    # Call PERKESO ASSIST API
    api_result = _call_perkeso_assist_api(payload, use_sandbox)

    if api_result["success"]:
        update_registration_status(
            employee_name,
            STATUS_ACTIVE,
            reference_number=api_result.get("reference_number", ""),
        )
        return {
            "success": True,
            "status": STATUS_ACTIVE,
            "reference_number": api_result.get("reference_number", ""),
            "error_code": "",
            "error_message": "",
            "payload": payload,
        }
    else:
        error_code = api_result.get("error_code", "ERR_SERVER")
        error_message = PERKESO_ERROR_CODES.get(error_code, api_result.get("error_message", "Unknown error"))

        update_registration_status(
            employee_name,
            STATUS_REJECTED,
            error_code=error_code,
        )

        _create_failed_registration_task(
            employee_name,
            employee_doc.get("employee_name", ""),
            error_code,
            error_message,
            employee_doc.get("company", ""),
        )

        return {
            "success": False,
            "status": STATUS_REJECTED,
            "reference_number": "",
            "error_code": error_code,
            "error_message": error_message,
            "payload": payload,
        }


def _call_perkeso_assist_api(payload: dict, use_sandbox: bool = True) -> dict:
    """Call the PERKESO ASSIST SKSPS registration API.

    In production this makes an HTTP POST to the ASSIST portal.
    Currently structured for mock/sandbox testing.

    Args:
        payload: Registration payload dict.
        use_sandbox: Whether to use sandbox URL.

    Returns:
        dict with:
            ``success``          — True/False
            ``reference_number`` — PERKESO ref if successful
            ``error_code``       — Error code if failed
            ``error_message``    — Error description if failed
    """
    base_url = ASSIST_SANDBOX_URL if use_sandbox else ASSIST_PRODUCTION_URL
    url = f"{base_url}{SKSPS_REGISTRATION_ENDPOINT}"

    try:
        import requests
        response = requests.post(
            url,
            json=payload,
            timeout=30,
            headers={"Content-Type": "application/json"},
        )

        if response.status_code == 200:
            data = response.json()
            return {
                "success": True,
                "reference_number": data.get("reference_number", ""),
                "error_code": "",
                "error_message": "",
            }
        elif response.status_code == 409:
            data = response.json()
            return {
                "success": False,
                "reference_number": "",
                "error_code": "ERR_DUPLICATE",
                "error_message": data.get("message", "Duplicate registration"),
            }
        else:
            data = {}
            try:
                data = response.json()
            except Exception:
                pass
            return {
                "success": False,
                "reference_number": "",
                "error_code": data.get("error_code", "ERR_SERVER"),
                "error_message": data.get("message", f"HTTP {response.status_code}"),
            }

    except Exception as e:
        return {
            "success": False,
            "reference_number": "",
            "error_code": "ERR_TIMEOUT",
            "error_message": str(e),
        }


# ---------------------------------------------------------------------------
# HR task creation for failed registrations
# ---------------------------------------------------------------------------

def _create_failed_registration_task(
    employee_name: str,
    employee_display_name: str,
    error_code: str,
    error_message: str,
    company: str = "",
) -> str | None:
    """Create an HR task (ToDo) for a failed SKSPS registration.

    Args:
        employee_name: Employee name/ID.
        employee_display_name: Human-readable employee name.
        error_code: PERKESO error code.
        error_message: Resolution steps.
        company: Company name for assignment routing.

    Returns:
        ToDo document name if created, else None.
    """
    resolution = PERKESO_ERROR_CODES.get(error_code, error_message)

    description = (
        f"<b>PERKESO SKSPS Registration Failed</b><br><br>"
        f"<b>Employee:</b> {employee_display_name} ({employee_name})<br>"
        f"<b>Error Code:</b> {error_code}<br>"
        f"<b>Error:</b> {error_message}<br>"
        f"<b>Resolution:</b> {resolution}<br><br>"
        f"Please resolve the issue and retry SKSPS registration for this gig worker."
    )

    try:
        todo = frappe.get_doc({
            "doctype": "ToDo",
            "description": description,
            "reference_type": "Employee",
            "reference_name": employee_name,
            "priority": "High",
            "status": "Open",
            "allocated_to": _get_hr_manager(company),
        })
        todo.insert(ignore_permissions=True)
        frappe.db.commit()
        return todo.name
    except Exception:
        return None


def _get_hr_manager(company: str = "") -> str:
    """Get the HR Manager email for task assignment.

    Falls back to Administrator if no HR Manager found.
    """
    try:
        hr_managers = frappe.get_all(
            "Has Role",
            filters={"role": "HR Manager", "parenttype": "User"},
            fields=["parent"],
            limit_page_length=1,
        )
        if hr_managers:
            return hr_managers[0]["parent"]
    except Exception:
        pass
    return "Administrator"


# ---------------------------------------------------------------------------
# Bulk registration
# ---------------------------------------------------------------------------

def bulk_register_gig_workers(
    company: str,
    employee_list: list | None = None,
    use_sandbox: bool = True,
) -> dict:
    """Bulk-register multiple gig workers under PERKESO SKSPS.

    Processes workers in batches of BULK_BATCH_SIZE. Skips workers already
    registered (status Active or Pending).

    Args:
        company: Company name to filter employees.
        employee_list: Optional explicit list of employee names. If None,
            auto-discovers all unregistered gig workers in the company.
        use_sandbox: Whether to use sandbox API URL.

    Returns:
        dict with keys:
            ``total``     — Total workers processed
            ``success``   — Count of successful registrations
            ``failed``    — Count of failed registrations
            ``skipped``   — Count of already-registered workers (skipped)
            ``results``   — List of per-worker result dicts
    """
    if employee_list is None:
        employee_list = _get_unregistered_gig_workers(company)

    results = []
    success_count = 0
    failed_count = 0
    skipped_count = 0

    for emp_name in employee_list:
        # Check current status — skip if already Active or Pending
        current = get_registration_status(emp_name)
        if current["status"] in (STATUS_ACTIVE, STATUS_PENDING):
            skipped_count += 1
            results.append({
                "employee": emp_name,
                "action": "skipped",
                "status": current["status"],
                "reason": f"Already {current['status']}",
                "reference_number": current.get("reference_number", ""),
            })
            continue

        # Submit registration
        reg_result = submit_sksps_registration(emp_name, use_sandbox=use_sandbox)

        if reg_result["success"]:
            success_count += 1
            results.append({
                "employee": emp_name,
                "action": "registered",
                "status": STATUS_ACTIVE,
                "reason": "",
                "reference_number": reg_result.get("reference_number", ""),
            })
        else:
            failed_count += 1
            results.append({
                "employee": emp_name,
                "action": "failed",
                "status": STATUS_REJECTED,
                "reason": reg_result.get("error_message", ""),
                "reference_number": "",
                "error_code": reg_result.get("error_code", ""),
            })

    return {
        "total": len(employee_list),
        "success": success_count,
        "failed": failed_count,
        "skipped": skipped_count,
        "results": results,
    }


def _get_unregistered_gig_workers(company: str) -> list:
    """Get list of gig workers in a company that are not yet SKSPS-registered.

    Args:
        company: Company name.

    Returns:
        List of Employee names.
    """
    try:
        workers = frappe.get_all(
            "Employee",
            filters={
                "company": company,
                "custom_employment_type": GIG_WORKER_EMPLOYMENT_TYPE,
                "custom_is_seia_worker": 1,
                "status": "Active",
                "custom_sksps_registration_status": ["in", [STATUS_NOT_REGISTERED, "", None]],
            },
            pluck="name",
        )
        return workers
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Age eligibility check
# ---------------------------------------------------------------------------

def check_sksps_age_eligibility(date_of_birth, as_of_date=None) -> dict:
    """Check if a gig worker meets the SKSPS age requirement (15–65 years).

    Args:
        date_of_birth: Worker's date of birth.
        as_of_date: Reference date; defaults to today.

    Returns:
        dict with keys:
            ``eligible`` — True if age is between 15 and 65 inclusive
            ``age``      — Calculated age in years
            ``reason``   — Explanation if ineligible
    """
    if not date_of_birth:
        return {
            "eligible": False,
            "age": 0,
            "reason": "Date of birth not provided",
        }

    check_date = getdate(as_of_date or nowdate())
    dob = getdate(date_of_birth)

    age = check_date.year - dob.year
    if (check_date.month, check_date.day) < (dob.month, dob.day):
        age -= 1

    if age < SKSPS_MIN_AGE:
        return {
            "eligible": False,
            "age": age,
            "reason": f"Worker is {age} years old. Minimum age for SKSPS is {SKSPS_MIN_AGE}.",
        }

    if age > SKSPS_MAX_AGE:
        return {
            "eligible": False,
            "age": age,
            "reason": f"Worker is {age} years old. Maximum age for SKSPS is {SKSPS_MAX_AGE}.",
        }

    return {
        "eligible": True,
        "age": age,
        "reason": "",
    }
