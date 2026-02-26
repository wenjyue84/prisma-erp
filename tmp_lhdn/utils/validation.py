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
