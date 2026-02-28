"""Tests for e-CP39 API Submission service — US-063.

Verifies:
  - Successful submission stores reference in LHDN CP39 Submission Log
  - Failed submission (non-2xx HTTP) logs error with Failed status
  - Missing MyTax credentials raise ValidationError
  - Empty data set returns early with Failed log
  - Pipe-delimited payload format matches LHDN spec
"""
import json
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from lhdn_payroll_integration.lhdn_payroll_integration.services.ecp39_service import (
    _build_pipe_delimited_payload,
    _get_mytax_access_token,
    _store_submission_log,
    submit_cp39_to_lhdn,
)


class TestEcp39MissingCredentials(FrappeTestCase):
    """Credential validation: missing client_id or client_secret must raise."""

    def test_missing_credentials_raises_validation_error(self):
        """submit_cp39_to_lhdn raises ValidationError when credentials absent."""
        company = frappe.db.get_value("Company", {}, "name")
        if not company:
            self.skipTest("No Company found")

        with patch(
            "lhdn_payroll_integration.lhdn_payroll_integration.services.ecp39_service.frappe.db.get_value",
            return_value=None,
        ):
            with self.assertRaises(frappe.ValidationError):
                _get_mytax_access_token(company)


class TestEcp39TokenFetch(FrappeTestCase):
    """OAuth token retrieval tests."""

    def _make_company(self):
        return frappe.db.get_value("Company", {}, "name") or "Test Company"

    def test_successful_token_fetch(self):
        """Returns access_token string when HTTP 200 received."""
        company = self._make_company()

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"access_token": "test-token-abc"}

        with patch(
            "lhdn_payroll_integration.lhdn_payroll_integration.services.ecp39_service.frappe.db.get_value",
            side_effect=["client-id-001", "client-secret-xyz"],
        ), patch(
            "lhdn_payroll_integration.lhdn_payroll_integration.services.ecp39_service.requests.post",
            return_value=mock_resp,
        ):
            token = _get_mytax_access_token(company)
        self.assertEqual(token, "test-token-abc")

    def test_failed_auth_raises_authentication_error(self):
        """Raises AuthenticationError on non-200 token response."""
        company = self._make_company()

        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.text = "Unauthorized"

        with patch(
            "lhdn_payroll_integration.lhdn_payroll_integration.services.ecp39_service.frappe.db.get_value",
            side_effect=["client-id-001", "client-secret-xyz"],
        ), patch(
            "lhdn_payroll_integration.lhdn_payroll_integration.services.ecp39_service.requests.post",
            return_value=mock_resp,
        ):
            with self.assertRaises(frappe.AuthenticationError):
                _get_mytax_access_token(company)


class TestEcp39PayloadBuilder(FrappeTestCase):
    """Pipe-delimited payload format tests."""

    def test_payload_lines_pipe_separated(self):
        """Each line has exactly 10 pipe characters (11 fields)."""
        mock_rows = [
            {
                "employer_e_number": "E12345678",
                "month_year": "01/2024",
                "employee_tin": "IG1234567890",
                "employee_nric": "901234561234",
                "employee_name": "Ahmad bin Ali",
                "pcb_category": "1",
                "gross_remuneration": 5000.0,
                "epf_employee": 550.0,
                "zakat_amount": 0.0,
                "cp38_amount": 0.0,
                "total_pcb": 200.0,
            }
        ]

        company = frappe.db.get_value("Company", {}, "name") or "Test Company"

        with patch(
            "lhdn_payroll_integration.lhdn_payroll_integration.services.ecp39_service.get_data",
            return_value=mock_rows,
        ):
            lines = _build_pipe_delimited_payload(company, "01", 2024)

        self.assertEqual(len(lines), 1)
        parts = lines[0].split("|")
        self.assertEqual(len(parts), 11, f"Expected 11 pipe-separated fields, got {len(parts)}: {lines[0]}")

    def test_payload_amounts_formatted_to_2dp(self):
        """Currency fields formatted to 2 decimal places."""
        mock_rows = [
            {
                "employer_e_number": "E12345678",
                "month_year": "02/2024",
                "employee_tin": "IG999",
                "employee_nric": "800101011234",
                "employee_name": "Siti binti Rahmat",
                "pcb_category": "2",
                "gross_remuneration": 6500.5,
                "epf_employee": 715.05,
                "zakat_amount": 50.0,
                "cp38_amount": 0.0,
                "total_pcb": 300.1,
            }
        ]

        company = frappe.db.get_value("Company", {}, "name") or "Test Company"

        with patch(
            "lhdn_payroll_integration.lhdn_payroll_integration.services.ecp39_service.get_data",
            return_value=mock_rows,
        ):
            lines = _build_pipe_delimited_payload(company, "02", 2024)

        parts = lines[0].split("|")
        # Gross at index 6, EPF at 7, Zakat at 8, CP38 at 9, PCB at 10
        for idx in [6, 7, 8, 9, 10]:
            val = parts[idx]
            self.assertRegex(
                val,
                r"^\d+\.\d{2}$",
                f"Amount field at index {idx} not 2dp: '{val}'",
            )

    def test_empty_data_returns_empty_list(self):
        """When no CP39 rows exist, payload list is empty."""
        company = frappe.db.get_value("Company", {}, "name") or "Test Company"

        with patch(
            "lhdn_payroll_integration.lhdn_payroll_integration.services.ecp39_service.get_data",
            return_value=[],
        ):
            lines = _build_pipe_delimited_payload(company, "01", 2024)

        self.assertEqual(lines, [])


