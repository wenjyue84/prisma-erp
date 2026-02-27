"""Tests for submission service HTTP POST — TDD Red Phase (UT-011).

Tests process_salary_slip() HTTP POST to LHDN MyInvois API.
The HTTP POST functions do NOT exist yet — so bench run-tests will fail
with ImportError, confirming the TDD red phase.
"""
import frappe
from frappe.tests.utils import FrappeTestCase
from unittest.mock import MagicMock, patch, call
import json


class TestSubmissionService(FrappeTestCase):
    """Test submission service HTTP POST to LHDN API."""

    def _mock_202_accepted_response(self):
        """Create a mock 202 response with acceptedDocuments."""
        resp = MagicMock()
        resp.status_code = 202
        resp.json.return_value = {
            "acceptedDocuments": [
                {
                    "uuid": "ABC123-DEF456-GHI789",
                    "invoiceCodeNumber": "SAL-SLP-00001",
                }
            ],
            "rejectedDocuments": [],
        }
        return resp

    def _mock_202_rejected_response(self):
        """Create a mock 202 response with rejectedDocuments."""
        resp = MagicMock()
        resp.status_code = 202
        resp.json.return_value = {
            "acceptedDocuments": [],
            "rejectedDocuments": [
                {
                    "invoiceCodeNumber": "SAL-SLP-00001",
                    "error": {
                        "code": "InvalidTIN",
                        "message": "TIN validation failed",
                    },
                }
            ],
        }
        return resp

    def _mock_401_then_202_responses(self):
        """Create a mock that returns 401 first, then 202 accepted on retry."""
        resp_401 = MagicMock()
        resp_401.status_code = 401
        resp_401.text = "Unauthorized"

        resp_202 = self._mock_202_accepted_response()
        return [resp_401, resp_202]

    def _mock_timeout_response(self):
        """Create a mock that raises a timeout exception."""
        import requests

        return requests.exceptions.Timeout("Connection timed out")

    @patch("lhdn_payroll_integration.services.submission_service.prepare_submission_wrapper")
    @patch("lhdn_payroll_integration.services.submission_service.build_salary_slip_xml")
    @patch("lhdn_payroll_integration.services.submission_service.frappe")
    def test_process_salary_slip_calls_xml_builder(
        self, mock_frappe, mock_build_xml, mock_wrapper
    ):
        """process_salary_slip calls build_salary_slip_xml with the docname."""
        from lhdn_payroll_integration.services.submission_service import (
            process_salary_slip,
            get_access_token,
        )

        mock_build_xml.return_value = "<Invoice>...</Invoice>"
        mock_wrapper.return_value = {
            "documents": [{"format": "XML", "document": "base64data", "documentHash": "sha256hash", "codeNumber": "00001"}]
        }

        # Mock requests.post to return 202 accepted
        with patch("lhdn_payroll_integration.services.submission_service.requests") as mock_requests:
            mock_requests.post.return_value = self._mock_202_accepted_response()
            mock_frappe.get_doc.return_value = MagicMock(company="Test Co")
            mock_frappe.db.get_single_value.return_value = "https://preprod-api.myinvois.hasil.gov.my"

            process_salary_slip("SAL-SLP-00001")

        mock_build_xml.assert_called_once_with("SAL-SLP-00001")

    @patch("lhdn_payroll_integration.services.submission_service.prepare_submission_wrapper")
    @patch("lhdn_payroll_integration.services.submission_service.build_salary_slip_xml")
    @patch("lhdn_payroll_integration.services.submission_service.requests")
    @patch("lhdn_payroll_integration.services.submission_service.frappe")
    def test_on_202_accepted_sets_submitted_status(
        self, mock_frappe, mock_requests, mock_build_xml, mock_wrapper
    ):
        """On 202 with acceptedDocuments, sets custom_lhdn_status='Submitted' and stores UUID."""
        from lhdn_payroll_integration.services.submission_service import (
            process_salary_slip,
            get_access_token,
        )

        mock_build_xml.return_value = "<Invoice>...</Invoice>"
        mock_wrapper.return_value = {
            "documents": [{"format": "XML", "document": "base64data", "documentHash": "sha256hash", "codeNumber": "00001"}]
        }
        mock_requests.post.return_value = self._mock_202_accepted_response()
        mock_frappe.get_doc.return_value = MagicMock(company="Test Co")
        mock_frappe.db.get_single_value.return_value = "https://preprod-api.myinvois.hasil.gov.my"

        process_salary_slip("SAL-SLP-00001")

        # Should set status to Submitted and store UUID
        set_value_calls = mock_frappe.db.set_value.call_args_list
        status_set = False
        uuid_set = False
        for c in set_value_calls:
            args = c[0] if c[0] else ()
            if len(args) >= 4:
                if args[2] == "custom_lhdn_status" and args[3] == "Submitted":
                    status_set = True
                if args[2] == "custom_lhdn_uuid" and args[3] == "ABC123-DEF456-GHI789":
                    uuid_set = True
        self.assertTrue(status_set, "custom_lhdn_status should be set to 'Submitted'")
        self.assertTrue(uuid_set, "custom_lhdn_uuid should be set to the returned UUID")

    @patch("lhdn_payroll_integration.services.submission_service.prepare_submission_wrapper")
    @patch("lhdn_payroll_integration.services.submission_service.build_salary_slip_xml")
    @patch("lhdn_payroll_integration.services.submission_service.requests")
    @patch("lhdn_payroll_integration.services.submission_service.frappe")
    def test_on_202_rejected_sets_invalid_status(
        self, mock_frappe, mock_requests, mock_build_xml, mock_wrapper
    ):
        """On 202 with rejectedDocuments, sets custom_lhdn_status='Invalid' and logs error."""
        from lhdn_payroll_integration.services.submission_service import (
            process_salary_slip,
            get_access_token,
        )

        mock_build_xml.return_value = "<Invoice>...</Invoice>"
        mock_wrapper.return_value = {
            "documents": [{"format": "XML", "document": "base64data", "documentHash": "sha256hash", "codeNumber": "00001"}]
        }
        mock_requests.post.return_value = self._mock_202_rejected_response()
        mock_frappe.get_doc.return_value = MagicMock(company="Test Co")
        mock_frappe.db.get_single_value.return_value = "https://preprod-api.myinvois.hasil.gov.my"

        process_salary_slip("SAL-SLP-00001")

        # Should set status to Invalid and log error
        set_value_calls = mock_frappe.db.set_value.call_args_list
        status_set = False
        error_logged = False
        for c in set_value_calls:
            args = c[0] if c[0] else ()
            if len(args) >= 4:
                if args[2] == "custom_lhdn_status" and args[3] == "Invalid":
                    status_set = True
                if args[2] == "custom_error_log":
                    error_logged = True
        self.assertTrue(status_set, "custom_lhdn_status should be set to 'Invalid'")
        self.assertTrue(error_logged, "custom_error_log should be set with error details")

    @patch("lhdn_payroll_integration.services.submission_service.prepare_submission_wrapper")
    @patch("lhdn_payroll_integration.services.submission_service.build_salary_slip_xml")
    @patch("lhdn_payroll_integration.services.submission_service.requests")
    @patch("lhdn_payroll_integration.services.submission_service.frappe")
    def test_on_timeout_calls_schedule_retry(
        self, mock_frappe, mock_requests, mock_build_xml, mock_wrapper
    ):
        """On request timeout, increments retry_count and re-enqueues."""
        from lhdn_payroll_integration.services.submission_service import (
            process_salary_slip,
            get_access_token,
            schedule_retry,
        )
        import requests as real_requests

        mock_build_xml.return_value = "<Invoice>...</Invoice>"
        mock_wrapper.return_value = {
            "documents": [{"format": "XML", "document": "base64data", "documentHash": "sha256hash", "codeNumber": "00001"}]
        }
        mock_requests.post.side_effect = real_requests.exceptions.Timeout("Connection timed out")
        mock_requests.exceptions = real_requests.exceptions
        mock_frappe.get_doc.return_value = MagicMock(company="Test Co")
        mock_frappe.db.get_single_value.return_value = "https://preprod-api.myinvois.hasil.gov.my"
        mock_frappe.db.get_value.return_value = 0  # current retry_count

        process_salary_slip("SAL-SLP-00001")

        # Should increment retry count
        set_value_calls = mock_frappe.db.set_value.call_args_list
        retry_incremented = False
        for c in set_value_calls:
            args = c[0] if c[0] else ()
            if len(args) >= 4 and args[2] == "custom_retry_count":
                retry_incremented = True
        self.assertTrue(retry_incremented, "custom_retry_count should be incremented on timeout")

        # Should re-enqueue
        mock_frappe.enqueue.assert_called()

    @patch("lhdn_payroll_integration.services.submission_service.prepare_submission_wrapper")
    @patch("lhdn_payroll_integration.services.submission_service.build_salary_slip_xml")
    @patch("lhdn_payroll_integration.services.submission_service.requests")
    @patch("lhdn_payroll_integration.services.submission_service.frappe")
    def test_token_fetch_via_get_access_token(
        self, mock_frappe, mock_requests, mock_build_xml, mock_wrapper
    ):
        """process_salary_slip fetches token via get_access_token before HTTP POST."""
        from lhdn_payroll_integration.services.submission_service import (
            process_salary_slip,
            get_access_token,
        )

        mock_build_xml.return_value = "<Invoice>...</Invoice>"
        mock_wrapper.return_value = {
            "documents": [{"format": "XML", "document": "base64data", "documentHash": "sha256hash", "codeNumber": "00001"}]
        }
        mock_requests.post.return_value = self._mock_202_accepted_response()

        # Mock company doc with LHDN credentials
        company_doc = MagicMock()
        company_doc.name = "Test Co"
        company_doc.custom_client_id = "test-client-id"
        company_doc.custom_client_secret = "test-client-secret"
        company_doc.custom_sandbox_url = "https://preprod-api.myinvois.hasil.gov.my"
        company_doc.custom_integration_type = "Sandbox"

        salary_slip_doc = MagicMock()
        salary_slip_doc.company = "Test Co"

        mock_frappe.get_doc.side_effect = lambda dt, name=None: (
            salary_slip_doc if dt == "Salary Slip" else company_doc
        )

        with patch(
            "lhdn_payroll_integration.services.submission_service.get_access_token"
        ) as mock_get_token:
            mock_get_token.return_value = "test-bearer-token-123"
            process_salary_slip("SAL-SLP-00001")
            mock_get_token.assert_called_once()

        # Verify Authorization header was set with the token
        post_call = mock_requests.post.call_args
        self.assertIn("headers", post_call[1] if post_call[1] else {})
        headers = post_call[1].get("headers", {})
        self.assertEqual(headers.get("Authorization"), "Bearer test-bearer-token-123")

    @patch("lhdn_payroll_integration.services.submission_service.prepare_submission_wrapper")
    @patch("lhdn_payroll_integration.services.submission_service.build_salary_slip_xml")
    @patch("lhdn_payroll_integration.services.submission_service.requests")
    @patch("lhdn_payroll_integration.services.submission_service.frappe")
    def test_401_refreshes_token_and_retries(
        self, mock_frappe, mock_requests, mock_build_xml, mock_wrapper
    ):
        """On 401 response, refreshes the access token and retries the POST once."""
        from lhdn_payroll_integration.services.submission_service import (
            process_salary_slip,
            get_access_token,
        )

        mock_build_xml.return_value = "<Invoice>...</Invoice>"
        mock_wrapper.return_value = {
            "documents": [{"format": "XML", "document": "base64data", "documentHash": "sha256hash", "codeNumber": "00001"}]
        }

        # First call returns 401, second returns 202 accepted
        responses = self._mock_401_then_202_responses()
        mock_requests.post.side_effect = responses
        mock_frappe.get_doc.return_value = MagicMock(company="Test Co")
        mock_frappe.db.get_single_value.return_value = "https://preprod-api.myinvois.hasil.gov.my"

        with patch(
            "lhdn_payroll_integration.services.submission_service.get_access_token"
        ) as mock_get_token:
            mock_get_token.side_effect = ["first-token", "refreshed-token"]
            process_salary_slip("SAL-SLP-00001")

            # get_access_token should be called twice: initial + refresh
            self.assertEqual(mock_get_token.call_count, 2)

        # requests.post should be called twice: initial 401 + retry with new token
        self.assertEqual(mock_requests.post.call_count, 2)

    @patch("lhdn_payroll_integration.services.submission_service.prepare_submission_wrapper")
    @patch("lhdn_payroll_integration.services.submission_service.build_salary_slip_xml")
    @patch("lhdn_payroll_integration.services.submission_service.requests")
    @patch("lhdn_payroll_integration.services.submission_service.frappe")
    def test_url_constructed_from_site_config(
        self, mock_frappe, mock_requests, mock_build_xml, mock_wrapper
    ):
        """Submission URL is constructed from Company LHDN config (sandbox/production URL)."""
        from lhdn_payroll_integration.services.submission_service import (
            process_salary_slip,
            get_access_token,
        )

        mock_build_xml.return_value = "<Invoice>...</Invoice>"
        mock_wrapper.return_value = {
            "documents": [{"format": "XML", "document": "base64data", "documentHash": "sha256hash", "codeNumber": "00001"}]
        }
        mock_requests.post.return_value = self._mock_202_accepted_response()

        # Mock company doc with sandbox URL
        company_doc = MagicMock()
        company_doc.name = "Test Co"
        company_doc.custom_sandbox_url = "https://preprod-api.myinvois.hasil.gov.my"
        company_doc.custom_production_url = "https://api.myinvois.hasil.gov.my"
        company_doc.custom_integration_type = "Sandbox"
        company_doc.custom_client_id = "test-id"
        company_doc.custom_client_secret = "test-secret"

        salary_slip_doc = MagicMock()
        salary_slip_doc.company = "Test Co"

        mock_frappe.get_doc.side_effect = lambda dt, name=None: (
            salary_slip_doc if dt == "Salary Slip" else company_doc
        )

        with patch(
            "lhdn_payroll_integration.services.submission_service.get_access_token"
        ) as mock_get_token:
            mock_get_token.return_value = "test-token"
            process_salary_slip("SAL-SLP-00001")

        # Verify the URL used in requests.post contains the sandbox base URL
        post_call = mock_requests.post.call_args
        url_used = post_call[0][0] if post_call[0] else post_call[1].get("url", "")
        self.assertIn(
            "preprod-api.myinvois.hasil.gov.my",
            url_used,
            "POST URL should use the sandbox URL from Company config",
        )
        self.assertIn(
            "/api/v1.0/documentsubmissions",
            url_used,
            "POST URL should include the LHDN submissions endpoint",
        )


