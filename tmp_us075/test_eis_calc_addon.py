"""Additional EIS tests for US-075 — added to test_statutory_rates.py.

Tests: calculate_eis_contribution() exemptions and wage ceiling.
"""
from datetime import date, timedelta
from frappe.tests.utils import FrappeTestCase


class TestCalculateEisContribution(FrappeTestCase):
    """Verify calculate_eis_contribution() per EIS Act 2017 Second Schedule."""

    def setUp(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.utils.statutory_rates import (
            calculate_eis_contribution,
        )
        self.calc = calculate_eis_contribution
        # Reference payroll date — use a fixed date to avoid age drift
        self.payroll_date = date(2025, 1, 1)

    def _dob_for_age(self, age):
        """Return a date_of_birth that gives exactly `age` years on payroll_date."""
        return date(self.payroll_date.year - age, self.payroll_date.month, self.payroll_date.day)

    def test_eis_constants_exist(self):
        """EIS_WAGE_CEILING and EIS_RATE must be exported from statutory_rates."""
        from lhdn_payroll_integration.lhdn_payroll_integration.utils.statutory_rates import (
            EIS_RATE,
            EIS_WAGE_CEILING,
        )
        self.assertAlmostEqual(EIS_WAGE_CEILING, 6000.0)
        self.assertAlmostEqual(EIS_RATE, 0.002)

    def test_foreign_worker_returns_zero(self):
        """Foreign worker → both employee and employer EIS = 0."""
        dob = self._dob_for_age(30)
        result = self.calc(5000, dob, is_foreign=True, payroll_date=self.payroll_date)
        self.assertEqual(result["employee"], 0.0)
        self.assertEqual(result["employer"], 0.0)

    def test_age_17_returns_zero(self):
        """Age 17 (under 18) → exempt, both EIS = 0."""
        dob = self._dob_for_age(17)
        result = self.calc(3000, dob, is_foreign=False, payroll_date=self.payroll_date)
        self.assertEqual(result["employee"], 0.0)
        self.assertEqual(result["employer"], 0.0)

    def test_age_18_is_covered(self):
        """Age exactly 18 → covered, EIS > 0."""
        dob = self._dob_for_age(18)
        result = self.calc(3000, dob, is_foreign=False, payroll_date=self.payroll_date)
        self.assertGreater(result["employee"], 0.0)
        self.assertGreater(result["employer"], 0.0)

    def test_age_59_is_covered(self):
        """Age 59 → covered, EIS > 0."""
        dob = self._dob_for_age(59)
        result = self.calc(3000, dob, is_foreign=False, payroll_date=self.payroll_date)
        self.assertGreater(result["employee"], 0.0)

    def test_age_60_returns_zero(self):
        """Age 60 → exempt, both EIS = 0."""
        dob = self._dob_for_age(60)
        result = self.calc(3000, dob, is_foreign=False, payroll_date=self.payroll_date)
        self.assertEqual(result["employee"], 0.0)
        self.assertEqual(result["employer"], 0.0)

    def test_age_65_returns_zero(self):
        """Age 65 → exempt (>= 60), both EIS = 0."""
        dob = self._dob_for_age(65)
        result = self.calc(5000, dob, is_foreign=False, payroll_date=self.payroll_date)
        self.assertEqual(result["employee"], 0.0)
        self.assertEqual(result["employer"], 0.0)

    def test_wages_7000_uses_ceiling_6000(self):
        """Wages RM7,000 → EIS computed on RM6,000 ceiling only (= 6000 * 0.002 = 12.00)."""
        dob = self._dob_for_age(30)
        result = self.calc(7000, dob, is_foreign=False, payroll_date=self.payroll_date)
        expected = round(6000 * 0.002, 2)  # 12.00
        self.assertAlmostEqual(result["employee"], expected, places=2)
        self.assertAlmostEqual(result["employer"], expected, places=2)

    def test_wages_6000_at_ceiling(self):
        """Wages exactly RM6,000 → EIS = 6000 * 0.002 = 12.00."""
        dob = self._dob_for_age(30)
        result = self.calc(6000, dob, is_foreign=False, payroll_date=self.payroll_date)
        self.assertAlmostEqual(result["employee"], 12.00, places=2)
        self.assertAlmostEqual(result["employer"], 12.00, places=2)

    def test_wages_3000_normal(self):
        """Wages RM3,000 → EIS = 3000 * 0.002 = 6.00 each."""
        dob = self._dob_for_age(30)
        result = self.calc(3000, dob, is_foreign=False, payroll_date=self.payroll_date)
        self.assertAlmostEqual(result["employee"], 6.00, places=2)
        self.assertAlmostEqual(result["employer"], 6.00, places=2)

    def test_employee_and_employer_equal(self):
        """Employee and employer EIS contributions must always be equal."""
        dob = self._dob_for_age(35)
        for wages in [1500, 3000, 5000, 6000, 8000]:
            result = self.calc(wages, dob, is_foreign=False, payroll_date=self.payroll_date)
            self.assertAlmostEqual(
                result["employee"], result["employer"], places=2,
                msg=f"Employee/employer EIS should be equal at wages={wages}"
            )
