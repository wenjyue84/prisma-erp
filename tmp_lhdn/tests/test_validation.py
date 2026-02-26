"""Tests for LHDN validation utilities.

TDD Red Phase — these tests import from lhdn_payroll_integration.utils.validation
which does NOT exist yet. All tests should fail with ImportError.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from lhdn_payroll_integration.utils.validation import (
    validate_tin,
    validate_document_name_length,
    validate_bank_account_length,
)


class TestValidationUtils(FrappeTestCase):
    """Test LHDN input validation and sanitization rules."""

    def test_invalid_tin_nric_raises_error(self):
        """validate_tin with wrong-length NRIC TIN should raise ValidationError."""
        with self.assertRaises(frappe.ValidationError):
            validate_tin("IG12345", "NRIC")

    def test_valid_nric_tin_returns_value(self):
        """validate_tin with valid 13-char NRIC TIN should return the value as-is."""
        result = validate_tin("IG12345678901", "NRIC")
        self.assertEqual(result, "IG12345678901")

    def test_foreign_worker_returns_ei_tin(self):
        """validate_tin for foreign worker should return EI00000000010 regardless of input."""
        result = validate_tin("ANYTHING", "NRIC", is_foreign_worker=True)
        self.assertEqual(result, "EI00000000010")

    def test_long_document_name_truncated_to_50(self):
        """Document name longer than 50 chars should be truncated to 50."""
        long_name = "A" * 80
        result = validate_document_name_length(long_name)
        self.assertEqual(len(result), 50)
        self.assertEqual(result, "A" * 50)

    def test_bank_account_truncated_to_150(self):
        """Bank account longer than 150 chars should be truncated to 150."""
        long_account = "1234567890" * 20  # 200 chars
        result = validate_bank_account_length(long_account)
        self.assertEqual(len(result), 150)
