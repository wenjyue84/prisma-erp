"""
TDD Red Phase — Tests for QR code rendering on Salary Slip print format (UT-026).

Tests verify:
  - generate_qr_code_base64() converts a URL to a base64-encoded PNG data URI
  - Valid LHDN QR URLs produce correct output format
  - Empty/None URL inputs return empty string without error
  - Jinja helper is registered in hooks.py for use in print formats

These tests are expected to FAIL until US-026 is implemented.
"""
import frappe
from frappe.tests.utils import FrappeTestCase

from lhdn_payroll_integration.utils.qr_utils import generate_qr_code_base64


class TestQRCodeRendering(FrappeTestCase):
    """Tests for US-026: QR code rendering for LHDN e-Invoice on Salary Slip print format."""

    # --- AC 1: generate_qr_code_base64 returns base64 PNG data URI ---
    def test_generate_qr_code_returns_base64_png(self):
        """generate_qr_code_base64() returns a string starting with 'data:image/png;base64,'."""
        result = generate_qr_code_base64("https://example.com/test")
        self.assertIsInstance(result, str)
        self.assertTrue(
            result.startswith("data:image/png;base64,"),
            f"Expected result to start with 'data:image/png;base64,' but got: {result[:50]}",
        )

    # --- AC 2: Valid LHDN MyInvois QR URL produces correct output ---
    def test_qr_code_from_valid_url(self):
        """A valid LHDN MyInvois URL generates a non-empty base64 PNG data URI."""
        lhdn_url = "https://myinvois.hasil.gov.my/abc123-def456-ghi789"
        result = generate_qr_code_base64(lhdn_url)
        self.assertIsInstance(result, str)
        self.assertTrue(
            result.startswith("data:image/png;base64,"),
            "LHDN QR URL must produce a data:image/png;base64, string",
        )
        # The base64 content after the prefix must be non-empty
        base64_part = result.replace("data:image/png;base64,", "")
        self.assertTrue(
            len(base64_part) > 0,
            "Base64-encoded PNG content must not be empty",
        )

    # --- AC 3: Empty URL returns empty string ---
    def test_qr_code_empty_url_returns_empty_string(self):
        """generate_qr_code_base64('') returns '' without error."""
        result = generate_qr_code_base64("")
        self.assertEqual(
            result,
            "",
            "Empty URL must return empty string, not raise an error",
        )

    # --- AC 4: None URL returns empty string ---
    def test_qr_code_none_url_returns_empty_string(self):
        """generate_qr_code_base64(None) returns '' without error."""
        result = generate_qr_code_base64(None)
        self.assertEqual(
            result,
            "",
            "None URL must return empty string, not raise an error",
        )

    # --- AC 5: Jinja helper registered in hooks.py ---
    def test_jinja_helper_registered_in_hooks(self):
        """hooks.py registers generate_qr_code_base64 as a Jinja template method."""
        from lhdn_payroll_integration import hooks

        jinja_methods = getattr(hooks, "jinja", None)
        if jinja_methods is None:
            # Also check alternative hook key
            jinja_methods = getattr(hooks, "jenv", None)

        self.assertIsNotNone(
            jinja_methods,
            "hooks.py must define 'jinja' dict or list for Jinja template helpers",
        )

        # hooks.jinja can be a dict with 'methods' key or a list
        if isinstance(jinja_methods, dict):
            methods = jinja_methods.get("methods", [])
        else:
            methods = jinja_methods

        self.assertIn(
            "lhdn_payroll_integration.utils.qr_utils.generate_qr_code_base64",
            methods,
            "generate_qr_code_base64 must be registered as a Jinja method in hooks.py",
        )
