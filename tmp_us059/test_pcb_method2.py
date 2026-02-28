"""Tests for US-059: MTD Method 2 (Year-to-Date Recalculation Formula).

Verifies:
- calculate_pcb_method2() implements LHDN PCB Guidelines Appendix D correctly
- For constant-income employees, Method 2 annual total matches Method 1
- Method 2 smooths PCB across months for variable-income employees
- Edge cases: first month, last month, non-resident, rebate-eligible income
- populate_ytd_pcb_fields() populates custom_ytd_gross and custom_ytd_pcb_deducted
"""
from unittest.mock import MagicMock, patch

from frappe.tests.utils import FrappeTestCase

from lhdn_payroll_integration.services.pcb_calculator import (
    calculate_pcb,
    calculate_pcb_method2,
    populate_ytd_pcb_fields,
    _compute_tax_on_chargeable_income,
)


class TestCalculatePcbMethod2Basic(FrappeTestCase):
    """Unit tests for calculate_pcb_method2() core formula."""

    def test_zero_income_returns_zero(self):
        """Zero YTD gross yields zero PCB for any month."""
        result = calculate_pcb_method2(0, 0, 1)
        self.assertEqual(result, 0.0)

    def test_negative_income_returns_zero(self):
        """Negative YTD gross yields zero PCB."""
        result = calculate_pcb_method2(-5000, 0, 1)
        self.assertEqual(result, 0.0)

    def test_income_below_relief_returns_zero(self):
        """If annualised income is below self-relief (RM9,000), PCB is zero."""
        # Month 1: ytd_gross=500, annualised=6,000 < 9,000 relief → 0
        result = calculate_pcb_method2(500, 0, 1)
        self.assertEqual(result, 0.0)

    def test_first_month_matches_method1(self):
        """In month 1, Method 2 with no prior deductions equals Method 1.

        Method 1: annual_tax / 12
        Method 2 month 1: (annual_tax - 0) / 12  (remaining = 13-1=12)
        Should be equal.
        """
        # Annual income RM60,000, single resident
        monthly_gross = 5_000
        annual_income = monthly_gross * 12  # 60,000

        m1 = calculate_pcb(annual_income, resident=True)
        m2 = calculate_pcb_method2(monthly_gross, 0.0, 1, resident=True)
        self.assertAlmostEqual(m1, m2, places=2)

    def test_last_month_clears_remaining_liability(self):
        """In month 12, Method 2 deducts all remaining tax liability.

        remaining_months = 13 - 12 = 1
        pcb = (annual_tax - ytd_pcb_deducted) / 1 = outstanding amount
        """
        monthly_gross = 5_000
        annual_income = monthly_gross * 12  # 60,000
        annual_tax = _compute_tax_on_chargeable_income(annual_income - 9_000)  # 1930
        # Simulate 11 months already paid at Method 1 rate
        m1_monthly = calculate_pcb(annual_income, resident=True)
        ytd_11_months = round(m1_monthly * 11, 2)
        ytd_gross_11 = monthly_gross * 11

        m2_month12 = calculate_pcb_method2(
            ytd_gross_11 + monthly_gross,  # full year gross
            ytd_11_months,
            12,
            resident=True,
        )
        # month 12 should clear the remaining liability
        expected = max(0.0, round(annual_tax - ytd_11_months, 2))
        self.assertAlmostEqual(m2_month12, expected, delta=1.0)

    def test_month_number_clamped_to_1_12(self):
        """month_number is clamped to valid range [1, 12]."""
        # Month 0 should behave as month 1
        r0 = calculate_pcb_method2(5_000, 0, 0)
        r1 = calculate_pcb_method2(5_000, 0, 1)
        self.assertEqual(r0, r1)

        # Month 13 should behave as month 12
        r13 = calculate_pcb_method2(60_000, 0, 13)
        r12 = calculate_pcb_method2(60_000, 0, 12)
        self.assertEqual(r13, r12)


