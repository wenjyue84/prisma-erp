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
    """Employee validate hook — checks custom_id_type / custom_id_value when set.

    Hooked via hooks.py: Employee → validate.

    Args:
        doc: The Employee document being validated.
        method: Unused (Frappe doc event signature).
    """
    id_type = doc.get("custom_id_type")
    id_value = doc.get("custom_id_value")

    if id_type and id_value:
        validate_id_value(id_type, id_value)
