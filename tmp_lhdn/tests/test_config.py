"""Tests for environment toggle configuration — TDD red phase (UT-020).

Tests verify that get_lhdn_base_url() and related config utilities:
- Return sandbox URL when lhdn_environment='sandbox'
- Return production URL when lhdn_environment='production'
- Default to sandbox when lhdn_environment is missing
- Read lhdn_einvoice_version from config
- No hardcoded LHDN API URLs exist in Python files
"""

import os
import re

import frappe
from frappe.tests.utils import FrappeTestCase
from unittest.mock import patch, MagicMock

from lhdn_payroll_integration.utils.config import get_lhdn_base_url, get_einvoice_version

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

		for root_dir, dirs, files in os.walk(app_dir):
			# Skip __pycache__ and test directories
			dirs[:] = [d for d in dirs if d != "__pycache__"]
			for filename in files:
				if not filename.endswith(".py"):
					continue
				# Skip this test file itself (contains URLs as test constants)
				if filename == "test_config.py":
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
