"""Additional EIS Monthly validation tests for US-075.

Tests get_eis_contribution_warning() and that the report column exists.
"""
from datetime import date
from frappe.tests.utils import FrappeTestCase


class TestEisMonthlyValidation(FrappeTestCase):
    """Tests for get_eis_contribution_warning() — US-075."""

    def setUp(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.lhdn_payroll_integration.report.eis_monthly.eis_monthly import (
            get_eis_contribution_warning,
        )
        self.warn = get_eis_contribution_warning
        self.payroll_date = date(2025, 1, 1)

    def _dob_for_age(self, age):
        return date(self.payroll_date.year - age, self.payroll_date.month, self.payroll_date.day)

    def test_columns_include_eis_warning(self):
        """US-075: EIS monthly report must include eis_contribution_warning column."""
        from lhdn_payroll_integration.lhdn_payroll_integration.lhdn_payroll_integration.report.eis_monthly.eis_monthly import (
            get_columns,
        )
        cols = get_columns()
        fieldnames = [c["fieldname"] for c in cols]
        self.assertIn("eis_contribution_warning", fieldnames)

    def test_foreign_worker_with_eis_warns(self):
        """Foreign worker incorrectly has EIS deducted → warning issued."""
        dob = self._dob_for_age(30)
        warning = self.warn(
            wages=5000, date_of_birth=dob, is_foreign=True,
            actual_employee=10.0, actual_employer=10.0
        )
        self.assertGreater(len(warning), 0)
        self.assertIn("foreign", warning.lower())

    def test_foreign_worker_no_eis_no_warning(self):
        """Foreign worker with zero EIS → no warning."""
        dob = self._dob_for_age(30)
        warning = self.warn(
            wages=5000, date_of_birth=dob, is_foreign=True,
            actual_employee=0.0, actual_employer=0.0
        )
        self.assertEqual(warning, "")

    def test_age_17_with_eis_warns(self):
        """Employee aged 17 (exempt) incorrectly has EIS → warning."""
        dob = self._dob_for_age(17)
        warning = self.warn(
            wages=3000, date_of_birth=dob, is_foreign=False,
            actual_employee=6.0, actual_employer=6.0
        )
        self.assertGreater(len(warning), 0)
        self.assertIn("exempt", warning.lower())

    def test_age_60_with_eis_warns(self):
        """Employee aged 60 (exempt) incorrectly has EIS → warning."""
        dob = self._dob_for_age(60)
        warning = self.warn(
            wages=3000, date_of_birth=dob, is_foreign=False,
            actual_employee=6.0, actual_employer=6.0
        )
        self.assertGreater(len(warning), 0)
        self.assertIn("exempt", warning.lower())

    def test_wage_7000_correct_ceiling_no_warning(self):
        """Wages RM7,000 but EIS correctly computed on RM6,000 ceiling → no warning."""
        dob = self._dob_for_age(30)
        correct_eis = round(6000 * 0.002, 2)  # 12.00
        warning = self.warn(
            wages=7000, date_of_birth=dob, is_foreign=False,
            actual_employee=correct_eis, actual_employer=correct_eis
        )
        self.assertEqual(warning, "")

    def test_wage_7000_wrong_ceiling_warns(self):
        """Wages RM7,000 with EIS on full 7000 (not capped) → warning."""
        dob = self._dob_for_age(30)
        wrong_eis = round(7000 * 0.002, 2)  # 14.00 — should be 12.00
        warning = self.warn(
            wages=7000, date_of_birth=dob, is_foreign=False,
            actual_employee=wrong_eis, actual_employer=wrong_eis
        )
        self.assertGreater(len(warning), 0)
        self.assertIn("ceiling", warning.lower())

    def test_correct_contribution_no_warning(self):
        """Correctly computed EIS → no warning."""
        dob = self._dob_for_age(30)
        correct_eis = round(5000 * 0.002, 2)  # 10.00
        warning = self.warn(
            wages=5000, date_of_birth=dob, is_foreign=False,
            actual_employee=correct_eis, actual_employer=correct_eis
        )
        self.assertEqual(warning, "")

    def test_no_dob_skips_validation(self):
        """Missing date_of_birth → no warning (cannot validate)."""
        warning = self.warn(
            wages=5000, date_of_birth=None, is_foreign=False,
            actual_employee=10.0, actual_employer=10.0
        )
        self.assertEqual(warning, "")
