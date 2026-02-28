"""
US-100: Employment Act S.61 Compliant Payslip — verification tests.

These tests check that:
1. The print format files exist with correct metadata
2. The HTML template contains all mandatory EA S.61 fields
3. The bulk generation API is importable
"""

import json
import os
import frappe
from frappe.tests.utils import FrappeTestCase

PRINT_FORMAT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "print_format",
    "ea_s61_payslip",
)
JSON_FILE = os.path.join(PRINT_FORMAT_DIR, "ea_s61_payslip.json")
HTML_FILE = os.path.join(PRINT_FORMAT_DIR, "ea_s61_payslip.html")


class TestEAS61PrintFormatFiles(FrappeTestCase):
    """Verify print format files exist and have correct metadata."""

    def test_json_file_exists(self):
        self.assertTrue(os.path.exists(JSON_FILE), f"JSON not found: {JSON_FILE}")

    def test_json_doc_type_is_salary_slip(self):
        self.assertTrue(os.path.exists(JSON_FILE))
        with open(JSON_FILE) as f:
            data = json.load(f)
        self.assertEqual(data.get("doc_type"), "Salary Slip")

    def test_json_not_disabled(self):
        self.assertTrue(os.path.exists(JSON_FILE))
        with open(JSON_FILE) as f:
            data = json.load(f)
        self.assertEqual(data.get("disabled"), 0)

    def test_json_is_standard(self):
        self.assertTrue(os.path.exists(JSON_FILE))
        with open(JSON_FILE) as f:
            data = json.load(f)
        self.assertEqual(data.get("standard"), "Yes")

    def test_json_print_format_type_jinja(self):
        self.assertTrue(os.path.exists(JSON_FILE))
        with open(JSON_FILE) as f:
            data = json.load(f)
        self.assertEqual(data.get("print_format_type"), "Jinja")

    def test_html_file_exists(self):
        self.assertTrue(os.path.exists(HTML_FILE), f"HTML not found: {HTML_FILE}")


class TestEAS61HTMLMandatoryFields(FrappeTestCase):
    """Verify HTML template references all EA S.61 mandatory fields."""

    def _html(self):
        self.assertTrue(os.path.exists(HTML_FILE), f"HTML missing: {HTML_FILE}")
        with open(HTML_FILE) as f:
            return f.read()

    def test_contains_employee_name(self):
        html = self._html()
        self.assertIn("employee_name", html, "Missing: employee_name (full name)")

    def test_contains_nric_id_fields(self):
        html = self._html()
        self.assertIn("custom_id_value", html, "Missing: custom_id_value (NRIC/ID)")
        self.assertIn("custom_id_type", html, "Missing: custom_id_type")

    def test_contains_gender(self):
        html = self._html()
        self.assertIn("gender", html, "Missing: gender field")

    def test_contains_citizenship_status(self):
        html = self._html()
        self.assertIn("custom_is_foreign_worker", html, "Missing: citizenship / foreign worker flag")

    def test_contains_wage_period(self):
        html = self._html()
        self.assertIn("start_date", html, "Missing: start_date (wage period start)")
        self.assertIn("end_date", html, "Missing: end_date (wage period end)")

    def test_contains_payment_date(self):
        html = self._html()
        self.assertIn("posting_date", html, "Missing: posting_date (payment date)")

    def test_contains_gross_earnings(self):
        html = self._html()
        self.assertIn("gross_pay", html, "Missing: gross_pay field")
        self.assertIn("doc.earnings", html, "Missing: earnings itemization loop")

    def test_contains_deductions(self):
        html = self._html()
        self.assertIn("doc.deductions", html, "Missing: deductions itemization loop")
        self.assertIn("total_deduction", html, "Missing: total_deduction field")

    def test_contains_net_pay(self):
        html = self._html()
        self.assertIn("net_pay", html, "Missing: net_pay field")

    def test_contains_employer_name(self):
        html = self._html()
        self.assertIn("doc.company", html, "Missing: doc.company (employer name)")

    def test_contains_employer_address(self):
        html = self._html()
        self.assertIn("company_doc", html, "Missing: company_doc (employer address)")

    def test_contains_place_of_employment(self):
        html = self._html()
        # place of employment can be branch or company city
        has_place = "branch" in html or "city" in html
        self.assertTrue(has_place, "Missing: place of employment (branch or city)")

    def test_contains_employment_type(self):
        html = self._html()
        self.assertIn("employment_type", html, "Missing: employment_type field")

    def test_contains_ea_s61_compliance_reference(self):
        html = self._html()
        has_ref = "Section 61" in html or "S.61" in html or "Employment Act" in html
        self.assertTrue(has_ref, "Missing: Employment Act S.61 compliance reference in footer")


class TestEAS61BulkGenerationAPI(FrappeTestCase):
    """Verify the bulk payslip generation API is importable."""

    def test_bulk_generation_module_importable(self):
        try:
            from lhdn_payroll_integration.lhdn_payroll_integration.api import payslip_bulk
            self.assertTrue(hasattr(payslip_bulk, "generate_bulk_payslips"),
                            "generate_bulk_payslips function missing from payslip_bulk API")
        except ImportError as e:
            self.fail(f"Cannot import payslip_bulk API: {e}")
