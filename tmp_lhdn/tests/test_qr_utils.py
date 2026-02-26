"""Tests for QR code rendering on Salary Slip print format — TDD red phase (UT-026).

Tests verify that generate_qr_code_base64():
- Returns a base64-encoded PNG string for valid URLs
- Returns empty string for empty/None URLs
- Jinja helper is registered in hooks
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from lhdn_payroll_integration.utils.qr_utils import generate_qr_code_base64


class TestQRCodeRendering(FrappeTestCase):
	"""Test suite for QR code generation utility."""

	def test_generate_qr_code_returns_base64_png(self):
		"""generate_qr_code_base64() with a valid URL must return a string
		starting with 'data:image/png;base64,'."""
		result = generate_qr_code_base64("https://myinvois.hasil.gov.my/ABC-123")
		self.assertIsInstance(result, str)
		self.assertTrue(
			result.startswith("data:image/png;base64,"),
			f"Expected base64 PNG data URI, got: {result[:50]}..."
		)

	def test_qr_code_from_valid_url(self):
		"""QR code generated from a valid URL must be a non-empty base64 string."""
		result = generate_qr_code_base64("https://example.com/invoice/123")
		self.assertTrue(len(result) > 50,
			"QR code base64 string should be substantial in length")

	def test_qr_code_empty_url_returns_empty_string(self):
		"""generate_qr_code_base64('') must return an empty string."""
		result = generate_qr_code_base64("")
		self.assertEqual(result, "",
			"Empty URL should return empty string")

	def test_qr_code_none_url_returns_empty_string(self):
		"""generate_qr_code_base64(None) must return an empty string."""
		result = generate_qr_code_base64(None)
		self.assertEqual(result, "",
			"None URL should return empty string")

	def test_jinja_helper_registered_in_hooks(self):
		"""The generate_qr_code_base64 function must be registered as a
		Jinja template method in hooks.py for use in print formats."""
		from lhdn_payroll_integration import hooks

		jinja_methods = getattr(hooks, "jinja", {})
		if isinstance(jinja_methods, dict):
			methods = jinja_methods.get("methods", [])
		elif isinstance(jinja_methods, list):
			methods = jinja_methods
		else:
			methods = []

		# Check if qr_utils function is referenced in jinja methods
		qr_ref = "lhdn_payroll_integration.utils.qr_utils.generate_qr_code_base64"
		self.assertIn(qr_ref, methods,
			f"generate_qr_code_base64 not found in hooks.jinja methods: {methods}")
