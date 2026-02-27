"""Tests for US-021: LHDN TIN validation API integration.

Covers:
- validate_tin_with_lhdn(): mocked HTTP for valid and invalid TIN responses
- enqueue_salary_slip_submission(): valid TIN proceeds to enqueue; invalid TIN sets Invalid
- validate_employee_tin(): whitelisted function guard logic
"""
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase


class TestValidateTinWithLhdn(FrappeTestCase):
    """Unit tests for validate_tin_with_lhdn() with mocked HTTP."""

    def _make_company_mock(self, integration_type="Sandbox"):
        company = MagicMock()
        company.custom_integration_type = integration_type
        company.custom_sandbox_url = "https://preprod-api.myinvois.hasil.gov.my"
        company.custom_production_url = "https://api.myinvois.hasil.gov.my"
        return company

    @patch("lhdn_payroll_integration.utils.tin_validator.requests")
    @patch("lhdn_payroll_integration.utils.tin_validator.frappe")
    @patch("lhdn_payroll_integration.utils.tin_validator.get_access_token", return_value="test-token")
    def test_valid_tin_returns_true(self, mock_token, mock_frappe, mock_requests):
        """200 response from LHDN → (True, None)."""
        from lhdn_payroll_integration.utils.tin_validator import validate_tin_with_lhdn

        mock_frappe.get_doc.return_value = self._make_company_mock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_requests.get.return_value = mock_response
        mock_requests.exceptions.RequestException = Exception

        is_valid, err = validate_tin_with_lhdn(
            "Test Co", "IG12345678901", "NRIC", "960101014444"
        )

        self.assertTrue(is_valid)
        self.assertIsNone(err)
        mock_requests.get.assert_called_once()

    @patch("lhdn_payroll_integration.utils.tin_validator.requests")
    @patch("lhdn_payroll_integration.utils.tin_validator.frappe")
    @patch("lhdn_payroll_integration.utils.tin_validator.get_access_token", return_value="test-token")
    def test_invalid_tin_returns_false_with_error_message(self, mock_token, mock_frappe, mock_requests):
        """400 response from LHDN → (False, error_msg containing status code)."""
        from lhdn_payroll_integration.utils.tin_validator import validate_tin_with_lhdn

        mock_frappe.get_doc.return_value = self._make_company_mock()
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {"message": "TIN not found"}
        mock_requests.get.return_value = mock_response
        mock_requests.exceptions.RequestException = Exception

        is_valid, err = validate_tin_with_lhdn(
            "Test Co", "IG99999999999", "NRIC", "960101014444"
        )

        self.assertFalse(is_valid)
        self.assertIn("400", err)

    @patch("lhdn_payroll_integration.utils.tin_validator.requests")
    @patch("lhdn_payroll_integration.utils.tin_validator.frappe")
    @patch("lhdn_payroll_integration.utils.tin_validator.get_access_token", return_value="")
    def test_missing_token_returns_false_no_http_call(self, mock_token, mock_frappe, mock_requests):
        """No access token → (False, error), no HTTP request made."""
        from lhdn_payroll_integration.utils.tin_validator import validate_tin_with_lhdn

        mock_frappe.get_doc.return_value = self._make_company_mock()
        mock_requests.exceptions.RequestException = Exception

        is_valid, err = validate_tin_with_lhdn(
            "Test Co", "IG12345678901", "NRIC", "960101014444"
        )

        self.assertFalse(is_valid)
        self.assertIn("token", err.lower())
        mock_requests.get.assert_not_called()

    @patch("lhdn_payroll_integration.utils.tin_validator.requests")
    @patch("lhdn_payroll_integration.utils.tin_validator.frappe")
    @patch("lhdn_payroll_integration.utils.tin_validator.get_access_token", return_value="test-token")
    def test_id_type_mapping_nric(self, mock_token, mock_frappe, mock_requests):
        """NRIC id_type maps to 'NRIC' in the API URL."""
        from lhdn_payroll_integration.utils.tin_validator import validate_tin_with_lhdn

        mock_frappe.get_doc.return_value = self._make_company_mock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_requests.get.return_value = mock_response
        mock_requests.exceptions.RequestException = Exception

        validate_tin_with_lhdn("Test Co", "IG12345678901", "NRIC", "960101014444")

        call_url = mock_requests.get.call_args[0][0]
        self.assertIn("/NRIC/", call_url)

    @patch("lhdn_payroll_integration.utils.tin_validator.requests")
    @patch("lhdn_payroll_integration.utils.tin_validator.frappe")
    @patch("lhdn_payroll_integration.utils.tin_validator.get_access_token", return_value="test-token")
    def test_id_type_mapping_passport(self, mock_token, mock_frappe, mock_requests):
        """Passport id_type maps to 'PASSPORT' in the API URL."""
        from lhdn_payroll_integration.utils.tin_validator import validate_tin_with_lhdn

        mock_frappe.get_doc.return_value = self._make_company_mock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_requests.get.return_value = mock_response
        mock_requests.exceptions.RequestException = Exception

        validate_tin_with_lhdn("Test Co", "IG12345678901", "Passport", "A12345678")

        call_url = mock_requests.get.call_args[0][0]
        self.assertIn("/PASSPORT/", call_url)

    @patch("lhdn_payroll_integration.utils.tin_validator.requests")
    @patch("lhdn_payroll_integration.utils.tin_validator.frappe")
    @patch("lhdn_payroll_integration.utils.tin_validator.get_access_token", return_value="test-token")
    def test_request_exception_returns_false(self, mock_token, mock_frappe, mock_requests):
        """Network error → (False, error message containing 'request error')."""
        from lhdn_payroll_integration.utils.tin_validator import validate_tin_with_lhdn

        mock_frappe.get_doc.return_value = self._make_company_mock()

        # Make requests.get raise a RequestException
        class FakeRequestException(Exception):
            pass

        mock_requests.exceptions.RequestException = FakeRequestException
        mock_requests.get.side_effect = FakeRequestException("connection timeout")

        is_valid, err = validate_tin_with_lhdn(
            "Test Co", "IG12345678901", "NRIC", "960101014444"
        )

        self.assertFalse(is_valid)
        self.assertIn("request error", err.lower())


