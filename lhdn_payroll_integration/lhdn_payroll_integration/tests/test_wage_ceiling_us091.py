"""Tests for US-091: SOCSO/EIS Wage Ceiling Update to RM6,000 (October 2024 Amendment).

Verifies that:
1. SOCSO_WAGE_CEILING = 6000 with October 2024 amendment comment
2. EIS_WAGE_CEILING = 6000 with October 2024 amendment comment
3. RM5,500 wages → SOCSO/EIS computed on RM5,500 (NOT capped at old RM5,000)
4. RM6,500 wages → SOCSO/EIS computed on RM6,000 ceiling (not RM6,500)
"""
from datetime import date

from frappe.tests.utils import FrappeTestCase


class TestSocsoWageCeilingOctober2024(FrappeTestCase):
    """Verify SOCSO wage ceiling is RM6,000 per October 2024 amendment."""

    def setUp(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.utils.statutory_rates import (
            SOCSO_WAGE_CEILING,
            calculate_socso_contribution,
        )
        self.ceiling = SOCSO_WAGE_CEILING
        self.calc = calculate_socso_contribution

    def test_socso_wage_ceiling_is_6000(self):
        """SOCSO_WAGE_CEILING must be 6000.0 (October 2024 amendment)."""
        self.assertEqual(self.ceiling, 6000.0,
                         "SOCSO_WAGE_CEILING must be 6000 (raised from 5000 in October 2024)")

    def test_wages_5500_uses_5500_not_5000(self):
        """RM5,500 wages must compute SOCSO on RM5,500, not old RM5,000 ceiling.

        If still capped at 5000, employee SOCSO would equal the RM5,000 bracket amount.
        The RM5,500 scheduled amount is different (higher) than RM5,000.
        """
        result_5500 = self.calc(5500)
        result_5000 = self.calc(5000)

        # RM5,500 should produce HIGHER contributions than RM5,000
        self.assertGreater(
            result_5500["employee"],
            result_5000["employee"],
            "SOCSO employee contribution at RM5,500 must exceed RM5,000 "
            "(ceiling is 6000, not 5000)",
        )
        self.assertGreater(
            result_5500["employer"],
            result_5000["employer"],
            "SOCSO employer contribution at RM5,500 must exceed RM5,000",
        )

    def test_wages_5500_correct_scheduled_amounts(self):
        """RM5,500 wages → PERKESO First Schedule amounts for RM5,500 bracket."""
        result = self.calc(5500)
        # PERKESO scheduled amounts for RM5,501-RM5,600 bracket
        self.assertAlmostEqual(result["employee"], 13.80, places=2,
                               msg="Employee SOCSO at RM5,500 must match First Schedule")
        self.assertAlmostEqual(result["employer"], 41.50, places=2,
                               msg="Employer SOCSO at RM5,500 must match First Schedule")

    def test_wages_6500_capped_at_6000(self):
        """RM6,500 wages must be capped at RM6,000 ceiling."""
        result_6500 = self.calc(6500)
        result_6000 = self.calc(6000)

        self.assertAlmostEqual(
            result_6500["employee"],
            result_6000["employee"],
            places=2,
            msg="SOCSO at RM6,500 must equal RM6,000 ceiling amount",
        )
        self.assertAlmostEqual(
            result_6500["employer"],
            result_6000["employer"],
            places=2,
            msg="SOCSO employer at RM6,500 must equal RM6,000 ceiling amount",
        )

    def test_wages_6000_not_capped(self):
        """RM6,000 wages (exactly at ceiling) should give ceiling amounts."""
        result = self.calc(6000)
        self.assertAlmostEqual(result["employee"], 15.05, places=2)
        self.assertAlmostEqual(result["employer"], 45.25, places=2)

    def test_wages_above_old_5000_ceiling_below_new_6000(self):
        """Wages from RM5,001 to RM6,000 must now have non-ceiling amounts.

        Before October 2024, these would all equal the RM5,000 ceiling.
        After update, each bracket should return its own scheduled amount.
        """
        result_5001 = self.calc(5001)
        result_5500 = self.calc(5500)
        result_6000 = self.calc(6000)

        # Contributions should be increasing as wages go up (within ceiling range)
        self.assertGreaterEqual(result_5500["employee"], result_5001["employee"])
        self.assertGreaterEqual(result_6000["employee"], result_5500["employee"])


class TestEisWageCeilingOctober2024(FrappeTestCase):
    """Verify EIS wage ceiling is RM6,000 per October 2024 amendment."""

    def setUp(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.utils.statutory_rates import (
            EIS_WAGE_CEILING,
            EIS_RATE,
            calculate_eis_contribution,
        )
        self.ceiling = EIS_WAGE_CEILING
        self.rate = EIS_RATE
        self.calc = calculate_eis_contribution
        # Standard DOB for a 30-year-old employee (not foreign, not age 60+)
        self.dob_30 = date(1994, 1, 15)
        self.payroll_date = date(2025, 1, 15)

    def test_eis_wage_ceiling_is_6000(self):
        """EIS_WAGE_CEILING must be 6000.0 (October 2024 amendment)."""
        self.assertEqual(self.ceiling, 6000.0,
                         "EIS_WAGE_CEILING must be 6000 (raised from 5000 in October 2024)")

    def test_wages_5500_uses_5500_not_5000(self):
        """RM5,500 wages must compute EIS on RM5,500, not old RM5,000 ceiling.

        EIS = 0.2% of insured wages (employee + employer).
        At RM5,500: employee = 5500 * 0.002 = 11.00
        At RM5,000: employee = 5000 * 0.002 = 10.00
        """
        result = self.calc(5500, self.dob_30, is_foreign=False, payroll_date=self.payroll_date)

        # EIS = 0.2% of RM5,500 = 11.00
        expected_eis = round(5500 * self.rate, 2)
        self.assertAlmostEqual(result["employee"], expected_eis, places=2,
                               msg="EIS at RM5,500 must use RM5,500 (not old RM5,000 ceiling)")
        self.assertAlmostEqual(result["employer"], expected_eis, places=2)

    def test_wages_5500_not_equal_to_5000_amount(self):
        """EIS at RM5,500 must NOT equal EIS at RM5,000 (old ceiling behavior)."""
        result_5500 = self.calc(5500, self.dob_30, is_foreign=False, payroll_date=self.payroll_date)
        result_5000 = self.calc(5000, self.dob_30, is_foreign=False, payroll_date=self.payroll_date)

        self.assertGreater(
            result_5500["employee"],
            result_5000["employee"],
            "EIS at RM5,500 must exceed EIS at RM5,000 — old 5000 ceiling no longer applies",
        )

    def test_wages_6500_capped_at_6000(self):
        """RM6,500 wages → EIS computed on RM6,000 ceiling only.

        EIS = 0.2% of RM6,000 = 12.00 (not 0.2% of RM6,500 = 13.00).
        """
        result = self.calc(6500, self.dob_30, is_foreign=False, payroll_date=self.payroll_date)
        expected_eis = round(6000 * self.rate, 2)  # 12.00
        self.assertAlmostEqual(result["employee"], expected_eis, places=2,
                               msg="EIS at RM6,500 must be capped at RM6,000 ceiling")
        self.assertAlmostEqual(result["employer"], expected_eis, places=2)

    def test_wages_6000_at_ceiling(self):
        """RM6,000 wages (at ceiling) → EIS = 12.00."""
        result = self.calc(6000, self.dob_30, is_foreign=False, payroll_date=self.payroll_date)
        self.assertAlmostEqual(result["employee"], 12.00, places=2)
        self.assertAlmostEqual(result["employer"], 12.00, places=2)

    def test_wages_range_5001_to_5999_not_capped_at_5000(self):
        """Wages between RM5,001 and RM5,999 must compute EIS on actual wage (not RM5,000)."""
        for wages in [5100, 5200, 5500, 5800, 5999]:
            result = self.calc(wages, self.dob_30, is_foreign=False, payroll_date=self.payroll_date)
            expected = round(wages * self.rate, 2)
            self.assertAlmostEqual(
                result["employee"],
                expected,
                places=2,
                msg=f"EIS at RM{wages} must use actual wage, not old RM5,000 ceiling",
            )


class TestWageCeilingConstantComments(FrappeTestCase):
    """Verify the constants exist and are exported from statutory_rates module."""

    def test_socso_ceiling_exported(self):
        """SOCSO_WAGE_CEILING must be importable from statutory_rates."""
        from lhdn_payroll_integration.lhdn_payroll_integration.utils.statutory_rates import (
            SOCSO_WAGE_CEILING,
        )
        self.assertEqual(SOCSO_WAGE_CEILING, 6000.0)

    def test_eis_ceiling_exported(self):
        """EIS_WAGE_CEILING must be importable from statutory_rates."""
        from lhdn_payroll_integration.lhdn_payroll_integration.utils.statutory_rates import (
            EIS_WAGE_CEILING,
        )
        self.assertEqual(EIS_WAGE_CEILING, 6000.0)

    def test_both_ceilings_aligned(self):
        """SOCSO and EIS ceilings must be identical (both RM6,000 from October 2024)."""
        from lhdn_payroll_integration.lhdn_payroll_integration.utils.statutory_rates import (
            SOCSO_WAGE_CEILING,
            EIS_WAGE_CEILING,
        )
        self.assertEqual(SOCSO_WAGE_CEILING, EIS_WAGE_CEILING,
                         "SOCSO and EIS ceilings must be equal (both 6000 per October 2024 amendment)")
