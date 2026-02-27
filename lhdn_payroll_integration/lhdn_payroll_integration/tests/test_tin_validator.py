"""Tests for TIN validation API integration (US-021).

Tests validate_tin_with_lhdn() and the enqueue_salary_slip_submission()
TIN gate using mocked HTTP. Confirms:
  - Valid TIN (HTTP 200) → submission proceeds to enqueue
  - Invalid TIN (HTTP 400) → status set to Invalid, no enqueue
  - validate_employee_tin() whitelisted endpoint returns structured result
"""
from unittest.mock import MagicMock, patch, call

import frappe
from frappe.tests.utils import FrappeTestCase


class TestTinValidatorValidTin(FrappeTestCase):
    """validate_tin_with_lhdn returns (True, '') when LHDN API returns 200."""

    @patch("lhdn_payroll_integration.utils.tin_validator.requests.get")
    @patch("lhdn_payroll_integration.utils.tin_validator.frappe.get_doc")
    @patch(
        "lhdn_payroll_integration.utils.tin_validator.get_access_token",
        return_value="tok123",
    )
    def test_valid_tin_returns_true(self, mock_token, mock_get_doc, mock_get):
        """HTTP 200 → (True, '')."""
        from lhdn_payroll_integration.utils.tin_validator import validate_tin_with_lhdn

        company = MagicMock()
        company.custom_integration_type = "Sandbox"
        company.custom_sandbox_url = "https://preprod-api.myinvois.hasil.gov.my"
        mock_get_doc.return_value = company

        resp = MagicMock()
        resp.status_code = 200
        mock_get.return_value = resp

        is_valid, msg = validate_tin_with_lhdn("Test Co", "IG12345678901", "NRIC", "901230101234")
        self.assertTrue(is_valid)
        self.assertEqual(msg, "")

    @patch("lhdn_payroll_integration.utils.tin_validator.requests.get")
    @patch("lhdn_payroll_integration.utils.tin_validator.frappe.get_doc")
    @patch(
        "lhdn_payroll_integration.utils.tin_validator.get_access_token",
        return_value="tok123",
    )
    def test_valid_tin_calls_correct_url(self, mock_token, mock_get_doc, mock_get):
        """URL is built as {base_url}/api/v1.0/taxpayer/validate/{tin}/{idType}/{idValue}."""
        from lhdn_payroll_integration.utils.tin_validator import validate_tin_with_lhdn

        company = MagicMock()
        company.custom_integration_type = "Sandbox"
        company.custom_sandbox_url = "https://preprod-api.myinvois.hasil.gov.my"
        mock_get_doc.return_value = company

        resp = MagicMock()
        resp.status_code = 200
        mock_get.return_value = resp

        validate_tin_with_lhdn("Test Co", "IG12345678901", "NRIC", "901230101234")

        called_url = mock_get.call_args[0][0]
        self.assertIn("/api/v1.0/taxpayer/validate/", called_url)
        self.assertIn("IG12345678901", called_url)
        self.assertIn("NRIC", called_url)
        self.assertIn("901230101234", called_url)

    @patch("lhdn_payroll_integration.utils.tin_validator.requests.get")
    @patch("lhdn_payroll_integration.utils.tin_validator.frappe.get_doc")
    @patch(
        "lhdn_payroll_integration.utils.tin_validator.get_access_token",
        return_value="tok123",
    )
    def test_passport_id_type_maps_to_passport_uppercase(self, mock_token, mock_get_doc, mock_get):
        """Passport id_type is mapped to PASSPORT in the API URL."""
        from lhdn_payroll_integration.utils.tin_validator import validate_tin_with_lhdn

        company = MagicMock()
        company.custom_integration_type = "Sandbox"
        company.custom_sandbox_url = "https://preprod-api.myinvois.hasil.gov.my"
        mock_get_doc.return_value = company

        resp = MagicMock()
        resp.status_code = 200
        mock_get.return_value = resp

        validate_tin_with_lhdn("Test Co", "IG12345678901", "Passport", "AB123456")

        called_url = mock_get.call_args[0][0]
        self.assertIn("PASSPORT", called_url)
        self.assertNotIn("/Passport/", called_url)