class TestEnqueueWithTinValidation(FrappeTestCase):
    """Test enqueue_salary_slip_submission() TIN validation gate (US-021)."""

    def _make_doc(self, name="SAL-001", employee="HR-EMP-001", company="Test Co"):
        doc = MagicMock()
        doc.name = name
        doc.employee = employee
        doc.company = company
        return doc

    def _make_employee(self, tin="IG12345678901", id_type="NRIC", id_value="960101014444"):
        """Create mock employee with explicit string attributes (not MagicMock auto-attributes)."""
        emp = MagicMock()
        emp.custom_lhdn_tin = tin
        emp.custom_id_type = id_type
        emp.custom_id_value = id_value
        emp.custom_requires_self_billed_invoice = 1
        return emp

    @patch("lhdn_payroll_integration.services.submission_service.validate_tin_with_lhdn")
    @patch("lhdn_payroll_integration.services.submission_service.frappe")
    @patch("lhdn_payroll_integration.services.submission_service.should_submit_to_lhdn", return_value=True)
    def test_valid_tin_proceeds_to_enqueue(self, mock_filter, mock_frappe, mock_validate):
        """Valid TIN (True, None) → status set to Pending and enqueue called."""
        from lhdn_payroll_integration.services.submission_service import enqueue_salary_slip_submission

        mock_validate.return_value = (True, None)
        mock_frappe.get_doc.return_value = self._make_employee()

        doc = self._make_doc()
        enqueue_salary_slip_submission(doc, "on_submit")

        mock_frappe.enqueue.assert_called_once()
        mock_frappe.db.set_value.assert_any_call(
            "Salary Slip", doc.name, "custom_lhdn_status", "Pending"
        )

    @patch("lhdn_payroll_integration.services.submission_service.validate_tin_with_lhdn")
    @patch("lhdn_payroll_integration.services.submission_service.frappe")
    @patch("lhdn_payroll_integration.services.submission_service.should_submit_to_lhdn", return_value=True)
    def test_invalid_tin_sets_invalid_status_no_enqueue(self, mock_filter, mock_frappe, mock_validate):
        """Invalid TIN (False, msg) → status set to Invalid, enqueue NOT called."""
        from lhdn_payroll_integration.services.submission_service import enqueue_salary_slip_submission

        mock_validate.return_value = (False, "TIN not found in LHDN")
        mock_frappe.get_doc.return_value = self._make_employee()

        doc = self._make_doc()
        enqueue_salary_slip_submission(doc, "on_submit")

        mock_frappe.enqueue.assert_not_called()
        mock_frappe.db.set_value.assert_any_call(
            "Salary Slip", doc.name, "custom_lhdn_status", "Invalid"
        )
        mock_frappe.db.set_value.assert_any_call(
            "Salary Slip", doc.name, "custom_error_log", "TIN not found in LHDN"
        )

    @patch("lhdn_payroll_integration.services.submission_service.validate_tin_with_lhdn")
    @patch("lhdn_payroll_integration.services.submission_service.frappe")
    @patch("lhdn_payroll_integration.services.submission_service.should_submit_to_lhdn", return_value=True)
    def test_missing_tin_skips_validation_and_enqueues(self, mock_filter, mock_frappe, mock_validate):
        """Employee with no TIN set → validation skipped, still enqueues."""
        from lhdn_payroll_integration.services.submission_service import enqueue_salary_slip_submission

        # Use explicit empty strings so getattr() in submission_service returns ""
        empty_emp = self._make_employee(tin="", id_type="", id_value="")
        mock_frappe.get_doc.return_value = empty_emp

        doc = self._make_doc()
        enqueue_salary_slip_submission(doc, "on_submit")

        mock_validate.assert_not_called()
        mock_frappe.enqueue.assert_called_once()


