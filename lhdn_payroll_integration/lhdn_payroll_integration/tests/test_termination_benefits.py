"""Tests for US-082: Termination and Lay-Off Benefits Calculator.

Covers:
1. calculate_termination_benefits: 1y6m -> 10 days/year rate
2. calculate_termination_benefits: 3 years -> 15 days/year rate
3. calculate_termination_benefits: 7 years -> 20 days/year rate
4. Daily rate derived from CTC / 12 / 26
5. Zero result when no joining date
6. CP22A.validate() populates years_of_service and statutory_minimum fields
7. CP22A.validate() sets underpayment_warning when actual < statutory min
8. CP22A.validate() clears warning when actual >= statutory min
"""
import frappe
from frappe.tests.utils import FrappeTestCase
from unittest.mock import MagicMock, patch


class TestCalculateTerminationBenefits(FrappeTestCase):
    """Unit tests for calculate_termination_benefits()."""

    def _make_employee(self, date_of_joining, ctc=156000.0):
        """Helper: mock Employee with date_of_joining and CTC."""
        emp = MagicMock()
        emp.date_of_joining = date_of_joining
        emp.ctc = ctc  # Annual CTC; monthly = ctc / 12
        return emp

    def test_rate_10_days_for_under_2_years(self):
        """1 year 6 months of service -> 10 days/year rate (< 2 years bracket)."""
        from lhdn_payroll_integration.utils.employment_compliance import calculate_termination_benefits

        employee = self._make_employee("2022-01-01", ctc=72000.0)  # RM6,000/month
        termination_date = "2023-07-01"  # ~18 months (1.5 years)

        result = calculate_termination_benefits(employee, termination_date)

        self.assertEqual(result["rate_days"], 10)
        self.assertAlmostEqual(result["years_of_service"], 1.5, delta=0.05)

    def test_rate_15_days_for_2_to_5_years(self):
        """3 years of service -> 15 days/year rate (2-5 years bracket)."""
        from lhdn_payroll_integration.utils.employment_compliance import calculate_termination_benefits

        employee = self._make_employee("2020-01-01", ctc=72000.0)
        termination_date = "2023-01-01"  # exactly 3 years

        result = calculate_termination_benefits(employee, termination_date)

        self.assertEqual(result["rate_days"], 15)
        self.assertAlmostEqual(result["years_of_service"], 3.0, delta=0.05)

    def test_rate_20_days_for_over_5_years(self):
        """7 years of service -> 20 days/year rate (> 5 years bracket)."""
        from lhdn_payroll_integration.utils.employment_compliance import calculate_termination_benefits

        employee = self._make_employee("2015-01-01", ctc=72000.0)
        termination_date = "2022-01-01"  # exactly 7 years

        result = calculate_termination_benefits(employee, termination_date)

        self.assertEqual(result["rate_days"], 20)
        self.assertAlmostEqual(result["years_of_service"], 7.0, delta=0.05)

    def test_daily_rate_is_monthly_over_26(self):
        """daily_rate = (CTC / 12) / 26."""
        from lhdn_payroll_integration.utils.employment_compliance import calculate_termination_benefits

        # CTC = 72,000/year -> monthly = 6,000 -> daily = 6000/26 ~ 230.77
        employee = self._make_employee("2020-01-01", ctc=72000.0)
        termination_date = "2023-01-01"  # 3 years

        result = calculate_termination_benefits(employee, termination_date)

        expected_daily = (72000.0 / 12) / 26
        self.assertAlmostEqual(result["daily_rate"], expected_daily, places=2)

    def test_statutory_minimum_calculation(self):
        """statutory_minimum = daily_rate * rate_days * years_of_service (3 years, 15 days)."""
        from lhdn_payroll_integration.utils.employment_compliance import calculate_termination_benefits

        employee = self._make_employee("2020-01-01", ctc=72000.0)
        termination_date = "2023-01-01"  # 3 years -> 15 days/year

        result = calculate_termination_benefits(employee, termination_date)

        # daily_rate = 6000/26; statutory = daily * 15 * years_of_service
        expected_daily = 6000.0 / 26
        expected_statutory = expected_daily * 15 * result["years_of_service"]
        self.assertAlmostEqual(result["statutory_minimum"], expected_statutory, delta=1.0)

    def test_returns_zero_when_no_joining_date(self):
        """Returns zeros when employee.date_of_joining is None."""
        from lhdn_payroll_integration.utils.employment_compliance import calculate_termination_benefits

        employee = self._make_employee(None, ctc=60000.0)
        result = calculate_termination_benefits(employee, "2023-01-01")

        self.assertEqual(result["statutory_minimum"], 0.0)
        self.assertEqual(result["years_of_service"], 0.0)

    def test_returns_zero_when_termination_before_joining(self):
        """Returns zeros when termination_date <= date_of_joining (invalid input)."""
        from lhdn_payroll_integration.utils.employment_compliance import calculate_termination_benefits

        employee = self._make_employee("2023-06-01", ctc=60000.0)
        result = calculate_termination_benefits(employee, "2022-01-01")

        self.assertEqual(result["statutory_minimum"], 0.0)

    def test_exactly_2_years_uses_15_day_rate(self):
        """Exactly 2.0 years of service -> 15 days/year (>= 2 years bracket)."""
        from lhdn_payroll_integration.utils.employment_compliance import calculate_termination_benefits

        employee = self._make_employee("2021-01-01", ctc=60000.0)
        termination_date = "2023-01-01"  # ~2.0 years

        result = calculate_termination_benefits(employee, termination_date)

        self.assertEqual(result["rate_days"], 15)

    def test_exactly_5_years_uses_20_day_rate(self):
        """Exactly 5.0 years of service -> 20 days/year (> 5 years bracket)."""
        from lhdn_payroll_integration.utils.employment_compliance import calculate_termination_benefits

        employee = self._make_employee("2018-01-01", ctc=60000.0)
        termination_date = "2023-01-01"  # ~5.0 years

        result = calculate_termination_benefits(employee, termination_date)

        self.assertEqual(result["rate_days"], 20)


