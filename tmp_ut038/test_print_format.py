"""
UT-038: Failing tests for LHDN Salary Slip print format.
These tests check that print format files exist with correct content.
They will FAIL until US-038 creates the print format files.
"""

import json
import os
import frappe
from frappe.tests.utils import FrappeTestCase

PRINT_FORMAT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "print_format",
    "lhdn_salary_slip_einvoice",
)
JSON_FILE = os.path.join(PRINT_FORMAT_DIR, "lhdn_salary_slip_einvoice.json")
HTML_FILE = os.path.join(PRINT_FORMAT_DIR, "lhdn_salary_slip_einvoice.html")


class TestPrintFormatFileExists(FrappeTestCase):
    """Verify the print format JSON file exists and is valid."""

    def test_print_format_json_exists(self):
        """Print format JSON file must exist."""
        self.assertTrue(
            os.path.exists(JSON_FILE),
            f"Print format JSON file not found at {JSON_FILE}",
        )

    def test_print_format_json_doc_type(self):
        """Print format JSON must have doc_type=Salary Slip."""
        self.assertTrue(os.path.exists(JSON_FILE), f"JSON file missing: {JSON_FILE}")
        with open(JSON_FILE) as f:
            data = json.load(f)
        self.assertEqual(
            data.get("doc_type"),
            "Salary Slip",
            f"Expected doc_type 'Salary Slip', got {data.get('doc_type')!r}",
        )

    def test_print_format_json_not_disabled(self):
        """Print format JSON must have disabled=0."""
        self.assertTrue(os.path.exists(JSON_FILE), f"JSON file missing: {JSON_FILE}")
        with open(JSON_FILE) as f:
            data = json.load(f)
        self.assertEqual(
            data.get("disabled"),
            0,
            f"Expected disabled=0, got {data.get('disabled')!r}",
        )

    def test_print_format_html_exists(self):
        """Print format HTML template must exist."""
        self.assertTrue(
            os.path.exists(HTML_FILE),
            f"Print format HTML file not found at {HTML_FILE}",
        )


class TestPrintFormatHTMLContent(FrappeTestCase):
    """Verify the HTML template contains required LHDN field references."""

    def _get_html(self):
        self.assertTrue(os.path.exists(HTML_FILE), f"HTML file missing: {HTML_FILE}")
        with open(HTML_FILE) as f:
            return f.read()

    def test_html_contains_lhdn_uuid(self):
        """HTML template must reference custom_lhdn_uuid field."""
        html = self._get_html()
        self.assertIn(
            "custom_lhdn_uuid",
            html,
            "HTML template does not reference custom_lhdn_uuid",
        )

    def test_html_contains_lhdn_qr_code(self):
        """HTML template must reference custom_lhdn_qr_code field."""
        html = self._get_html()
        self.assertIn(
            "custom_lhdn_qr_code",
            html,
            "HTML template does not reference custom_lhdn_qr_code",
        )

    def test_html_contains_lhdn_status_check(self):
        """HTML template must have a conditional check for custom_lhdn_status == 'Valid'."""
        html = self._get_html()
        self.assertIn(
            "custom_lhdn_status",
            html,
            "HTML template does not reference custom_lhdn_status",
        )
        # Badge/compliant indicator should be conditional on Valid status
        self.assertIn(
            "Valid",
            html,
            "HTML template does not contain 'Valid' status check for LHDN badge",
        )

    def test_html_contains_compliant_badge(self):
        """HTML template must show an LHDN Compliant badge."""
        html = self._get_html()
        # Accept either English phrasing
        has_badge = "LHDN" in html and (
            "Compliant" in html or "e-Invoice" in html
        )
        self.assertTrue(
            has_badge,
            "HTML template does not contain an LHDN Compliant / e-Invoice badge",
        )
