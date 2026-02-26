"""Tests for environment toggle and mandatory date gating configuration.

Tests verify that:
- get_lhdn_base_url() and related config utilities work correctly (UT-020)
- Mandatory e-invoice date gating returns correct dates per revenue tier (UT-028)
- Sandbox mode bypasses mandatory date checks
- Production mode before mandatory date logs a warning
"""

import os
import re

import frappe
from frappe.tests.utils import FrappeTestCase
from unittest.mock import patch, MagicMock

from datetime import date

from lhdn_payroll_integration.utils.config import get_lhdn_base_url, get_einvoice_version
from lhdn_payroll_integration.utils.config import get_mandatory_date, check_mandatory_compliance

SANDBOX_URL = "https://preprod-api.myinvois.hasil.gov.my"
PRODUCTION_URL = "https://api.myinvois.hasil.gov.my"


class TestEnvironmentToggle(FrappeTestCase):
	"""Test suite for LHDN environment toggle configuration."""

	@patch("lhdn_payroll_integration.utils.config.frappe")
	def test_sandbox_config_uses_preprod_url(self, mock_frappe):
		"""With lhdn_environment='sandbox', get_lhdn_base_url() returns
		the sandbox (preprod) URL."""
		mock_frappe.conf.get.side_effect = lambda key, default=None: {
			"lhdn_environment": "sandbox",
			"lhdn_sandbox_url": SANDBOX_URL,
		}.get(key, default)

		url = get_lhdn_base_url()

		self.assertEqual(url, SANDBOX_URL,
			f"Sandbox config should return preprod URL, got '{url}'")

	@patch("lhdn_payroll_integration.utils.config.frappe")
	def test_production_config_uses_prod_url(self, mock_frappe):
		"""With lhdn_environment='production', get_lhdn_base_url() returns
		the production URL."""
		mock_frappe.conf.get.side_effect = lambda key, default=None: {
			"lhdn_environment": "production",
			"lhdn_production_url": PRODUCTION_URL,
		}.get(key, default)

		url = get_lhdn_base_url()

		self.assertEqual(url, PRODUCTION_URL,
			f"Production config should return prod URL, got '{url}'")

	@patch("lhdn_payroll_integration.utils.config.frappe")
	def test_missing_config_defaults_to_sandbox(self, mock_frappe):
		"""When lhdn_environment is not set, default to sandbox (safe default)."""
		mock_frappe.conf.get.side_effect = lambda key, default=None: {
			"lhdn_sandbox_url": SANDBOX_URL,
		}.get(key, default)

		url = get_lhdn_base_url()

		self.assertEqual(url, SANDBOX_URL,
			f"Missing lhdn_environment should default to sandbox URL, got '{url}'")

	@patch("lhdn_payroll_integration.utils.config.frappe")
	def test_einvoice_version_from_config(self, mock_frappe):
		"""get_einvoice_version() reads lhdn_einvoice_version from site config."""
		mock_frappe.conf.get.side_effect = lambda key, default=None: {
			"lhdn_einvoice_version": "1.1",
		}.get(key, default)

		version = get_einvoice_version()

		self.assertEqual(version, "1.1",
			f"Expected einvoice version '1.1', got '{version}'")

	def test_no_hardcoded_urls_in_python_files(self):
		"""No .py file in the app should contain hardcoded LHDN API URLs.
		All URLs should come from site config via get_lhdn_base_url()."""
		app_dir = os.path.join(
			os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
		)

		# Patterns that should NOT appear in Python source
		hardcoded_patterns = [
			re.compile(r'["\']https?://preprod-api\.myinvois\.hasil\.gov\.my'),
			re.compile(r'["\']https?://api\.myinvois\.hasil\.gov\.my'),
		]

		violations = []

		# Files that legitimately contain URLs (test mocks and config defaults)
		skip_files = {"test_config.py", "config.py"}

		for root_dir, dirs, files in os.walk(app_dir):
			# Skip __pycache__ and test directories
			dirs[:] = [d for d in dirs if d not in ("__pycache__", "tests")]
			for filename in files:
				if not filename.endswith(".py"):
					continue
				# Skip test files and config module (they use URLs legitimately)
				if filename in skip_files:
					continue

				filepath = os.path.join(root_dir, filename)
				with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
					content = f.read()

				for pattern in hardcoded_patterns:
					matches = pattern.findall(content)
					if matches:
						rel_path = os.path.relpath(filepath, app_dir)
						violations.append(f"{rel_path}: {matches}")

		self.assertEqual(violations, [],
			f"Hardcoded LHDN URLs found in Python files:\n" +
			"\n".join(violations))


class TestMandatoryDateGating(FrappeTestCase):
	"""Test suite for mandatory e-invoice date gating by company revenue tier."""

	def test_revenue_above_100m_mandatory_from_aug_2024(self):
		"""Companies with annual revenue above RM100M must comply from 1 Aug 2024."""
		result = get_mandatory_date("Above RM100M")
		self.assertEqual(result, date(2024, 8, 1),
			f"Above RM100M mandatory date should be 2024-08-01, got {result}")

	def test_revenue_25m_to_100m_mandatory_from_jan_2025(self):
		"""Companies with annual revenue RM25M-RM100M must comply from 1 Jan 2025."""
		result = get_mandatory_date("RM25M to RM100M")
		self.assertEqual(result, date(2025, 1, 1),
			f"RM25M-RM100M mandatory date should be 2025-01-01, got {result}")

	def test_revenue_5m_to_25m_mandatory_from_jul_2025(self):
		"""Companies with annual revenue RM5M-RM25M must comply from 1 Jul 2025."""
		result = get_mandatory_date("RM5M to RM25M")
		self.assertEqual(result, date(2025, 7, 1),
			f"RM5M-RM25M mandatory date should be 2025-07-01, got {result}")

	def test_revenue_1m_to_5m_mandatory_from_jan_2026(self):
		"""Companies with annual revenue RM1M-RM5M must comply from 1 Jan 2026."""
		result = get_mandatory_date("RM1M to RM5M")
		self.assertEqual(result, date(2026, 1, 1),
			f"RM1M-RM5M mandatory date should be 2026-01-01, got {result}")

	def test_below_1m_exempt_mandatory_date_is_none(self):
		"""Companies with annual revenue below RM1M are exempt (no mandatory date)."""
		result = get_mandatory_date("Below RM1M (Exempt)")
		self.assertIsNone(result,
			f"Below RM1M (Exempt) should return None, got {result}")

	@patch("lhdn_payroll_integration.utils.config.frappe")
	def test_production_before_mandatory_date_logs_warning(self, mock_frappe):
		"""In production mode before mandatory date, check_mandatory_compliance
		should log a warning via frappe.log_error."""
		mock_frappe.conf.get.return_value = "production"
		mock_frappe.db.get_value.return_value = "RM1M to RM5M"
		mock_frappe.utils.today.return_value = "2025-06-15"

		check_mandatory_compliance("Test Company")

		mock_frappe.log_error.assert_called()
		log_call_args = str(mock_frappe.log_error.call_args)
		self.assertIn("LHDN Compliance Warning", log_call_args,
			"Should log an LHDN Compliance Warning before mandatory date")

	@patch("lhdn_payroll_integration.utils.config.frappe")
	def test_sandbox_mode_bypasses_mandatory_date_check(self, mock_frappe):
		"""In sandbox mode, check_mandatory_compliance should bypass entirely
		and NOT log any warning."""
		mock_frappe.conf.get.return_value = "sandbox"

		check_mandatory_compliance("Test Company")

		mock_frappe.db.get_value.assert_not_called()
		mock_frappe.log_error.assert_not_called()