class TestTinValidatorInvalidTin(FrappeTestCase):
    """validate_tin_with_lhdn returns (False, error_msg) when LHDN API returns 400."""

    @patch("lhdn_payroll_integration.utils.tin_validator.requests.get")
    @patch("lhdn_payroll_integration.utils.tin_validator.frappe.get_doc")
    @patch(
        "lhdn_payroll_integration.utils.tin_validator.get_access_token",
        return_value="tok123",
    )
    def test_invalid_tin_returns_false(self, mock_token, mock_get_doc, mock_get):
        """HTTP 400 → (False, error_msg with HTTP 400)."""
        from lhdn_payroll_integration.utils.tin_validator import validate_tin_with_lhdn

        company = MagicMock()
        company.custom_integration_type = "Sandbox"
        company.custom_sandbox_url = "https://preprod-api.myinvois.hasil.gov.my"
        mock_get_doc.return_value = company

        resp = MagicMock()
        resp.status_code = 400
        resp.json.return_value = {"message": "TIN not found"}
        mock_get.return_value = resp

        is_valid, msg = validate_tin_with_lhdn("Test Co", "IG99999999999", "NRIC", "999999999999")
        self.assertFalse(is_valid)
        self.assertIn("400", msg)

    @patch("lhdn_payroll_integration.utils.tin_validator.requests.get")
    @patch("lhdn_payroll_integration.utils.tin_validator.frappe.get_doc")
    @patch(
        "lhdn_payroll_integration.utils.tin_validator.get_access_token",
        return_value="tok123",
    )
    def test_invalid_tin_includes_api_message(self, mock_token, mock_get_doc, mock_get):
        """Error message includes the API's error detail."""
        from lhdn_payroll_integration.utils.tin_validator import validate_tin_with_lhdn

        company = MagicMock()
        company.custom_integration_type = "Sandbox"
        company.custom_sandbox_url = "https://preprod-api.myinvois.hasil.gov.my"
        mock_get_doc.return_value = company

        resp = MagicMock()
        resp.status_code = 400
        resp.json.return_value = {"message": "TIN not found in registry"}
        mock_get.return_value = resp

        is_valid, msg = validate_tin_with_lhdn("Test Co", "IG99999999999", "NRIC", "999999999999")
        self.assertIn("TIN not found in registry", msg)


class TestEnqueueSalarySlipTinGate(FrappeTestCase):
    """enqueue_salary_slip_submission() blocks invalid TINs before enqueuing."""

    @patch("lhdn_payroll_integration.services.submission_service.frappe.enqueue")
    @patch("lhdn_payroll_integration.services.submission_service.frappe.db")
    @patch("lhdn_payroll_integration.services.submission_service.frappe.get_doc")
    @patch(
        "lhdn_payroll_integration.services.submission_service.validate_document_name_length",
        return_value="SAL-SLP-00001",
    )
    @patch(
        "lhdn_payroll_integration.services.submission_service.should_submit_to_lhdn",
        return_value=True,
    )
    @patch(
        "lhdn_payroll_integration.utils.tin_validator.validate_tin_with_lhdn",
        return_value=(True, ""),
    )
    def test_valid_tin_proceeds_to_enqueue(
        self,
        mock_validate_tin,
        mock_should_submit,
        mock_validate_name,
        mock_get_doc,
        mock_db,
        mock_enqueue,
    ):
        """When TIN is valid (200), doc is enqueued for processing."""
        from lhdn_payroll_integration.services.submission_service import (
            enqueue_salary_slip_submission,
        )

        employee = MagicMock()
        employee.get.side_effect = lambda k, d=None: {
            "custom_tin": "IG12345678901",
            "custom_id_type": "NRIC",
            "custom_id_value": "901230101234",
        }.get(k, d)
        mock_get_doc.return_value = employee

        doc = MagicMock()
        doc.name = "SAL-SLP-00001"
        doc.employee = "EMP-001"
        doc.company = "Test Company"

        enqueue_salary_slip_submission(doc, "on_submit")

        mock_enqueue.assert_called_once()
        enqueue_kwargs = mock_enqueue.call_args[1]
        self.assertIn("process_salary_slip", enqueue_kwargs.get("method", ""))

    @patch("lhdn_payroll_integration.services.submission_service.frappe.enqueue")
    @patch("lhdn_payroll_integration.services.submission_service.frappe.db")
    @patch("lhdn_payroll_integration.services.submission_service.frappe.get_doc")
    @patch(
        "lhdn_payroll_integration.services.submission_service.validate_document_name_length",
        return_value="SAL-SLP-00001",
    )
    @patch(
        "lhdn_payroll_integration.services.submission_service.should_submit_to_lhdn",
        return_value=True,
    )
    @patch(
        "lhdn_payroll_integration.utils.tin_validator.validate_tin_with_lhdn",
        return_value=(False, "TIN validation failed (HTTP 400): TIN not found"),
    )
    def test_invalid_tin_sets_status_invalid(
        self,
        mock_validate_tin,
        mock_should_submit,
        mock_validate_name,
        mock_get_doc,
        mock_db,
        mock_enqueue,
    ):
        """When TIN is invalid (400), status is set to Invalid and no enqueue happens."""
        from lhdn_payroll_integration.services.submission_service import (
            enqueue_salary_slip_submission,
        )

        employee = MagicMock()
        employee.get.side_effect = lambda k, d=None: {
            "custom_tin": "IG99999999999",
            "custom_id_type": "NRIC",
            "custom_id_value": "999999999999",
        }.get(k, d)
        mock_get_doc.return_value = employee

        doc = MagicMock()
        doc.name = "SAL-SLP-00001"
        doc.employee = "EMP-001"
        doc.company = "Test Company"

        enqueue_salary_slip_submission(doc, "on_submit")

        # enqueue must NOT have been called
        mock_enqueue.assert_not_called()

        # db.set_value must have been called to set status to Invalid
        set_value_calls = [str(c) for c in mock_db.set_value.call_args_list]
        invalid_call = any("Invalid" in c for c in set_value_calls)
        self.assertTrue(invalid_call, f"Expected 'Invalid' in set_value calls: {set_value_calls}")


