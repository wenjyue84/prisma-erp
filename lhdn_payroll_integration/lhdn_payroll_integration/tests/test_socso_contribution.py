"""Tests for US-074: SOCSO Contribution Bracketed Table Lookup.

Verifies calculate_socso_contribution() implements PERKESO First Schedule
and SOCSO Borang 8A validation warns for amounts outside scheduled brackets.
"""
from frappe.tests.utils import FrappeTestCase


class TestCalculateSocsoContribution(FrappeTestCase):
    """Verify SOCSO First Schedule table lookup."""

    def setUp(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.utils.statutory_rates import (
            calculate_socso_contribution,
            SOCSO_WAGE_CEILING,
        )
        self.calc = calculate_socso_contribution
        self.ceiling = SOCSO_WAGE_CEILING

    def test_socso_wage_ceiling_is_6000(self):
        """Wage ceiling must be RM6,000 (updated October 2024)."""
        self.assertAlmostEqual(self.ceiling, 6000.0)

    def test_wages_1500_correct_amounts(self):
        """RM1,500 wages → scheduled employee and employer SOCSO amounts."""
        result = self.calc(1500)
        self.assertIn("employee", result)
        self.assertIn("employer", result)
        # Scheduled amount for RM1,500 bracket per PERKESO First Schedule
        self.assertAlmostEqual(result["employee"], 3.80, places=2)
        self.assertAlmostEqual(result["employer"], 11.50, places=2)

    def test_wages_3000_correct_amounts(self):
        """RM3,000 wages → scheduled SOCSO amounts."""
        result = self.calc(3000)
        self.assertAlmostEqual(result["employee"], 7.55, places=2)
        self.assertAlmostEqual(result["employer"], 22.75, places=2)

    def test_wages_5500_correct_amounts(self):
        """RM5,500 wages → scheduled SOCSO amounts."""
        result = self.calc(5500)
        self.assertAlmostEqual(result["employee"], 13.80, places=2)
        self.assertAlmostEqual(result["employer"], 41.50, places=2)

    def test_wages_6000_at_ceiling(self):
        """RM6,000 wages (at ceiling) → highest bracket amounts."""
        result = self.calc(6000)
        self.assertAlmostEqual(result["employee"], 15.05, places=2)
        self.assertAlmostEqual(result["employer"], 45.25, places=2)

    def test_wages_6001_capped_at_ceiling(self):
        """RM6,001 wages (above ceiling) → same as RM6,000 (ceiling applies)."""
        result_at_ceiling = self.calc(6000)
        result_above_ceiling = self.calc(6001)
        self.assertAlmostEqual(result_above_ceiling["employee"], result_at_ceiling["employee"], places=2)
        self.assertAlmostEqual(result_above_ceiling["employer"], result_at_ceiling["employer"], places=2)

    def test_wages_above_ceiling_same_as_ceiling(self):
        """RM10,000 wages → same as RM6,000 ceiling amounts."""
        result_ceiling = self.calc(6000)
        result_high = self.calc(10000)
        self.assertAlmostEqual(result_high["employee"], result_ceiling["employee"], places=2)
        self.assertAlmostEqual(result_high["employer"], result_ceiling["employer"], places=2)

    def test_returns_dict_with_employee_employer_keys(self):
        """Function must return dict with 'employee' and 'employer' keys."""
        result = self.calc(2000)
        self.assertIsInstance(result, dict)
        self.assertIn("employee", result)
        self.assertIn("employer", result)

    def test_employer_amount_greater_than_employee(self):
        """Employer SOCSO contribution is always higher than employee's."""
        for wages in [500, 1000, 2000, 4000, 6000]:
            result = self.calc(wages)
            self.assertGreater(
                result["employer"],
                result["employee"],
                f"Employer SOCSO should exceed employee SOCSO at wages RM{wages}",
            )


class TestSocsoBorangValidation(FrappeTestCase):
    """Verify SOCSO Borang 8A warns when amounts deviate from First Schedule."""

    def setUp(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.report.socso_borang_8a.socso_borang_8a import (
            get_socso_amount_warning,
        )
        self.get_warning = get_socso_amount_warning

    def test_correct_amounts_no_warning(self):
        """Correct First Schedule amounts → no warning."""
        from lhdn_payroll_integration.lhdn_payroll_integration.utils.statutory_rates import (
            calculate_socso_contribution,
        )
        scheduled = calculate_socso_contribution(1500)
        warning = self.get_warning(
            wages=1500,
            employee_socso=scheduled["employee"],
            employer_socso=scheduled["employer"],
        )
        self.assertEqual(warning, "")

    def test_wrong_employee_amount_warns(self):
        """Employee SOCSO >5% below schedule → warning."""
        # RM1,500 → scheduled employee = 3.80; use 2.00 (47% off)
        warning = self.get_warning(wages=1500, employee_socso=2.00, employer_socso=11.50)
        self.assertTrue(len(warning) > 0, "Should warn for wrong employee SOCSO")
        self.assertIn("Employee SOCSO", warning)

    def test_wrong_employer_amount_warns(self):
        """Employer SOCSO >5% below schedule → warning."""
        # RM1,500 → scheduled employer = 11.50; use 5.00 (57% off)
        warning = self.get_warning(wages=1500, employee_socso=3.80, employer_socso=5.00)
        self.assertTrue(len(warning) > 0, "Should warn for wrong employer SOCSO")
        self.assertIn("Employer SOCSO", warning)

    def test_zero_wages_no_warning(self):
        """Zero wages → no warning."""
        warning = self.get_warning(wages=0, employee_socso=0, employer_socso=0)
        self.assertEqual(warning, "")

    def test_above_ceiling_wages_warns_correctly(self):
        """Wages above ceiling → validated against ceiling amounts."""
        from lhdn_payroll_integration.lhdn_payroll_integration.utils.statutory_rates import (
            calculate_socso_contribution,
        )
        # RM7,000 wages should be validated against RM6,000 ceiling amounts
        scheduled = calculate_socso_contribution(7000)  # capped at 6000
        warning = self.get_warning(
            wages=7000,
            employee_socso=scheduled["employee"],
            employer_socso=scheduled["employer"],
        )
        self.assertEqual(warning, "")

    def test_columns_include_socso_warning(self):
        """US-074: SOCSO Borang 8A report must include socso_warning column."""
        from lhdn_payroll_integration.lhdn_payroll_integration.report.socso_borang_8a.socso_borang_8a import (
            get_columns,
        )
        cols = get_columns()
        fieldnames = [c["fieldname"] for c in cols]
        self.assertIn("socso_warning", fieldnames)