class TestEcp39SubmissionLog(FrappeTestCase):
    """Log creation tests."""

    def test_store_submission_log_creates_record(self):
        """_store_submission_log inserts a record and returns its name."""
        company = frappe.db.get_value("Company", {}, "name")
        if not company:
            self.skipTest("No Company found")

        log_name = _store_submission_log(
            company_name=company,
            month="01",
            year=2024,
            status="Submitted",
            submission_reference="REF-TEST-001",
            response_message='{"ok": true}',
            employees_count=5,
        )

        self.assertIsNotNone(log_name)
        log = frappe.get_doc("LHDN CP39 Submission Log", log_name)
        self.assertEqual(log.company, company)
        self.assertEqual(log.status, "Submitted")
        self.assertEqual(log.submission_reference, "REF-TEST-001")
        self.assertEqual(log.employees_count, 5)

    def test_store_failed_log_creates_record(self):
        """_store_submission_log with Failed status stores error message."""
        company = frappe.db.get_value("Company", {}, "name")
        if not company:
            self.skipTest("No Company found")

        log_name = _store_submission_log(
            company_name=company,
            month="02",
            year=2024,
            status="Failed",
            submission_reference="",
            response_message="HTTP 500: Internal Server Error",
            employees_count=0,
        )

        log = frappe.get_doc("LHDN CP39 Submission Log", log_name)
        self.assertEqual(log.status, "Failed")
        self.assertIn("500", log.response_message)