class TestCalculatePcbMethod2ConstantIncome(FrappeTestCase):
    """Test that Method 2 produces the same annual total as Method 1 for constant income."""

    def _simulate_12_months_m2(self, monthly_gross, category=None, tp1=0.0):
        """Simulate 12 months of Method 2 PCB for constant-income employee."""
        ytd_gross = 0.0
        ytd_pcb = 0.0
        total = 0.0
        for month in range(1, 13):
            ytd_gross += monthly_gross
            pcb = calculate_pcb_method2(
                ytd_gross, ytd_pcb, month,
                tp1_reliefs=tp1, category=category, resident=True,
            )
            total += pcb
            ytd_pcb += pcb
        return round(total, 2)

    def test_constant_income_annual_total_matches_method1(self):
        """For constant monthly income, Method 2 total == Method 1 total (within RM1).

        Single resident, annual RM60,000:
        Method 1: RM1,930 / 12 = RM160.83/month → RM1,930 annual
        Method 2 should also sum to ~RM1,930
        """
        monthly_gross = 5_000
        annual_income = monthly_gross * 12  # 60,000
        m1_annual = calculate_pcb(annual_income, resident=True) * 12
        m2_annual = self._simulate_12_months_m2(monthly_gross)
        self.assertAlmostEqual(m2_annual, m1_annual, delta=2.0)

    def test_constant_income_mid_range_matches_method1(self):
        """Mid-range income (RM8,000/month = RM96,000/year) annual totals match."""
        monthly_gross = 8_000
        annual_income = monthly_gross * 12  # 96,000
        m1_annual = calculate_pcb(annual_income, resident=True) * 12
        m2_annual = self._simulate_12_months_m2(monthly_gross)
        self.assertAlmostEqual(m2_annual, m1_annual, delta=2.0)

    def test_constant_income_with_spouse_matches_method1(self):
        """Category 2 (non-working spouse) constant income annual totals match."""
        monthly_gross = 6_000
        annual_income = monthly_gross * 12  # 72,000
        m1_annual = calculate_pcb(annual_income, resident=True, category=2) * 12
        m2_annual = self._simulate_12_months_m2(monthly_gross, category=2)
        self.assertAlmostEqual(m2_annual, m1_annual, delta=2.0)

    def test_low_income_below_rebate_threshold(self):
        """Below RM35,000 chargeable: rebate applies; Method 2 total matches Method 1."""
        monthly_gross = 3_000  # annual 36,000; chargeable 27,000 < 35,000
        annual_income = monthly_gross * 12
        m1_annual = calculate_pcb(annual_income, resident=True) * 12
        m2_annual = self._simulate_12_months_m2(monthly_gross)
        self.assertAlmostEqual(m2_annual, m1_annual, delta=2.0)


class TestCalculatePcbMethod2VariableIncome(FrappeTestCase):
    """Test Method 2 behaviour for employees with variable income."""

    def test_method2_adjusts_after_bonus_month(self):
        """After a high-income month, subsequent months carry higher PCB.

        Employee: RM5,000/month. Month 6 is RM15,000 (bonus of RM10,000).
        Method 2 should raise PCB for months 7-12 to cover the increased liability.
        Method 1 (constant RM5,000) would underestimate after the bonus month.
        """
        schedule = [5_000] * 5 + [15_000] + [5_000] * 6
        # Method 1 baseline (based on RM5,000/month):
        m1_baseline = calculate_pcb(60_000, resident=True)

        ytd_gross = 0.0
        ytd_pcb = 0.0
        monthly_pcbs = []
        for month, gross in enumerate(schedule, 1):
            ytd_gross += gross
            pcb = calculate_pcb_method2(ytd_gross, ytd_pcb, month, resident=True)
            monthly_pcbs.append(pcb)
            ytd_pcb += pcb

        # Month 6 PCB should be significantly higher than Method 1 baseline
        # (because annualised income now = 45,000*12/6 = 90,000 > 60,000)
        self.assertGreater(monthly_pcbs[5], m1_baseline)

        # Months 7-11 should also be higher than Method 1 baseline (catching up remaining).
        # Month 12 may be lower as it only clears the remaining small balance after
        # months 7-11 already over-collected relative to Method 1 baseline.
        for i in range(6, 11):
            self.assertGreater(monthly_pcbs[i], m1_baseline)

    def test_method2_annual_total_with_bonus_month(self):
        """Total Method 2 PCB for variable income equals tax on actual annual income.

        Total annual income = 5,000*11 + 15,000 = 70,000.
        Method 2 sum should approximate actual tax on RM70,000.
        """
        schedule = [5_000] * 5 + [15_000] + [5_000] * 6
        actual_annual = sum(schedule)  # 70,000
        actual_annual_tax = calculate_pcb(actual_annual, resident=True) * 12

        ytd_gross = 0.0
        ytd_pcb = 0.0
        total_m2 = 0.0
        for month, gross in enumerate(schedule, 1):
            ytd_gross += gross
            pcb = calculate_pcb_method2(ytd_gross, ytd_pcb, month, resident=True)
            total_m2 += pcb
            ytd_pcb += pcb

        # Method 2 should closely approximate the actual annual tax
        self.assertAlmostEqual(total_m2, actual_annual_tax, delta=3.0)

    def test_method2_smooths_relative_to_method1_for_bonus_earner(self):
        """Method 2 produces MORE PCB than Method 1 in high-income months.

        This is the core 'smoothing' — Method 2 increases PCB when income spikes.
        """
        # Month 6: ytd includes RM10,000 bonus
        ytd_after_bonus = 5_000 * 5 + 15_000  # = 40,000
        m2_month6 = calculate_pcb_method2(ytd_after_bonus, 0.0, 6, resident=True)

        # Method 1 for RM15,000 * 12 = RM180,000 annual
        m1_high = calculate_pcb(180_000, resident=True)

        # Method 2 month 6 < Method 1 at RM15K/month (because it uses annualised YTD)
        # Annualised = 40,000*12/6 = 80,000 < 180,000
        # But M2 is higher than M1 for constant RM5,000/month (=60,000/year):
        m1_low = calculate_pcb(60_000, resident=True)
        self.assertGreater(m2_month6, m1_low)


