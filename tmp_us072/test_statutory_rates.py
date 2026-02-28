"""Tests for US-073: EPF Employer Rate Differential.

Also covers utils/statutory_rates.py as shared module.
"""
from frappe.tests.utils import FrappeTestCase


class TestCalculateEpfEmployerRate(FrappeTestCase):
    """Verify calculate_epf_employer_rate() returns correct statutory rate."""

    def setUp(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.utils.statutory_rates import (
            calculate_epf_employer_rate,
        )
        self.calc = calculate_epf_employer_rate

    def test_epf_constants_exist(self):
        """Module must export EPF rate constants."""
        from lhdn_payroll_integration.lhdn_payroll_integration.utils.statutory_rates import (
            EPF_EMPLOYER_RATE_HIGH,
            EPF_EMPLOYER_RATE_LOW,
            EPF_LOWER_SALARY_THRESHOLD,
        )
        self.assertAlmostEqual(EPF_EMPLOYER_RATE_HIGH, 0.13)
        self.assertAlmostEqual(EPF_EMPLOYER_RATE_LOW, 0.12)
        self.assertAlmostEqual(EPF_LOWER_SALARY_THRESHOLD, 5000.0)

    def test_rate_at_5000_is_13_percent(self):
        """Employee at exactly RM5,000 → employer contributes 13%."""
        rate = self.calc(5000)
        self.assertAlmostEqual(rate, 0.13)

    def test_rate_below_5000_is_13_percent(self):
        """Employee at RM3,000 (below threshold) → 13% employer rate."""
        rate = self.calc(3000)
        self.assertAlmostEqual(rate, 0.13)

    def test_rate_at_5001_is_12_percent(self):
        """Employee at RM5,001 (above threshold) → 12% employer rate."""
        rate = self.calc(5001)
        self.assertAlmostEqual(rate, 0.12)

    def test_rate_at_high_salary_is_12_percent(self):
        """Employee at RM15,000 → 12% employer rate."""
        rate = self.calc(15000)
        self.assertAlmostEqual(rate, 0.12)

    def test_rate_at_zero_is_13_percent(self):
        """Zero wages → 13% (threshold logic: 0 <= 5000)."""
        rate = self.calc(0)
        self.assertAlmostEqual(rate, 0.13)


class TestEpfBorangAValidation(FrappeTestCase):
    """Verify EPF Borang A report validates employer rate per employee."""

    def setUp(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.report.epf_borang_a.epf_borang_a import (
            get_epf_employer_rate_warning,
        )
        self.get_warning = get_epf_employer_rate_warning

    def test_employee_5000_employer_13pct_no_warning(self):
        """RM5,000 wages with correct 13% employer EPF → no warning."""
        employer_epf = 5000 * 0.13  # 650
        warning = self.get_warning(wages=5000, employer_epf=employer_epf)
        self.assertEqual(warning, "")

    def test_employee_5000_employer_12pct_warns(self):
        """RM5,000 wages with 12% employer EPF → warning (should be 13%)."""
        employer_epf = 5000 * 0.12  # 600 — wrong, should be 650
        warning = self.get_warning(wages=5000, employer_epf=employer_epf)
        self.assertTrue(len(warning) > 0, "Should warn for 12% when 13% is required")
        self.assertIn("13%", warning)

    def test_employee_5001_employer_12pct_no_warning(self):
        """RM5,001 wages with correct 12% employer EPF → no warning."""
        employer_epf = 5001 * 0.12
        warning = self.get_warning(wages=5001, employer_epf=employer_epf)
        self.assertEqual(warning, "")

    def test_employee_5001_employer_13pct_warns(self):
        """RM5,001 wages with 13% employer EPF → no warning (above threshold = 12%, overpaying is within tolerance of 8.33%)."""
        # 13% vs 12% = 8.33% deviation, > 5% tolerance → should warn
        employer_epf = 5001 * 0.13
        warning = self.get_warning(wages=5001, employer_epf=employer_epf)
        self.assertTrue(len(warning) > 0, "Deviation > 5% tolerance should warn")

    def test_within_tolerance_no_warning(self):
        """Employer EPF within 5% tolerance → no warning."""
        # RM5,000 wages at 13% = 650; 2% overpay = 663 → within 5% tolerance
        employer_epf = 5000 * 0.13 * 1.02
        warning = self.get_warning(wages=5000, employer_epf=employer_epf)
        self.assertEqual(warning, "")

    def test_zero_wages_no_warning(self):
        """Zero wages → no warning (no meaningful check)."""
        warning = self.get_warning(wages=0, employer_epf=0)
        self.assertEqual(warning, "")

    def test_columns_include_epf_rate_warning(self):
        """US-073: EPF Borang A report must include epf_rate_warning column."""
        from lhdn_payroll_integration.lhdn_payroll_integration.report.epf_borang_a.epf_borang_a import (
            get_columns,
        )
        cols = get_columns()
        fieldnames = [c["fieldname"] for c in cols]
        self.assertIn("epf_rate_warning", fieldnames)
