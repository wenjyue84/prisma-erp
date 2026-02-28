"""Validation utilities for LHDN payroll integration."""
import re

import frappe


def validate_tin(tin, id_type, is_foreign_worker=False):
    """Validate and return a TIN value for LHDN submission.

    Args:
        tin: The TIN string to validate.
        id_type: The ID type (e.g. 'NRIC', 'Passport', 'BRN', 'Army ID').
        is_foreign_worker: If True, returns the fixed foreign worker TIN.

    Returns:
        str: The validated TIN value.

    Raises:
        frappe.ValidationError: If TIN format is invalid.
    """
    if is_foreign_worker:
        return "EI00000000010"

    # Individual TIN: ^IG\d{11}$ (13 chars total)
    if id_type in ("NRIC", "Passport", "Army ID"):
        pattern = r"^IG\d{11}$"
        if not re.match(pattern, tin):
            frappe.throw(
                f"Invalid individual TIN '{tin}' for ID type '{id_type}'. "
                "Expected format: IG followed by 11 digits.",
                frappe.ValidationError,
            )
    else:
        # Non-individual TIN: ^[A-Z]\d{8,9}0$
        pattern = r"^[A-Z]\d{8,9}0$"
        if not re.match(pattern, tin):
            frappe.throw(
                f"Invalid non-individual TIN '{tin}' for ID type '{id_type}'. "
                "Expected format: letter followed by 8-9 digits ending in 0.",
                frappe.ValidationError,
            )

    return tin


def validate_document_name_length(doc_name, max_length=50):
    """Validate and truncate document name if it exceeds max_length.

    Args:
        doc_name: The document name string.
        max_length: Maximum allowed length (default 50).

    Returns:
        str: The original or truncated name.
    """
    if len(doc_name) > max_length:
        frappe.log_error(
            message=f"Document name '{doc_name}' exceeds {max_length} chars, truncated.",
            title="LHDN Document Name Warning",
        )
        return doc_name[:max_length]
    return doc_name


def validate_bank_account_length(account, max_length=150):
    """Validate and truncate bank account number if it exceeds max_length.

    Args:
        account: The bank account string.
        max_length: Maximum allowed length (default 150).

    Returns:
        str: The original or truncated account number.
    """
    if len(account) > max_length:
        return account[:max_length]
    return account


# ---------------------------------------------------------------------------
# NRIC / ID Value Validation (US-005)
# ---------------------------------------------------------------------------

# Valid Malaysian NRIC state/birth codes
_VALID_STATE_CODES = set(range(1, 17)) | set(range(21, 60))


def validate_nric(value):
    """Validate a Malaysian NRIC (MyKad) number.

    Rules:
    - Exactly 12 digits
    - First 6 digits: valid YYMMDD date (MM 01-12, DD 01-31)
    - Digits 7-8: valid state/birth code (01-16 local, 21-59 foreign born)

    Args:
        value: The NRIC string to validate.

    Raises:
        frappe.ValidationError: If the NRIC format is invalid.
    """
    if not re.fullmatch(r"\d{12}", value or ""):
        frappe.throw(
            f"Invalid NRIC '{value}': must be exactly 12 digits.",
            frappe.ValidationError,
        )

    month = int(value[2:4])
    day = int(value[4:6])
    state_code = int(value[6:8])

    if not (1 <= month <= 12):
        frappe.throw(
            f"Invalid NRIC '{value}': month portion '{value[2:4]}' must be 01-12.",
            frappe.ValidationError,
        )

    if not (1 <= day <= 31):
        frappe.throw(
            f"Invalid NRIC '{value}': day portion '{value[4:6]}' must be 01-31.",
            frappe.ValidationError,
        )

    if state_code not in _VALID_STATE_CODES:
        frappe.throw(
            f"Invalid NRIC '{value}': state/birth code '{value[6:8]}' is not a recognised "
            "Malaysian code (01-16 local, 21-59 foreign born).",
            frappe.ValidationError,
        )


def validate_id_value(id_type, id_value):
    """Dispatch ID value validation based on id_type.

    Args:
        id_type: 'NRIC', 'Passport', or 'BRN'.
        id_value: The ID value string to validate.

    Raises:
        frappe.ValidationError: If the ID value fails its format check.
    """
    if not id_value:
        return

    if id_type == "NRIC":
        validate_nric(id_value)

    elif id_type == "Passport":
        # Passport: 1-20 alphanumeric characters
        if not re.fullmatch(r"[A-Za-z0-9]{1,20}", id_value):
            frappe.throw(
                f"Invalid Passport number '{id_value}': must be 1-20 alphanumeric characters.",
                frappe.ValidationError,
            )

    elif id_type == "BRN":
        # Business Registration Number: exactly 12 numeric digits
        if not re.fullmatch(r"\d{12}", id_value):
            frappe.throw(
                f"Invalid BRN '{id_value}': must be exactly 12 numeric digits.",
                frappe.ValidationError,
            )