class TestValidateEmployeeTin(FrappeTestCase):
    """Unit tests for the whitelisted validate_employee_tin() function."""

    @patch("lhdn_payroll_integration.utils.tin_validator.validate_tin_with_lhdn")
    @patch("lhdn_payroll_integration.utils.tin_validator.frappe")
    def test_valid_employee_returns_valid_dict(self, mock_frappe, mock_validate):
        """Employee with TIN fields set and valid API response returns valid=True."""
        from lhdn_payroll_integration.utils.tin_validator import validate_employee_tin

        mock_employee = MagicMock()
        mock_employee.custom_lhdn_tin = "IG12345678901"
        mock_employee.custom_id_type = "NRIC"
        mock_employee.custom_id_value = "960101014444"
        mock_employee.company = "Test Co"
        mock_frappe.get_doc.return_value = mock_employee

        mock_validate.return_value = (True, None)

        result = validate_employee_tin("HR-EMP-001")

        self.assertTrue(result["valid"])
        self.assertIn("valid", result["message"].lower())

    @patch("lhdn_payroll_integration.utils.tin_validator.frappe")
    def test_missing_tin_returns_invalid(self, mock_frappe):
        """Employee with no TIN set returns valid=False."""
        from lhdn_payroll_integration.utils.tin_validator import validate_employee_tin

        mock_employee = MagicMock()
        mock_employee.custom_lhdn_tin = ""
        mock_employee.custom_id_type = "NRIC"
        mock_employee.custom_id_value = "960101014444"
        mock_employee.company = "Test Co"
        mock_frappe.get_doc.return_value = mock_employee

        result = validate_employee_tin("HR-EMP-001")

        self.assertFalse(result["valid"])
        self.assertIn("TIN", result["message"])

    @patch("lhdn_payroll_integration.utils.tin_validator.validate_tin_with_lhdn")
    @patch("lhdn_payroll_integration.utils.tin_validator.frappe")
    def test_invalid_api_response_returns_invalid(self, mock_frappe, mock_validate):
        """API returns (False, err) → validate_employee_tin returns valid=False with message."""
        from lhdn_payroll_integration.utils.tin_validator import validate_employee_tin

        mock_employee = MagicMock()
        mock_employee.custom_lhdn_tin = "IG99999999999"
        mock_employee.custom_id_type = "NRIC"
        mock_employee.custom_id_value = "960101014444"
        mock_employee.company = "Test Co"
        mock_frappe.get_doc.return_value = mock_employee

        mock_validate.return_value = (False, "LHDN TIN not found")

        result = validate_employee_tin("HR-EMP-001")

        self.assertFalse(result["valid"])
        self.assertEqual(result["message"], "LHDN TIN not found")