class TestValidateEmployeeTinWhitelisted(FrappeTestCase):
    """validate_employee_tin() whitelisted endpoint returns {valid, message}."""

    @patch("lhdn_payroll_integration.utils.tin_validator.validate_tin_with_lhdn")
    @patch("lhdn_payroll_integration.utils.tin_validator.frappe.get_doc")
    def test_valid_employee_tin_returns_valid_true(self, mock_get_doc, mock_validate):
        """Valid TIN returns {valid: True, message: ...}."""
        from lhdn_payroll_integration.utils.tin_validator import validate_employee_tin

        employee = MagicMock()
        employee.get.side_effect = lambda k, d=None: {
            "custom_tin": "IG12345678901",
            "custom_id_type": "NRIC",
            "custom_id_value": "901230101234",
            "company": "Test Company",
        }.get(k, d)
        mock_get_doc.return_value = employee

        mock_validate.return_value = (True, "")

        result = validate_employee_tin("EMP-001")
        self.assertTrue(result["valid"])
        self.assertIn("IG12345678901", result["message"])

    @patch("lhdn_payroll_integration.utils.tin_validator.validate_tin_with_lhdn")
    @patch("lhdn_payroll_integration.utils.tin_validator.frappe.get_doc")
    def test_invalid_employee_tin_returns_valid_false(self, mock_get_doc, mock_validate):
        """Invalid TIN returns {valid: False, message: error}."""
        from lhdn_payroll_integration.utils.tin_validator import validate_employee_tin

        employee = MagicMock()
        employee.get.side_effect = lambda k, d=None: {
            "custom_tin": "IG99999999999",
            "custom_id_type": "NRIC",
            "custom_id_value": "999999999999",
            "company": "Test Company",
        }.get(k, d)
        mock_get_doc.return_value = employee

        mock_validate.return_value = (False, "TIN not found")

        result = validate_employee_tin("EMP-001")
        self.assertFalse(result["valid"])
        self.assertIn("TIN not found", result["message"])

    @patch("lhdn_payroll_integration.utils.tin_validator.frappe.get_doc")
    def test_missing_tin_returns_error(self, mock_get_doc):
        """Employee without TIN returns {valid: False, message: ...}."""
        from lhdn_payroll_integration.utils.tin_validator import validate_employee_tin

        employee = MagicMock()
        employee.get.side_effect = lambda k, d=None: {
            "custom_tin": "",
            "custom_id_type": "NRIC",
            "custom_id_value": "901230101234",
            "company": "Test Company",
        }.get(k, d)
        mock_get_doc.return_value = employee

        result = validate_employee_tin("EMP-001")
        self.assertFalse(result["valid"])
        self.assertIn("no TIN", result["message"])
