"""US-094: EC Form (Borang EC) for Statutory / Government Body Employers.

ITA 1967 Section 83A — verifies:
1. EC Form report files exist with correct metadata
2. EC Form column labels use "EC" prefix (not "EA")
3. custom_is_statutory_employer Check field is defined in fixtures
4. EC Form reuses EA Form data pipeline (get_data is shared)
"""
import json
import os

import frappe
from frappe.tests.utils import FrappeTestCase

APP_DIR = os.path.dirname(os.path.dirname(__file__))
EC_FORM_DIR = os.path.join(APP_DIR, "report", "ec_form")
EC_JSON = os.path.join(EC_FORM_DIR, "ec_form.json")
EC_PY = os.path.join(EC_FORM_DIR, "ec_form.py")
FIXTURES_DIR = os.path.join(APP_DIR, "fixtures")
CUSTOM_FIELD_JSON = os.path.join(FIXTURES_DIR, "custom_field.json")


class TestECFormFiles(FrappeTestCase):
    """EC Form report files exist and have correct metadata."""

    def test_ec_form_json_exists(self):
        self.assertTrue(os.path.exists(EC_JSON), f"EC Form JSON not found: {EC_JSON}")

    def test_ec_form_py_exists(self):
        self.assertTrue(os.path.exists(EC_PY), f"EC Form .py not found: {EC_PY}")

    def test_ec_form_json_report_type_is_script(self):
        self.assertTrue(os.path.exists(EC_JSON))
        with open(EC_JSON) as f:
            data = json.load(f)
        self.assertEqual(data.get("report_type"), "Script Report")

    def test_ec_form_json_is_standard(self):
        self.assertTrue(os.path.exists(EC_JSON))
        with open(EC_JSON) as f:
            data = json.load(f)
        self.assertEqual(data.get("is_standard"), "Yes")

    def test_ec_form_json_ref_doctype_salary_slip(self):
        self.assertTrue(os.path.exists(EC_JSON))
        with open(EC_JSON) as f:
            data = json.load(f)
        self.assertEqual(data.get("ref_doctype"), "Salary Slip")

    def test_ec_form_json_module(self):
        self.assertTrue(os.path.exists(EC_JSON))
        with open(EC_JSON) as f:
            data = json.load(f)
        self.assertEqual(data.get("module"), "LHDN Payroll Integration")


class TestECFormColumns(FrappeTestCase):
    """EC Form columns use EC-specific labels, not EA labels."""

    def _get_columns(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.report.ec_form.ec_form import (
            get_columns,
        )
        return get_columns()

    def test_get_columns_returns_list(self):
        cols = self._get_columns()
        self.assertIsInstance(cols, list)
        self.assertGreater(len(cols), 5)

    def test_employer_name_label_uses_ec(self):
        cols = self._get_columns()
        labels = [c.get("label", "") for c in cols]
        # Employer name column should reference EC Form
        ec_labels = [l for l in labels if "EC Form" in l or "EC-" in l]
        self.assertGreater(len(ec_labels), 0, "No EC-specific labels found in columns")

    def test_b12_column_uses_ec_prefix(self):
        cols = self._get_columns()
        labels = [c.get("label", "") for c in cols]
        self.assertTrue(
            any("EC-B12" in l for l in labels),
            "EC-B12 column not found; columns: %s" % labels,
        )

    def test_c1_column_uses_ec_prefix(self):
        cols = self._get_columns()
        labels = [c.get("label", "") for c in cols]
        self.assertTrue(
            any("EC-C1" in l for l in labels),
            "EC-C1 column not found",
        )

    def test_no_bare_b12_ea_label(self):
        """EC Form should NOT have a bare 'B12 – Total Gross' label (EA style)."""
        cols = self._get_columns()
        labels = [c.get("label", "") for c in cols]
        # Must not have a label that starts exactly with "B12" (non-EC)
        bare_b12 = [l for l in labels if l.startswith("B12")]
        self.assertEqual(bare_b12, [], f"Found bare B12 (EA-style) label in EC Form: {bare_b12}")


class TestStatutoryEmployerFixture(FrappeTestCase):
    """custom_is_statutory_employer Check field must be in custom_field.json."""

    def test_custom_field_fixture_exists(self):
        self.assertTrue(
            os.path.exists(CUSTOM_FIELD_JSON),
            f"custom_field.json not found: {CUSTOM_FIELD_JSON}",
        )

    def test_statutory_employer_field_in_fixture(self):
        self.assertTrue(os.path.exists(CUSTOM_FIELD_JSON))
        with open(CUSTOM_FIELD_JSON) as f:
            fields = json.load(f)
        fieldnames = [f.get("fieldname") for f in fields]
        self.assertIn(
            "custom_is_statutory_employer",
            fieldnames,
            "custom_is_statutory_employer not found in custom_field.json",
        )

    def test_statutory_employer_field_is_check(self):
        self.assertTrue(os.path.exists(CUSTOM_FIELD_JSON))
        with open(CUSTOM_FIELD_JSON) as f:
            fields = json.load(f)
        match = next(
            (f for f in fields if f.get("fieldname") == "custom_is_statutory_employer"),
            None,
        )
        self.assertIsNotNone(match, "custom_is_statutory_employer field not found")
        self.assertEqual(match.get("fieldtype"), "Check")

    def test_statutory_employer_field_on_company(self):
        self.assertTrue(os.path.exists(CUSTOM_FIELD_JSON))
        with open(CUSTOM_FIELD_JSON) as f:
            fields = json.load(f)
        match = next(
            (f for f in fields if f.get("fieldname") == "custom_is_statutory_employer"),
            None,
        )
        self.assertIsNotNone(match)
        self.assertEqual(match.get("dt"), "Company")


class TestECFormDataPipeline(FrappeTestCase):
    """EC Form reuses EA Form data pipeline (execute returns columns + data)."""

    def test_execute_returns_tuple(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.report.ec_form.ec_form import (
            execute,
        )
        result = execute({"company": "_Test Company", "year": 2024})
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)

    def test_execute_columns_not_empty(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.report.ec_form.ec_form import (
            execute,
        )
        cols, _data = execute({"company": "_Test Company", "year": 2024})
        self.assertIsInstance(cols, list)
        self.assertGreater(len(cols), 0)

    def test_ec_form_imports_ea_form_get_data(self):
        """EC Form must reuse get_data from ea_form — no duplicated SQL."""
        import inspect
        from lhdn_payroll_integration.lhdn_payroll_integration.report.ec_form import ec_form as ec_mod
        from lhdn_payroll_integration.lhdn_payroll_integration.report.ea_form.ea_form import get_data as ea_get_data
        # ec_form.execute calls get_data which should be the same function as ea_form.get_data
        src = inspect.getsource(ec_mod)
        self.assertIn("from lhdn_payroll_integration", src, "EC Form should import from ea_form")
        self.assertIn("get_data", src)