class TestEcp39FullSubmitSuccess(FrappeTestCase):
    """End-to-end submit_cp39_to_lhdn with mocked HTTP."""

    def _get_company(self):
        return frappe.db.get_value("Company", {}, "name")

    def test_successful_submission_stores_reference(self):
        """On 200 response, log is created with status=Submitted and reference."""
        company = self._get_company()
        if not company:
            self.skipTest("No Company found")

        mock_submit_resp = MagicMock()
        mock_submit_resp.status_code = 200
        mock_submit_resp.text = '{"submissionReference": "CP39-2024-01-ABC"}'
        mock_submit_resp.json.return_value = {"submissionReference": "CP39-2024-01-ABC"}

        mock_rows = [
            {
                "employer_e_number": "E99999",
                "month_year": "01/2024",
                "employee_tin": "IG000",
                "employee_nric": "900101011234",
                "employee_name": "Test Employee",
                "pcb_category": "1",
                "gross_remuneration": 4000.0,
                "epf_employee": 440.0,
                "zakat_amount": 0.0,
                "cp38_amount": 0.0,
                "total_pcb": 150.0,
            }
        ]

        _svc = "lhdn_payroll_integration.lhdn_payroll_integration.services.ecp39_service"
        with patch(f"{_svc}._get_mytax_access_token", return_value="tok-xyz"), patch(
            f"{_svc}.requests.post",
            return_value=mock_submit_resp,
        ), patch(
            f"{_svc}.get_data",
            return_value=mock_rows,
        ):
            result = submit_cp39_to_lhdn(company, "01", 2024)

        self.assertTrue(result["success"])
        self.assertEqual(result["reference"], "CP39-2024-01-ABC")
        self.assertIsNotNone(result["log_name"])

        # Verify log exists in DB
        log = frappe.get_doc("LHDN CP39 Submission Log", result["log_name"])
        self.assertEqual(log.status, "Submitted")
        self.assertEqual(log.submission_reference, "CP39-2024-01-ABC")
        self.assertEqual(log.employees_count, 1)

    def test_failed_submission_logs_error(self):
        """On non-2xx response, log is created with status=Failed and error message."""
        company = self._get_company()
        if not company:
            self.skipTest("No Company found")

        mock_submit_resp = MagicMock()
        mock_submit_resp.status_code = 422
        mock_submit_resp.text = "Unprocessable Entity: Invalid TIN"

        mock_rows = [
            {
                "employer_e_number": "E99999",
                "month_year": "01/2024",
                "employee_tin": "INVALID",
                "employee_nric": "900101011234",
                "employee_name": "Bad Employee",
                "pcb_category": "1",
                "gross_remuneration": 3000.0,
                "epf_employee": 330.0,
                "zakat_amount": 0.0,
                "cp38_amount": 0.0,
                "total_pcb": 100.0,
            }
        ]

        _svc = "lhdn_payroll_integration.lhdn_payroll_integration.services.ecp39_service"
        with patch(f"{_svc}._get_mytax_access_token", return_value="tok-abc"), patch(
            f"{_svc}.requests.post",
            return_value=mock_submit_resp,
        ), patch(
            f"{_svc}.get_data",
            return_value=mock_rows,
        ):
            result = submit_cp39_to_lhdn(company, "01", 2024)

        self.assertFalse(result["success"])
        self.assertIn("422", result["message"])
        self.assertIsNotNone(result["log_name"])

        log = frappe.get_doc("LHDN CP39 Submission Log", result["log_name"])
        self.assertEqual(log.status, "Failed")

    def test_empty_data_returns_failed_without_api_call(self):
        """When no CP39 rows exist, submission fails without hitting the API."""
        company = self._get_company()
        if not company:
            self.skipTest("No Company found")

        _svc = "lhdn_payroll_integration.lhdn_payroll_integration.services.ecp39_service"
        with patch(f"{_svc}._get_mytax_access_token", return_value="tok-xyz"), patch(
            f"{_svc}.requests.post",
        ) as mock_post, patch(
            f"{_svc}.get_data",
            return_value=[],
        ):
            result = submit_cp39_to_lhdn(company, "03", 2024)

        self.assertFalse(result["success"])
        self.assertIn("No CP39 data", result["message"])
        # requests.post must NOT be called (no submission payload)
        mock_post.assert_not_called()


class TestEcp39CustomFields(FrappeTestCase):
    """Verify custom_mytax_client_id and custom_mytax_client_secret exist on Company."""

    def test_company_has_mytax_client_id_field(self):
        """custom_mytax_client_id must exist as Custom Field on Company."""
        exists = frappe.db.exists(
            "Custom Field", {"dt": "Company", "fieldname": "custom_mytax_client_id"}
        )
        self.assertTrue(exists, "custom_mytax_client_id Custom Field missing on Company")

    def test_company_has_mytax_client_secret_field(self):
        """custom_mytax_client_secret must exist as Custom Field on Company."""
        exists = frappe.db.exists(
            "Custom Field", {"dt": "Company", "fieldname": "custom_mytax_client_secret"}
        )
        self.assertTrue(exists, "custom_mytax_client_secret Custom Field missing on Company")

    def test_cp39_submission_log_doctype_exists(self):
        """LHDN CP39 Submission Log DocType must be installed."""
        exists = frappe.db.exists("DocType", "LHDN CP39 Submission Log")
        self.assertTrue(exists, "LHDN CP39 Submission Log DocType not found")