class TestCalculatePcbMethod2NonResident(FrappeTestCase):
    """Test Method 2 for non-resident employees (flat 30%)."""

    def test_non_resident_month1_equals_30pct(self):
        """Non-resident month 1: PCB = annualised * 30% / 12."""
        monthly_gross = 5_000
        # annualised = 5,000*12/1 = 60,000; tax = 60,000*0.30 = 18,000; /12 = 1,500
        expected = round(18_000 / 12, 2)
        result = calculate_pcb_method2(monthly_gross, 0.0, 1, resident=False)
        self.assertAlmostEqual(result, expected, places=2)

    def test_non_resident_constant_income_annual_total(self):
        """Non-resident constant income: Method 2 annual = annual * 30%."""
        monthly_gross = 5_000
        ytd_gross = 0.0
        ytd_pcb = 0.0
        total = 0.0
        for month in range(1, 13):
            ytd_gross += monthly_gross
            pcb = calculate_pcb_method2(ytd_gross, ytd_pcb, month, resident=False)
            total += pcb
            ytd_pcb += pcb
        expected_annual = 60_000 * 0.30
        self.assertAlmostEqual(total, expected_annual, delta=2.0)


class TestPopulateYtdPcbFields(FrappeTestCase):
    """Unit tests for populate_ytd_pcb_fields() before_submit hook."""

    def _make_doc(self, employee="EMP-001", end_date="2025-03-31"):
        """Create a minimal Salary Slip mock."""
        doc = MagicMock()
        doc.employee = employee
        doc.end_date = end_date
        doc.custom_ytd_gross = 0.0
        doc.custom_ytd_pcb_deducted = 0.0
        return doc

    @patch("lhdn_payroll_integration.services.pcb_calculator.frappe")
    def test_populates_ytd_fields_from_db(self, mock_frappe):
        """populate_ytd_pcb_fields() sets custom_ytd_gross and custom_ytd_pcb_deducted."""
        # Prior 2 months: RM5,000 gross each, RM160.83 PCB each
        mock_frappe.db.sql.side_effect = [
            [(10_000.0,)],  # gross query: 2 * 5,000
            [(321.66,)],    # PCB query: 2 * 160.83
        ]
        doc = self._make_doc(end_date="2025-03-31")
        populate_ytd_pcb_fields(doc)

        self.assertAlmostEqual(doc.custom_ytd_gross, 10_000.0, places=2)
        self.assertAlmostEqual(doc.custom_ytd_pcb_deducted, 321.66, places=2)

    @patch("lhdn_payroll_integration.services.pcb_calculator.frappe")
    def test_first_month_gives_zero_ytd(self, mock_frappe):
        """First month of the year: no prior slips → YTD fields = 0."""
        mock_frappe.db.sql.side_effect = [
            [(None,)],  # gross query returns NULL
            [(None,)],  # PCB query returns NULL
        ]
        doc = self._make_doc(end_date="2025-01-31")
        populate_ytd_pcb_fields(doc)

        self.assertEqual(doc.custom_ytd_gross, 0.0)
        self.assertEqual(doc.custom_ytd_pcb_deducted, 0.0)

    @patch("lhdn_payroll_integration.services.pcb_calculator.frappe")
    def test_db_error_does_not_raise(self, mock_frappe):
        """If DB query fails, hook silently suppresses the error."""
        mock_frappe.db.sql.side_effect = Exception("DB connection error")
        doc = self._make_doc()
        # Should not raise
        try:
            populate_ytd_pcb_fields(doc)
        except Exception:
            self.fail("populate_ytd_pcb_fields() raised an exception on DB error")

    @patch("lhdn_payroll_integration.services.pcb_calculator.frappe")
    def test_uses_correct_employee_and_year(self, mock_frappe):
        """Queries are parameterised with the correct employee and year."""
        mock_frappe.db.sql.side_effect = [
            [(5_000.0,)],
            [(160.83,)],
        ]
        doc = self._make_doc(employee="HR-EMP-0042", end_date="2025-06-30")
        populate_ytd_pcb_fields(doc)

        # Verify both SQL calls were made
        self.assertEqual(mock_frappe.db.sql.call_count, 2)

        # First call (gross): check employee and year params
        gross_call_args = mock_frappe.db.sql.call_args_list[0]
        gross_params = gross_call_args[0][1]  # positional (sql, params)
        self.assertEqual(gross_params[0], "HR-EMP-0042")
        self.assertEqual(gross_params[1], 2025)

    @patch("lhdn_payroll_integration.services.pcb_calculator.frappe")
    def test_string_end_date_parsed_correctly(self, mock_frappe):
        """ISO string end_date is parsed to extract the correct year."""
        mock_frappe.db.sql.side_effect = [
            [(0.0,)],
            [(0.0,)],
        ]
        doc = self._make_doc(end_date="2026-12-31")
        populate_ytd_pcb_fields(doc)

        gross_params = mock_frappe.db.sql.call_args_list[0][0][1]
        self.assertEqual(gross_params[1], 2026)
