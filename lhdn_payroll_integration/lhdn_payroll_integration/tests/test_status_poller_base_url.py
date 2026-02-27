"""Additional tests for status_poller _get_base_url(company_name) — US-003.

Validates that:
- _get_base_url accepts a company_name parameter (not default company)
- Returns correct sandbox or production URL based on integration type
- Returns empty string for None or empty company_name
"""
import frappe
from frappe.tests.utils import FrappeTestCase
from unittest.mock import MagicMock, patch


class TestGetBaseUrl(FrappeTestCase):
	"""Tests for _get_base_url(company_name) accepting company_name parameter."""

	@patch("lhdn_payroll_integration.services.status_poller.frappe")
	def test_get_base_url_accepts_company_name_param(self, mock_frappe):
		"""_get_base_url(company_name) fetches the named Company and returns sandbox URL."""
		from lhdn_payroll_integration.services.status_poller import _get_base_url

		company_doc = MagicMock()
		company_doc.custom_integration_type = "Sandbox"
		company_doc.custom_sandbox_url = "https://preprod-api.myinvois.hasil.gov.my"
		mock_frappe.get_doc.return_value = company_doc

		url = _get_base_url("Arising Packaging")

		self.assertEqual(url, "https://preprod-api.myinvois.hasil.gov.my")
		mock_frappe.get_doc.assert_called_once_with("Company", "Arising Packaging")

	@patch("lhdn_payroll_integration.services.status_poller.frappe")
	def test_get_base_url_returns_production_url(self, mock_frappe):
		"""_get_base_url returns production URL when integration_type is Production."""
		from lhdn_payroll_integration.services.status_poller import _get_base_url

		company_doc = MagicMock()
		company_doc.custom_integration_type = "Production"
		company_doc.custom_production_url = "https://api.myinvois.hasil.gov.my"
		mock_frappe.get_doc.return_value = company_doc

		url = _get_base_url("Arising Packaging")

		self.assertEqual(url, "https://api.myinvois.hasil.gov.my")

	def test_get_base_url_returns_empty_for_none(self):
		"""_get_base_url returns empty string when company_name is None."""
		from lhdn_payroll_integration.services.status_poller import _get_base_url

		self.assertEqual(_get_base_url(None), "")

	def test_get_base_url_returns_empty_for_empty_string(self):
		"""_get_base_url returns empty string when company_name is empty string."""
		from lhdn_payroll_integration.services.status_poller import _get_base_url

		self.assertEqual(_get_base_url(""), "")
