"""Tests for get_access_token() expiry checking and error logging — US-003.

Validates that:
- Cached token is returned when more than 5 minutes remain until expiry
- Token is refreshed when within 5 minutes of expiry
- Exceptions during token fetch are logged via frappe.log_error()
  rather than silently swallowed; empty string is returned on failure
- Cached token with no expiry timestamp is trusted directly
"""
import frappe
from frappe.tests.utils import FrappeTestCase
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta


class TestGetAccessTokenExpiry(FrappeTestCase):
	"""Tests for get_access_token() token expiry handling."""

	@patch("lhdn_payroll_integration.services.submission_service.frappe")
	def test_cached_token_returned_when_expiry_far(self, mock_frappe):
		"""Cached token is returned directly when more than 5 minutes until expiry."""
		from lhdn_payroll_integration.services.submission_service import get_access_token

		now = datetime(2026, 2, 27, 10, 0, 0)
		expires_at = now + timedelta(minutes=10)  # 10 min remaining — well beyond 5 min buffer

		company_doc = MagicMock()
		company_doc.custom_bearer_token = "cached-token-123"
		company_doc.custom_token_expires_at = expires_at
		mock_frappe.get_doc.return_value = company_doc
		mock_frappe.utils.now_datetime.return_value = now

		result = get_access_token("Test Company")

		self.assertEqual(result, "cached-token-123")

	@patch("lhdn_payroll_integration.services.submission_service.frappe")
	def test_token_refreshed_when_near_expiry(self, mock_frappe):
		"""Token refresh is triggered when within 5 minutes of expiry."""
		from lhdn_payroll_integration.services.submission_service import get_access_token

		now = datetime(2026, 2, 27, 10, 0, 0)
		expires_at = now + timedelta(minutes=2)  # only 2 min remaining — within 5 min buffer

		company_doc = MagicMock()
		company_doc.custom_bearer_token = "old-token"
		company_doc.custom_token_expires_at = expires_at
		mock_frappe.get_doc.return_value = company_doc
		mock_frappe.utils.now_datetime.return_value = now

		with patch(
			"myinvois_erpgulf.myinvois_erpgulf.taxpayerlogin.get_access_token"
		) as mock_get_token:
			mock_get_token.return_value = "new-refreshed-token"
			result = get_access_token("Test Company")

		self.assertEqual(result, "new-refreshed-token")

	@patch("lhdn_payroll_integration.services.submission_service.frappe")
	def test_exception_calls_log_error_and_returns_empty(self, mock_frappe):
		"""Exception during token fetch logs via frappe.log_error and returns empty string."""
		from lhdn_payroll_integration.services.submission_service import get_access_token

		company_doc = MagicMock()
		company_doc.custom_bearer_token = None
		company_doc.custom_token_expires_at = None
		mock_frappe.get_doc.return_value = company_doc
		mock_frappe.get_traceback.return_value = "Traceback (most recent call last): ..."

		with patch(
			"myinvois_erpgulf.myinvois_erpgulf.taxpayerlogin.get_access_token",
			side_effect=Exception("LHDN API unavailable"),
		):
			result = get_access_token("Test Company")

		mock_frappe.log_error.assert_called()
		self.assertEqual(result, "")

	@patch("lhdn_payroll_integration.services.submission_service.frappe")
	def test_cached_token_without_expiry_returned_directly(self, mock_frappe):
		"""Cached token with no expiry timestamp is returned without refresh attempt."""
		from lhdn_payroll_integration.services.submission_service import get_access_token

		company_doc = MagicMock()
		company_doc.custom_bearer_token = "no-expiry-token"
		company_doc.custom_token_expires_at = None  # no expiry set
		mock_frappe.get_doc.return_value = company_doc

		result = get_access_token("Test Company")

		self.assertEqual(result, "no-expiry-token")
		# frappe.utils.now_datetime should NOT be called (no expiry to check)
		mock_frappe.utils.now_datetime.assert_not_called()
