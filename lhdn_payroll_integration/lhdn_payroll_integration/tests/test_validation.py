"""Tests for LHDN validation utilities."""

import frappe
from frappe.tests.utils import FrappeTestCase
from unittest.mock import MagicMock

from lhdn_payroll_integration.utils.validation import (
    validate_tin,
    validate_document_name_length,
    validate_bank_account_length,
    validate_nric,
    validate_id_value,
    validate_document_for_lhdn,
)


class TestValidationUtils(FrappeTestCase):
    """Test LHDN input validation and sanitization rules."""

    def test_invalid_tin_nric_raises_error(self):
        with self.assertRaises(frappe.ValidationError):
            validate_tin("IG12345", "NRIC")

    def test_valid_nric_tin_returns_value(self):
        result = validate_tin("IG12345678901", "NRIC")
        self.assertEqual(result, "IG12345678901")

    def test_foreign_worker_returns_ei_tin(self):
        result = validate_tin("ANYTHING", "NRIC", is_foreign_worker=True)
        self.assertEqual(result, "EI00000000010")

    def test_long_document_name_truncated_to_50(self):
        long_name = "A" * 80
        result = validate_document_name_length(long_name)
        self.assertEqual(len(result), 50)
        self.assertEqual(result, "A" * 50)

    def test_bank_account_truncated_to_150(self):
        long_account = "1234567890" * 20
        result = validate_bank_account_length(long_account)
        self.assertEqual(len(result), 150)


class TestValidateNric(FrappeTestCase):
    """Tests for validate_nric() - Malaysian NRIC format validation."""

    def test_valid_nric_local_state_johor(self):
        validate_nric("900101010001")

    def test_valid_nric_local_state_max(self):
        validate_nric("850615161234")

    def test_valid_nric_foreign_born_min(self):
        validate_nric("780312211234")

    def test_valid_nric_foreign_born_max(self):
        validate_nric("901231591234")

    def test_nric_less_than_12_digits_raises(self):
        with self.assertRaises(frappe.ValidationError):
            validate_nric("90010101000")

    def test_nric_more_than_12_digits_raises(self):
        with self.assertRaises(frappe.ValidationError):
            validate_nric("9001010100012")

    def test_nric_with_hyphens_raises(self):
        with self.assertRaises(frappe.ValidationError):
            validate_nric("900101-01-0001")

    def test_nric_with_letters_raises(self):
        with self.assertRaises(frappe.ValidationError):
            validate_nric("90010A010001")

    def test_nric_invalid_month_00_raises(self):
        with self.assertRaises(frappe.ValidationError):
            validate_nric("900001010001")

    def test_nric_invalid_month_13_raises(self):
        with self.assertRaises(frappe.ValidationError):
            validate_nric("901301010001")

    def test_nric_invalid_day_00_raises(self):
        with self.assertRaises(frappe.ValidationError):
            validate_nric("900100010001")

    def test_nric_invalid_day_32_raises(self):
        with self.assertRaises(frappe.ValidationError):
            validate_nric("900132010001")

    def test_nric_state_code_00_raises(self):
        with self.assertRaises(frappe.ValidationError):
            validate_nric("900101001234")

    def test_nric_state_code_17_raises(self):
        with self.assertRaises(frappe.ValidationError):
            validate_nric("900101171234")

    def test_nric_state_code_20_raises(self):
        with self.assertRaises(frappe.ValidationError):
            validate_nric("900101201234")

    def test_nric_state_code_60_raises(self):
        with self.assertRaises(frappe.ValidationError):
            validate_nric("900101601234")


class TestValidateIdValue(FrappeTestCase):
    """Tests for validate_id_value() dispatcher."""

    def test_valid_nric_id_value_passes(self):
        validate_id_value("NRIC", "900101011234")

    def test_invalid_nric_id_value_raises(self):
        with self.assertRaises(frappe.ValidationError):
            validate_id_value("NRIC", "12345")

    def test_valid_passport_alphanumeric_passes(self):
        validate_id_value("Passport", "A12345678")

    def test_passport_with_spaces_raises(self):
        with self.assertRaises(frappe.ValidationError):
            validate_id_value("Passport", "A 1234 567")

    def test_passport_too_long_raises(self):
        with self.assertRaises(frappe.ValidationError):
            validate_id_value("Passport", "A" * 21)

    def test_passport_exactly_20_chars_passes(self):
        validate_id_value("Passport", "A" * 20)

    def test_valid_brn_12_digits_passes(self):
        validate_id_value("BRN", "202301012345")

    def test_brn_less_than_12_digits_raises(self):
        with self.assertRaises(frappe.ValidationError):
            validate_id_value("BRN", "20230101234")

    def test_brn_with_letters_raises(self):
        with self.assertRaises(frappe.ValidationError):
            validate_id_value("BRN", "20230101A345")

    def test_brn_13_digits_raises(self):
        with self.assertRaises(frappe.ValidationError):
            validate_id_value("BRN", "2023010123456")

    def test_empty_string_id_value_no_raise(self):
        validate_id_value("NRIC", "")

    def test_none_id_value_no_raise(self):
        validate_id_value("NRIC", None)


class TestValidateDocumentForLhdn(FrappeTestCase):
    """Tests for the Employee validate hook validate_document_for_lhdn()."""

    def _make_employee(self, id_type=None, id_value=None):
        doc = MagicMock()
        doc.get.side_effect = lambda key, default=None: {
            "custom_id_type": id_type,
            "custom_id_value": id_value,
        }.get(key, default)
        return doc

    def test_valid_nric_employee_passes(self):
        doc = self._make_employee("NRIC", "900101011234")
        validate_document_for_lhdn(doc)

    def test_invalid_nric_employee_raises(self):
        doc = self._make_employee("NRIC", "12345")
        with self.assertRaises(frappe.ValidationError):
            validate_document_for_lhdn(doc)

    def test_valid_passport_employee_passes(self):
        doc = self._make_employee("Passport", "A12345678")
        validate_document_for_lhdn(doc)

    def test_invalid_passport_employee_raises(self):
        doc = self._make_employee("Passport", "A" * 21)
        with self.assertRaises(frappe.ValidationError):
            validate_document_for_lhdn(doc)

    def test_valid_brn_employee_passes(self):
        doc = self._make_employee("BRN", "202301012345")
        validate_document_for_lhdn(doc)

    def test_no_id_type_noop(self):
        doc = self._make_employee(id_type=None, id_value=None)
        validate_document_for_lhdn(doc)

    def test_id_type_without_value_noop(self):
        doc = self._make_employee(id_type="NRIC", id_value=None)
        validate_document_for_lhdn(doc)

    def test_method_param_accepted(self):
        doc = self._make_employee("NRIC", "900101011234")
        validate_document_for_lhdn(doc, method="validate")
