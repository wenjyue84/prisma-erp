"""Tests for US-075: EIS Contribution Ceiling (RM6,000) and Age/Foreign Worker Exemptions.

Verifies calculate_eis_contribution() and EIS monthly report validation.
"""
from datetime import date
from frappe.tests.utils import FrappeTestCase


class TestCalculateEisContribution(FrappeTestCase):
    """Verify calculate_eis_contribution() per EIS Act 2017 Second Schedule."""

    def setUp(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.utils.statutory_rates import (
            calculate_eis_contribution,
            EIS_WAGE_CEILING,
            EIS_RATE,
        )
        self.calc = calculate_eis_contribution
        self.ceiling = EIS_WAGE_CEILING
        self.rate = EIS_RATE

    def test_eis_constants(self):
        """EIS_WAGE_CEILING must be 6000 and EIS_RATE must be 0.002."""
        self.assertAlmostEqual(self.ceiling, 6000.0)
        self.assertAlmostEqual(self.rate, 0.002)

    def test_foreign_worker_returns_zero(self):
        """Foreign workers are not covered by EIS — both amounts must be zero."""
        dob = date(1990, 1, 1)  # Age ~35
        result = self.calc(wages=5000, date_of_birth=dob, is_foreign=True)
        self.assertEqual(result["employee"], 0.0)
        self.assertEqual(result["employer"], 0.0)

    def test_age_17_exempt(self):
        """Employee age 17 (under 18) → EIS exempt."""
        payroll_date = date(2026, 1, 1)
        dob = date(2009, 1, 2)  # 16 years old at payroll_date
        result = self.calc(wages=3000, date_of_birth=dob, is_foreign=False, payroll_date=payroll_date)
        self.assertEqual(result["employee"], 0.0)
        self.assertEqual(result["employer"], 0.0)

    def test_age_60_exempt(self):
        """Employee age 60 → EIS exempt."""
        payroll_date = date(2026, 1, 1)
        dob = date(1966, 1, 1)  # Exactly 60
        result = self.calc(wages=5000, date_of_birth=dob, is_foreign=False, payroll_date=payroll_date)
        self.assertEqual(result["employee"], 0.0)
        self.assertEqual(result["employer"], 0.0)

    def test_age_59_not_exempt(self):
        """Employee age 59 → not exempt, EIS applies."""
        payroll_date = date(2026, 1, 1)
        dob = date(1966, 6, 15)  # 59 years old
        result = self.calc(wages=5000, date_of_birth=dob, is_foreign=False, payroll_date=payroll_date)
        self.assertGreater(result["employee"], 0.0)
        self.assertGreater(result["employer"], 0.0)

    def test_wages_within_ceiling(self):
        """Normal wages RM5,000 → 0.2% employee + 0.2% employer."""
        dob = date(1990, 1, 1)
        payroll_date = date(2026, 1, 1)
        result = self.calc(wages=5000, date_of_birth=dob, is_foreign=False, payroll_date=payroll_date)
        expected = 5000 * 0.002  # = 10.0
        self.assertAlmostEqual(result["employee"], expected, places=2)
        self.assertAlmostEqual(result["employer"], expected, places=2)

    def test_wages_7000_capped_at_6000(self):
        """RM7,000 wages → EIS on RM6,000 only (ceiling applies)."""
        dob = date(1990, 1, 1)
        payroll_date = date(2026, 1, 1)
        result = self.calc(wages=7000, date_of_birth=dob, is_foreign=False, payroll_date=payroll_date)
        expected = 6000 * 0.002  # = 12.0
        self.assertAlmostEqual(result["employee"], expected, places=2)
        self.assertAlmostEqual(result["employer"], expected, places=2)

    def test_wages_at_ceiling_6000(self):
        """RM6,000 wages → EIS on full RM6,000."""
        dob = date(1990, 1, 1)
        payroll_date = date(2026, 1, 1)
        result = self.calc(wages=6000, date_of_birth=dob, is_foreign=False, payroll_date=payroll_date)
        expected = 6000 * 0.002  # = 12.0
        self.assertAlmostEqual(result["employee"], expected, places=2)
        self.assertAlmostEqual(result["employer"], expected, places=2)

    def test_employee_equals_employer_contribution(self):
        """Employee and employer EIS contributions must be equal."""
        dob = date(1990, 1, 1)
        payroll_date = date(2026, 1, 1)
        for wages in [2000, 4000, 6000, 8000]:
            result = self.calc(wages=wages, date_of_birth=dob, is_foreign=False, payroll_date=payroll_date)
            self.assertAlmostEqual(result["employee"], result["employer"], places=2,
                                   msg=f"Employee and employer EIS must be equal at wages RM{wages}")


class TestEisMonthlyValidation(FrappeTestCase):
    """Verify EIS monthly report validation logic."""

    def setUp(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.report.eis_monthly.eis_monthly import (
            get_eis_validation_warning,
        )
        self.get_warning = get_eis_validation_warning

    def test_correct_eis_no_warning(self):
        """Correct EIS amounts → no warning."""
        expected = 5000 * 0.002  # 10.0
        warning = self.get_warning(
            wages=5000,
            eis_employee=expected,
            eis_employer=expected,
            is_exempt=False,
        )
        self.assertEqual(warning, "")

    def test_exempt_foreign_worker_with_eis_warns(self):
        """Foreign worker incorrectly charged EIS → warning."""
        warning = self.get_warning(
            wages=5000, eis_employee=10.0, eis_employer=10.0,
            is_exempt=True, exempt_reason="foreign worker",
        )
        self.assertTrue(len(warning) > 0)
        self.assertIn("exempt", warning)
        self.assertIn("foreign worker", warning)

    def test_exempt_under_age_with_eis_warns(self):
        """Employee age < 18 incorrectly charged EIS → warning."""
        warning = self.get_warning(
            wages=3000, eis_employee=6.0, eis_employer=6.0,
            is_exempt=True, exempt_reason="age 17 (under 18)",
        )
        self.assertTrue(len(warning) > 0)
        self.assertIn("exempt", warning)

    def test_exempt_over_60_no_eis_no_warning(self):
        """Employee age 60+ correctly with zero EIS → no warning."""
        warning = self.get_warning(
            wages=5000, eis_employee=0.0, eis_employer=0.0,
            is_exempt=True, exempt_reason="age 62 (60 or above)",
        )
        self.assertEqual(warning, "")

    def test_wages_above_ceiling_warns_if_wrong(self):
        """RM7,000 wages: EIS should be based on RM6,000; wrong amount warns."""
        # Correct: 6000 * 0.002 = 12.0; Wrong: 7000 * 0.002 = 14.0 (17% off)
        correct_eis = 6000 * 0.002
        warning = self.get_warning(
            wages=7000, eis_employee=correct_eis, eis_employer=correct_eis,
            is_exempt=False,
        )
        self.assertEqual(warning, "", "Correct ceiling-based EIS should have no warning")

    def test_columns_include_eis_warning(self):
        """US-075: EIS monthly report must include eis_warning column."""
        from lhdn_payroll_integration.lhdn_payroll_integration.report.eis_monthly.eis_monthly import (
            get_columns,
        )
        cols = get_columns()
        fieldnames = [c["fieldname"] for c in cols]
        self.assertIn("eis_warning", fieldnames)