def validate_document_for_lhdn(doc, method=None):
    """Multi-doctype validate/before_submit hook for LHDN compliance checks.

    Dispatches to doctype-specific checks:
    - Employee: validates custom_id_type / custom_id_value
    - Salary Slip: checks minimum wage compliance (Minimum Wages Order 2025)
                   and OT rate compliance (Employment Act S.60A(3))

    Hooked via hooks.py:
      Employee    → validate
      Salary Slip → before_submit

    Args:
        doc: The document being validated.
        method: Unused (Frappe doc event signature).
    """
    doctype = doc.get("doctype")

    if doctype == "Salary Slip":
        _validate_salary_slip_minimum_wage(doc)
        _validate_salary_slip_ot(doc)
    else:
        # Default: Employee ID validation
        id_type = doc.get("custom_id_type")
        id_value = doc.get("custom_id_value")
        if id_type and id_value:
            validate_id_value(id_type, id_value)


def _validate_salary_slip_minimum_wage(doc):
    """Check minimum wage compliance on a Salary Slip before submission.

    Issues a frappe.msgprint warning (non-blocking) if salary is below
    RM1,700/month or RM8.17/hour for part-time employees.

    Args:
        doc: Salary Slip document.
    """
    from lhdn_payroll_integration.utils.employment_compliance import check_minimum_wage

    basic_pay = float(doc.get("base_gross_pay") or doc.get("gross_pay") or 0)

    # Try to get employment type from linked Employee
    employment_type = "Full-time"
    contracted_hours = None
    employee_name = doc.get("employee")
    if employee_name:
        emp = frappe.get_cached_doc("Employee", employee_name) if frappe.db.exists("Employee", employee_name) else None
        if emp:
            employment_type = emp.get("custom_employment_type") or "Full-time"
            contracted_hours = emp.get("custom_contracted_hours_per_month")

    result = check_minimum_wage(
        monthly_salary=basic_pay,
        employment_type=employment_type,
        contracted_hours=contracted_hours,
    )

    if not result["compliant"] and result.get("warning"):
        frappe.msgprint(
            msg=result["warning"],
            title="Minimum Wage Warning",
            indicator="orange",
        )


def _validate_salary_slip_ot(doc):
    """Check OT rate compliance for EA-covered employees on a Salary Slip.

    For each earnings component with custom_day_type and custom_ot_hours_claimed set,
    verifies the component amount meets the statutory OT minimum
    (Employment Act S.60A(3): 1.5x Normal, 2.0x Rest Day, 3.0x Public Holiday).

    Issues a non-blocking frappe.msgprint warning per underpaid OT component.
    Only applies to employees earning <= RM4,000/month.

    Args:
        doc: Salary Slip document.
    """
    from lhdn_payroll_integration.utils.employment_compliance import check_overtime_rate

    basic_pay = float(doc.get("base_gross_pay") or doc.get("gross_pay") or 0)

    # Get contracted hours from linked Employee for accurate hourly ORP
    contracted_hours = None
    employee_name = doc.get("employee")
    if employee_name and frappe.db.exists("Employee", employee_name):
        emp = frappe.get_cached_doc("Employee", employee_name)
        contracted_hours = emp.get("custom_contracted_hours_per_month")

    # Iterate through earnings components
    earnings = doc.get("earnings") or []
    for comp in earnings:
        day_type = comp.get("custom_day_type")
        ot_hours = comp.get("custom_ot_hours_claimed")

        # Skip non-OT components (no day_type or hours claimed)
        if not day_type or not ot_hours:
            continue

        amount = comp.get("amount") or comp.get("default_amount") or 0

        result = check_overtime_rate(
            monthly_salary=basic_pay,
            component_amount=amount,
            ot_hours_claimed=ot_hours,
            day_type=day_type,
            contracted_hours_per_month=contracted_hours,
        )

        if not result["compliant"] and result.get("warning"):
            frappe.msgprint(
                msg=result["warning"],
                title="Overtime Rate Warning",
                indicator="orange",
            )
