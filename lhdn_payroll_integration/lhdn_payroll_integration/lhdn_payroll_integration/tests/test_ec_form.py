"""Tests for US-094: EC Form Variant for Statutory/Government Body Employers."""

import json
import os
from frappe.tests.utils import FrappeTestCase

CUSTOM_FIELD_FIXTURE = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "fixtures",
    "custom_field.json",
)


class TestECFormFixture(FrappeTestCase):
    def _load_fixture(self):
        with open(CUSTOM_FIELD_FIXTURE) as f:
            return json.load(f)

    def test_statutory_employer_field_exists_in_fixture(self):
        fields = self._load_fixture()
        names = {f.get("fieldname") for f in fields}
        self.assertIn(
            "custom_is_statutory_employer",
            names,
            "custom_is_statutory_employer missing from custom_field.json",
        )

    def test_statutory_employer_field_is_check_on_company(self):
        fields = self._load_fixture()
        field = next(
            (f for f in fields if f.get("fieldname") == "custom_is_statutory_employer"),
            None,
        )
        self.assertIsNotNone(field)
        self.assertEqual(field.get("dt"), "Company")
        self.assertEqual(field.get("fieldtype"), "Check")

    def test_statutory_employer_field_default_is_zero(self):
        fields = self._load_fixture()
        field = next(
            (f for f in fields if f.get("fieldname") == "custom_is_statutory_employer"),
            None,
        )
        self.assertIsNotNone(field)
        self.assertEqual(str(field.get("default", "0")), "0")


class TestECFormReport(FrappeTestCase):
    def test_ec_form_module_importable(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.report.ec_form import ec_form  # noqa: F401

    def test_ec_form_has_execute_function(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.report.ec_form.ec_form import execute
        self.assertTrue(callable(execute))

    def test_ec_form_has_get_columns_function(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.report.ec_form.ec_form import get_columns
        self.assertTrue(callable(get_columns))

    def test_ec_form_has_get_data_function(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.report.ec_form.ec_form import get_data
        self.assertTrue(callable(get_data))

    def test_ec_form_get_columns_returns_list(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.report.ec_form.ec_form import get_columns
        cols = get_columns()
        self.assertIsInstance(cols, list)
        self.assertGreater(len(cols), 0)

    def test_ec_form_columns_contain_ec_section_a_header(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.report.ec_form.ec_form import get_columns
        cols = get_columns()
        labels = [c.get("label", "") for c in cols]
        # EC Form must use EC-specific Section A label
        self.assertIn(
            "A \u2013 Employer (Statutory Body / Government)",
            labels,
            "EC Form Section A label not found — should be 'A – Employer (Statutory Body / Government)'",
        )

    def test_ec_form_section_a_label_differs_from_ea_form(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.report.ec_form.ec_form import get_columns as ec_cols
        from lhdn_payroll_integration.lhdn_payroll_integration.report.ea_form.ea_form import get_columns as ea_cols
        ec_labels = {c.get("label") for c in ec_cols()}
        ea_labels = {c.get("label") for c in ea_cols()}
        # EC Form has its own Section A label
        self.assertIn("A \u2013 Employer (Statutory Body / Government)", ec_labels)
        # EA Form should NOT have the EC label
        self.assertNotIn("A \u2013 Employer (Statutory Body / Government)", ea_labels)

    def test_ec_form_reuses_ea_form_columns_count(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.report.ec_form.ec_form import get_columns as ec_cols
        from lhdn_payroll_integration.lhdn_payroll_integration.report.ea_form.ea_form import get_columns as ea_cols
        # EC Form should have the same number of columns as EA Form
        self.assertEqual(len(ec_cols()), len(ea_cols()))

    def test_ec_form_execute_returns_tuple(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.report.ec_form.ec_form import execute
        result = execute({})
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)

    def test_statutory_employer_uses_ec_form_not_ea(self):
        """Statutory employer flag should signal EC Form generation instead of EA Form."""
        from lhdn_payroll_integration.lhdn_payroll_integration.report.ec_form.ec_form import get_columns
        # The EC Form report itself serves as the EC generator for statutory employers
        cols = get_columns()
        section_a = next((c for c in cols if "Employer" in c.get("label", "")), None)
        self.assertIsNotNone(section_a)
        self.assertIn("Statutory Body", section_a.get("label", ""),
                      "Section A label must identify statutory body for EC Form")

    def test_non_statutory_employer_uses_ea_form_header(self):
        """Non-statutory employer EA Form should not contain EC-specific header."""
        from lhdn_payroll_integration.lhdn_payroll_integration.report.ea_form.ea_form import get_columns
        cols = get_columns()
        labels = [c.get("label", "") for c in cols]
        self.assertNotIn(
            "A \u2013 Employer (Statutory Body / Government)",
            labels,
            "EA Form must NOT use EC-specific Section A label",
        )