class TestCP22ATerminationBenefitsIntegration(FrappeTestCase):
    """Tests for CP22A.validate() integration with termination benefits calculator."""

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.lhdn_cp22a.lhdn_cp22a.frappe")
    def test_validate_populates_termination_fields(self, mock_frappe):
        """CP22A.validate() populates years_of_service and statutory_minimum_termination_pay."""
        from lhdn_payroll_integration.lhdn_payroll_integration.doctype.lhdn_cp22a.lhdn_cp22a import LHDNCP22A

        # Mock employee doc
        mock_employee = MagicMock()
        mock_employee.date_of_joining = "2020-01-01"
        mock_employee.ctc = 72000.0
        mock_employee.date_of_birth = "1970-01-15"
        mock_frappe.get_doc.return_value = mock_employee

        doc = LHDNCP22A({
            "doctype": "LHDN CP22A",
            "employee": "HR-EMP-00100",
            "cessation_date": "2023-01-01",  # 3 years service
            "date_of_birth": "1970-01-15",
            "actual_termination_pay": 0,
        })

        doc.validate()

        # years_of_service should be around 3.0
        self.assertAlmostEqual(doc.years_of_service, 3.0, delta=0.1)
        # statutory minimum should be positive
        self.assertGreater(doc.statutory_minimum_termination_pay, 0)

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.lhdn_cp22a.lhdn_cp22a.frappe")
    def test_validate_sets_underpayment_warning(self, mock_frappe):
        """CP22A.validate() sets underpayment_warning when actual < statutory minimum."""
        from lhdn_payroll_integration.lhdn_payroll_integration.doctype.lhdn_cp22a.lhdn_cp22a import LHDNCP22A

        mock_employee = MagicMock()
        mock_employee.date_of_joining = "2020-01-01"
        mock_employee.ctc = 72000.0  # monthly 6000; daily 230.77; 3yr x 15d ~ 10,384
        mock_employee.date_of_birth = "1970-01-15"
        mock_frappe.get_doc.return_value = mock_employee

        doc = LHDNCP22A({
            "doctype": "LHDN CP22A",
            "employee": "HR-EMP-00101",
            "cessation_date": "2023-01-01",
            "date_of_birth": "1970-01-15",
            "actual_termination_pay": 500.0,  # Way below statutory minimum
        })

        doc.validate()

        self.assertTrue(len(doc.underpayment_warning) > 0)
        self.assertIn("below the statutory minimum", doc.underpayment_warning)

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.lhdn_cp22a.lhdn_cp22a.frappe")
    def test_validate_clears_warning_when_actual_meets_minimum(self, mock_frappe):
        """CP22A.validate() clears underpayment_warning when actual >= statutory minimum."""
        from lhdn_payroll_integration.lhdn_payroll_integration.doctype.lhdn_cp22a.lhdn_cp22a import LHDNCP22A

        mock_employee = MagicMock()
        mock_employee.date_of_joining = "2020-01-01"
        mock_employee.ctc = 72000.0
        mock_employee.date_of_birth = "1970-01-15"
        mock_frappe.get_doc.return_value = mock_employee

        doc = LHDNCP22A({
            "doctype": "LHDN CP22A",
            "employee": "HR-EMP-00102",
            "cessation_date": "2023-01-01",
            "date_of_birth": "1970-01-15",
            "actual_termination_pay": 50000.0,  # Well above statutory minimum
        })

        doc.validate()

        self.assertEqual(doc.underpayment_warning, "")
