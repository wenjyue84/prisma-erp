"""Validation utilities for LHDN payroll integration."""
import frappe


def validate_document_name_length(doc_name, max_length=50):
    """Validate that document name does not exceed max_length.

    Args:
        doc_name: The document name string to validate.
        max_length: Maximum allowed length (default 50).

    Raises:
        frappe.ValidationError: If name exceeds max_length.
    """
    if len(doc_name) > max_length:
        frappe.throw(
            f"Document name '{doc_name}' exceeds maximum length of {max_length} characters.",
            frappe.ValidationError
        )