class TestTokenExpiry(FrappeTestCase):
    """Tests for get_access_token token expiry checking and error logging (US-003)."""

    @patch("lhdn_payroll_integration.services.submission_service.frappe")
    def test_valid_cached_token_returned_without_refresh(self, mock_frappe):
        """When cached token has > 5 min remaining, returns it without calling taxpayerlogin."""
        from datetime import datetime
        from lhdn_payroll_integration.services.submission_service import get_access_token

        now = datetime(2026, 1, 1, 12, 0, 0)
        company_doc = MagicMock()
        company_doc.custom_bearer_token = "cached-valid-token"
        company_doc.custom_token_expires_at = datetime(2026, 1, 1, 12, 10, 0)  # 10 min from now
        mock_frappe.get_doc.return_value = company_doc
        mock_frappe.utils.now_datetime.return_value = now

        result = get_access_token("Test Co")

        self.assertEqual(result, "cached-valid-token")

    @patch("lhdn_payroll_integration.services.submission_service.frappe")
    def test_token_within_5min_triggers_refresh(self, mock_frappe):
        """When cached token expires within 5 min, calls taxpayerlogin for fresh token."""
        import sys
        from datetime import datetime
        from lhdn_payroll_integration.services.submission_service import get_access_token

        now = datetime(2026, 1, 1, 12, 0, 0)
        company_doc = MagicMock()
        company_doc.custom_bearer_token = "expiring-token"
        company_doc.custom_token_expires_at = datetime(2026, 1, 1, 12, 3, 0)  # only 3 min left
        mock_frappe.get_doc.return_value = company_doc
        mock_frappe.utils.now_datetime.return_value = now

        mock_taxpayer = MagicMock()
        mock_taxpayer.get_access_token.return_value = "fresh-token"

        with patch.dict(sys.modules, {
            "myinvois_erpgulf": MagicMock(),
            "myinvois_erpgulf.myinvois_erpgulf": MagicMock(),
            "myinvois_erpgulf.myinvois_erpgulf.taxpayerlogin": mock_taxpayer,
        }):
            result = get_access_token("Test Co")

        self.assertEqual(result, "fresh-token")
        mock_taxpayer.get_access_token.assert_called_once_with("Test Co")

    @patch("lhdn_payroll_integration.services.submission_service.frappe")
    def test_no_cached_token_calls_taxpayerlogin(self, mock_frappe):
        """When no cached token exists, calls taxpayerlogin for a fresh token."""
        import sys
        from lhdn_payroll_integration.services.submission_service import get_access_token

        company_doc = MagicMock()
        company_doc.custom_bearer_token = None
        company_doc.custom_token_expires_at = None
        mock_frappe.get_doc.return_value = company_doc

        mock_taxpayer = MagicMock()
        mock_taxpayer.get_access_token.return_value = "brand-new-token"

        with patch.dict(sys.modules, {
            "myinvois_erpgulf": MagicMock(),
            "myinvois_erpgulf.myinvois_erpgulf": MagicMock(),
            "myinvois_erpgulf.myinvois_erpgulf.taxpayerlogin": mock_taxpayer,
        }):
            result = get_access_token("Test Co")

        self.assertEqual(result, "brand-new-token")

    @patch("lhdn_payroll_integration.services.submission_service.frappe")
    def test_token_exception_logs_error_and_returns_empty(self, mock_frappe):
        """When taxpayerlogin raises, frappe.log_error is called and '' is returned."""
        import sys
        from lhdn_payroll_integration.services.submission_service import get_access_token

        company_doc = MagicMock()
        company_doc.custom_bearer_token = None
        company_doc.custom_token_expires_at = None
        mock_frappe.get_doc.return_value = company_doc
        mock_frappe.get_traceback.return_value = "Traceback ..."

        mock_taxpayer = MagicMock()
        mock_taxpayer.get_access_token.side_effect = Exception("Connection refused")

        with patch.dict(sys.modules, {
            "myinvois_erpgulf": MagicMock(),
            "myinvois_erpgulf.myinvois_erpgulf": MagicMock(),
            "myinvois_erpgulf.myinvois_erpgulf.taxpayerlogin": mock_taxpayer,
        }):
            result = get_access_token("Test Co")

        self.assertEqual(result, "")
        mock_frappe.log_error.assert_called_once()
        call_kwargs = mock_frappe.log_error.call_args
        title_arg = call_kwargs[1].get("title") or (call_kwargs[0][0] if call_kwargs[0] else "")
        self.assertIn("Test Co", title_arg)
