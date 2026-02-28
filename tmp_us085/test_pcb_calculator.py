"""Tests for PCB/MTD calculator — US-004, US-018, US-035, US-036, and US-058.

Covers:
- Single resident: progressive tax bands
- Married with children: reliefs reduce chargeable income
- Non-resident: flat 30%
- Zero income: returns 0.0
- validate_pcb_amount: returns warning dict
- Bonus/irregular payment: one-twelfth annualisation rule (US-018)
- Gratuity/leave encashment: Schedule 6 para 25 exemption (US-035)
- Mid-month proration: worked_days/total_days proration (US-036)
- ITA 1967 s.6A RM400 personal and spouse tax rebates (US-058)
"""
from unittest.mock import MagicMock, patch

from frappe.tests.utils import FrappeTestCase

from lhdn_payroll_integration.services.pcb_calculator import (
    calculate_pcb,
    get_cp38_amount,
    validate_pcb_amount,
    _compute_tax_on_chargeable_income,
)


class TestCalculatePcbResident(FrappeTestCase):
    """Test calculate_pcb() for resident employees."""

    def test_zero_income_returns_zero(self):
        """Zero income yields zero PCB."""
        result = calculate_pcb(0, resident=True)
        self.assertEqual(result, 0.0)

    def test_negative_income_returns_zero(self):
        """Negative income yields zero PCB."""
        result = calculate_pcb(-5000, resident=True)
        self.assertEqual(result, 0.0)

    def test_income_below_relief_returns_zero(self):
        """Income below self-relief (RM9,000) gives zero chargeable income → zero PCB."""
        result = calculate_pcb(8_000, resident=True, married=False, children=0)
        self.assertEqual(result, 0.0)

    def test_single_resident_low_income(self):
        """Single resident, annual income RM 20,000.

        Chargeable = 20,000 - 9,000 = 11,000
        Tax: first 5,000 at 0% = 0; next 6,000 at 1% = 60
        ITA s.6A personal rebate (chargeable 11,000 <= 35,000): max(0, 60-400) = 0
        Monthly = 0.00
        """
        result = calculate_pcb(20_000, resident=True, married=False, children=0)
        self.assertAlmostEqual(result, 0.00, places=2)

    def test_single_resident_mid_income(self):
        """Single resident, annual income RM 60,000.

        Chargeable = 60,000 - 9,000 = 51,000
        Tax:
          0%  on 5,000         =    0
          1%  on 15,000        =  150
          3%  on 15,000        =  450
          8%  on 15,000        = 1200
          13% on  1,000        =  130
          Total = 1,930
        Monthly = 1930 / 12 ≈ 160.83
        """
        result = calculate_pcb(60_000, resident=True, married=False, children=0)
        self.assertAlmostEqual(result, 1930 / 12, places=2)

    def test_married_resident_with_two_children(self):
        """Married resident with 2 children, annual income RM 60,000.

        Total relief = 9,000 + 4,000 + 2*2,000 = 17,000
        Chargeable = 60,000 - 17,000 = 43,000
        Tax:
          0%  on 5,000  =    0
          1%  on 15,000 =  150
          3%  on 15,000 =  450
          8%  on  8,000 =  640
          Total = 1,240
        Monthly = 1240 / 12 ≈ 103.33
        """
        result = calculate_pcb(60_000, resident=True, married=True, children=2)
        self.assertAlmostEqual(result, 1240 / 12, places=2)

    def test_high_income_band_24_percent(self):
        """Single resident, annual income RM 200,000.

        Chargeable = 200,000 - 9,000 = 191,000
        Tax:
          0%   on   5,000 =      0
          1%   on  15,000 =    150
          3%   on  15,000 =    450
          8%   on  15,000 =  1,200
          13%  on  20,000 =  2,600
          21%  on  30,000 =  6,300
          24%  on  91,000 = 21,840
          Total = 32,540
        Monthly = 32,540 / 12 ≈ 2,711.67
        """
        result = calculate_pcb(200_000, resident=True, married=False, children=0)
        self.assertAlmostEqual(result, 32_540 / 12, places=2)


class TestCalculatePcbNonResident(FrappeTestCase):
    """Test calculate_pcb() for non-resident employees (flat 30%)."""

    def test_non_resident_flat_30_percent(self):
        """Non-resident: 30% flat on gross, no reliefs."""
        annual = 60_000
        result = calculate_pcb(annual, resident=False)
        expected_monthly = (annual * 0.30) / 12
        self.assertAlmostEqual(result, expected_monthly, places=2)

    def test_non_resident_zero_income(self):
        """Non-resident with zero income yields zero."""
        result = calculate_pcb(0, resident=False)
        self.assertEqual(result, 0.0)

    def test_non_resident_ignores_married_children(self):
        """Non-resident: married/children flags ignored — flat 30% still applies."""
        annual = 80_000
        result_single = calculate_pcb(annual, resident=False, married=False, children=0)
        result_married = calculate_pcb(annual, resident=False, married=True, children=3)
        self.assertEqual(result_single, result_married)
        expected = round((annual * 0.30) / 12, 2)
        self.assertEqual(result_single, expected)


class TestComputeTaxOnChargeableIncome(FrappeTestCase):
    """Test _compute_tax_on_chargeable_income() internal helper directly."""

    def test_zero_chargeable_returns_zero(self):
        self.assertEqual(_compute_tax_on_chargeable_income(0), 0.0)

    def test_negative_chargeable_returns_zero(self):
        self.assertEqual(_compute_tax_on_chargeable_income(-1000), 0.0)

    def test_exactly_at_band_boundary_5000(self):
        """RM 5,000: still in 0% band."""
        self.assertEqual(_compute_tax_on_chargeable_income(5_000), 0.0)

    def test_just_above_band_boundary_5001(self):
        """RM 5,001: 1 RM in the 1% band → RM 0.01 tax."""
        self.assertAlmostEqual(_compute_tax_on_chargeable_income(5_001), 0.01, places=2)

    def test_full_second_band_20000(self):
        """RM 20,000: 15,000 at 1% = 150."""
        self.assertAlmostEqual(_compute_tax_on_chargeable_income(20_000), 150.0, places=2)


class TestValidatePcbAmount(FrappeTestCase):
    """Test validate_pcb_amount() whitelist function."""

    def _make_deduction_row(self, component, amount):
        row = MagicMock()
        row.salary_component = component
        row.amount = amount
        return row

    @patch("lhdn_payroll_integration.services.pcb_calculator.frappe")
    def test_returns_dict_with_required_keys(self, mock_frappe):
        """validate_pcb_amount returns dict with all required keys."""
        slip = MagicMock()
        slip.gross_pay = 5_000
        slip.employee = "EMP-001"
        slip.deductions = [self._make_deduction_row("Monthly Tax Deduction", 160.0)]

        employee = MagicMock()
        employee.custom_is_non_resident = 0
        employee.custom_tax_resident_status = "Resident"
        employee.custom_marital_status = "Single"
        employee.custom_number_of_children = 0

        mock_frappe.get_doc.side_effect = lambda doctype, name: (
            slip if doctype == "Salary Slip" else employee
        )

        result = validate_pcb_amount("SLIP-001")
        self.assertIn("expected_monthly_pcb", result)
        self.assertIn("actual_pcb", result)
        self.assertIn("deviation_pct", result)
        self.assertIn("warning", result)
        self.assertIn("message", result)

    @patch("lhdn_payroll_integration.services.pcb_calculator.frappe")
    def test_no_warning_when_pcb_within_10_percent(self, mock_frappe):
        """No warning emitted when actual PCB is within 10% of estimate."""
        # Annual = 60,000; single resident; expected = 1930/12 ≈ 160.83
        expected_monthly = 1930 / 12
        actual_pcb = expected_monthly * 1.05  # 5% over — within threshold

        slip = MagicMock()
        slip.gross_pay = 5_000  # monthly → annual = 60,000
        slip.employee = "EMP-001"
        slip.deductions = [self._make_deduction_row("Monthly Tax Deduction", actual_pcb)]

        employee = MagicMock()
        employee.custom_is_non_resident = 0
        employee.custom_tax_resident_status = "Resident"
        employee.custom_marital_status = "Single"
        employee.custom_number_of_children = 0

        mock_frappe.get_doc.side_effect = lambda doctype, name: (
            slip if doctype == "Salary Slip" else employee
        )

        result = validate_pcb_amount("SLIP-001")
        self.assertFalse(result["warning"])
        mock_frappe.msgprint.assert_not_called()

    @patch("lhdn_payroll_integration.services.pcb_calculator.frappe")
    def test_warning_when_pcb_deviates_more_than_10_percent(self, mock_frappe):
        """Warning emitted when actual PCB deviates >10% from estimate."""
        # Annual = 60,000; expected ≈ 160.83; give 50% less
        expected_monthly = 1930 / 12
        actual_pcb = expected_monthly * 0.50  # 50% off

        slip = MagicMock()
        slip.gross_pay = 5_000
        slip.employee = "EMP-001"
        slip.deductions = [self._make_deduction_row("Monthly Tax Deduction", actual_pcb)]

        employee = MagicMock()
        employee.custom_is_non_resident = 0
        employee.custom_tax_resident_status = "Resident"
        employee.custom_marital_status = "Single"
        employee.custom_number_of_children = 0

        mock_frappe.get_doc.side_effect = lambda doctype, name: (
            slip if doctype == "Salary Slip" else employee
        )

        result = validate_pcb_amount("SLIP-001")
        self.assertTrue(result["warning"])
        mock_frappe.msgprint.assert_called_once()

    @patch("lhdn_payroll_integration.services.pcb_calculator.frappe")
    def test_zero_gross_pay_no_warning(self, mock_frappe):
        """Zero gross pay: expected=0, actual=0 → no warning."""
        slip = MagicMock()
        slip.gross_pay = 0
        slip.employee = "EMP-001"
        slip.deductions = []

        employee = MagicMock()
        employee.custom_is_non_resident = 0
        employee.custom_tax_resident_status = "Resident"
        employee.custom_marital_status = "Single"
        employee.custom_number_of_children = 0

        mock_frappe.get_doc.side_effect = lambda doctype, name: (
            slip if doctype == "Salary Slip" else employee
        )

        result = validate_pcb_amount("SLIP-001")
        self.assertFalse(result["warning"])
        self.assertEqual(result["expected_monthly_pcb"], 0.0)
        self.assertEqual(result["actual_pcb"], 0.0)

    @patch("lhdn_payroll_integration.services.pcb_calculator.frappe")
    def test_non_resident_flag_triggers_flat_30_percent(self, mock_frappe):
        """custom_is_non_resident=1 causes validate_pcb_amount to use flat 30% rate."""
        # Annual = 60,000; non-resident flat 30% → 1,500/month
        annual = 60_000
        monthly_gross = annual / 12  # 5,000
        expected_non_resident_monthly = round(annual * 0.30 / 12, 2)  # 1,500.0

        slip = MagicMock()
        slip.gross_pay = monthly_gross
        slip.employee = "EMP-002"
        slip.deductions = [self._make_deduction_row("Monthly Tax Deduction", expected_non_resident_monthly)]

        employee = MagicMock()
        employee.custom_is_non_resident = 1  # non-resident flag set
        employee.custom_marital_status = "Single"
        employee.custom_number_of_children = 0

        mock_frappe.get_doc.side_effect = lambda doctype, name: (
            slip if doctype == "Salary Slip" else employee
        )

        result = validate_pcb_amount("SLIP-002")
        self.assertAlmostEqual(result["expected_monthly_pcb"], expected_non_resident_monthly, places=2)
        self.assertFalse(result["warning"])  # actual matches expected, no warning


class TestCalculatePcbBonus(FrappeTestCase):
    """Test calculate_pcb() with bonus_amount (US-018 — irregular payment PCB).

    LHDN Schedule D one-twelfth annualisation rule:
      bonus_pcb = tax_on(annual_income + bonus_amount - reliefs)
                  - tax_on(annual_income - reliefs)
      total_pcb = regular_monthly_pcb + bonus_pcb
    """

    def test_bonus_pcb_differs_from_regular_same_income(self):
        """Bonus PCB for same annual income must be greater than regular monthly PCB."""
        annual = 60_000
        bonus = 5_000
        regular = calculate_pcb(annual, resident=True)
        with_bonus = calculate_pcb(annual, resident=True, bonus_amount=bonus)
        self.assertGreater(with_bonus, regular)

    def test_zero_bonus_equals_regular_pcb(self):
        """Passing bonus_amount=0 must return same value as no bonus_amount."""
        annual = 60_000
        regular = calculate_pcb(annual, resident=True)
        explicit_zero = calculate_pcb(annual, resident=True, bonus_amount=0.0)
        self.assertAlmostEqual(regular, explicit_zero, places=2)

    def test_bonus_pcb_annualisation_calculation_single_resident(self):
        """Verify mathematical correctness of bonus PCB for single resident.

        annual_income = 60,000; bonus = 10,000; self-relief = 9,000
        Regular:
          chargeable = 60,000 - 9,000 = 51,000
          tax = 0 + 150 + 450 + 1200 + 130 = 1,930
          monthly = 1,930 / 12

        With bonus:
          total = 70,000; chargeable = 70,000 - 9,000 = 61,000
          tax:
            0%  on  5,000  =     0
            1%  on 15,000  =   150
            3%  on 15,000  =   450
            8%  on 15,000  = 1,200
            13% on 11,000  = 1,430
            Total = 3,230
          bonus_pcb = 3,230 - 1,930 = 1,300
          total_pcb = 1,930/12 + 1,300
        """
        annual = 60_000
        bonus = 10_000
        result = calculate_pcb(annual, resident=True, bonus_amount=bonus)

        regular_monthly = 1_930 / 12
        bonus_pcb = 3_230 - 1_930  # = 1,300
        expected = round(regular_monthly + bonus_pcb, 2)
        self.assertAlmostEqual(result, expected, places=2)

    def test_bonus_pcb_higher_band_jumps(self):
        """Large bonus pushing income into a higher tax band produces larger PCB."""
        annual = 60_000
        small_bonus = calculate_pcb(annual, resident=True, bonus_amount=5_000)
        large_bonus = calculate_pcb(annual, resident=True, bonus_amount=50_000)
        self.assertGreater(large_bonus, small_bonus)

    def test_bonus_pcb_married_with_children_reduces_tax(self):
        """Married-with-children reliefs also reduce bonus PCB vs single."""
        annual = 60_000
        bonus = 10_000
        single_pcb = calculate_pcb(annual, resident=True, married=False, children=0, bonus_amount=bonus)
        married_pcb = calculate_pcb(annual, resident=True, married=True, children=2, bonus_amount=bonus)
        self.assertGreater(single_pcb, married_pcb)

    def test_bonus_pcb_non_resident_flat_30(self):
        """Non-resident bonus PCB = bonus * 30% (full flat rate, not divided by 12)."""
        annual = 60_000
        bonus = 10_000
        result = calculate_pcb(annual, resident=False, bonus_amount=bonus)
        expected_regular = (annual * 0.30) / 12
        expected_bonus_pcb = bonus * 0.30
        expected = round(expected_regular + expected_bonus_pcb, 2)
        self.assertAlmostEqual(result, expected, places=2)

    def test_bonus_only_no_regular_income(self):
        """Bonus with zero annual income: only bonus tax applies."""
        bonus = 10_000
        result = calculate_pcb(0, resident=True, bonus_amount=bonus)
        # chargeable = max(0, 0 + 10000 - 9000) = 1000; at 0% band → 0 tax
        # regular_monthly = 0
        # bonus_pcb = 0 - 0 = 0
        self.assertAlmostEqual(result, 0.0, places=2)

    def test_large_bonus_exceeds_regular_pcb_by_significant_amount(self):
        """Bonus of RM 50,000 on RM 60,000 annual income produces substantial additional PCB."""
        annual = 60_000
        bonus = 50_000
        regular = calculate_pcb(annual, resident=True)
        with_bonus = calculate_pcb(annual, resident=True, bonus_amount=bonus)
        # Bonus alone should add at least RM 1,000 of additional PCB
        self.assertGreater(with_bonus - regular, 1_000)


class TestCalculatePcbGratuityExemption(FrappeTestCase):
    """Test calculate_pcb() with gratuity/leave encashment — US-035.

    ITA 1967 Schedule 6 paragraph 25:
    Gratuity / leave encashment is exempt RM1,000 per completed year of service.
    Only the remainder above the exempt amount is taxable (irregular payment).
    """

    def test_full_exemption_no_tax_on_gratuity(self):
        """Gratuity <= RM1,000 × years_of_service is fully exempt.

        10 years × RM1,000 = RM10,000 exempt.
        Gratuity of RM8,000 is fully exempt → no additional PCB.
        """
        annual = 60_000
        regular = calculate_pcb(annual, resident=True)
        with_gratuity = calculate_pcb(
            annual, resident=True,
            gratuity_amount=8_000, years_of_service=10,
        )
        self.assertAlmostEqual(regular, with_gratuity, places=2)

    def test_partial_exemption_reduces_taxable_gratuity(self):
        """Gratuity RM15,000 with 10 years service: exempt RM10,000, taxable RM5,000.

        annual_income = 60,000; single resident; self-relief = 9,000
        Regular chargeable = 51,000; annual_tax = 1,930
        With taxable gratuity RM5,000:
          total_chargeable = 60,000 + 5,000 - 9,000 = 56,000
          tax:
            0%  on  5,000 =     0
            1%  on 15,000 =   150
            3%  on 15,000 =   450
            8%  on 15,000 = 1,200
            13% on  6,000 =   780
            Total = 2,580
          irregular_pcb = 2,580 - 1,930 = 650
          total = 1,930/12 + 650
        """
        annual = 60_000
        result = calculate_pcb(
            annual, resident=True,
            gratuity_amount=15_000, years_of_service=10,
        )
        regular_monthly = 1_930 / 12
        irregular_pcb = 2_580 - 1_930  # = 650
        expected = round(regular_monthly + irregular_pcb, 2)
        self.assertAlmostEqual(result, expected, places=2)

    def test_zero_years_of_service_no_exemption(self):
        """Zero years of service means no exemption — full gratuity is taxable.

        Gratuity RM10,000 with 0 years = same as bonus RM10,000.
        """
        annual = 60_000
        gratuity_result = calculate_pcb(
            annual, resident=True,
            gratuity_amount=10_000, years_of_service=0,
        )
        bonus_result = calculate_pcb(
            annual, resident=True,
            bonus_amount=10_000,
        )
        self.assertAlmostEqual(gratuity_result, bonus_result, places=2)

    def test_exemption_capped_at_gratuity_amount(self):
        """Exempt amount cannot exceed the gratuity itself.

        20 years × RM1,000 = RM20,000 cap, but gratuity is only RM5,000.
        Exempt = min(5,000, 20,000) = 5,000 → fully exempt.
        """
        annual = 60_000
        regular = calculate_pcb(annual, resident=True)
        with_gratuity = calculate_pcb(
            annual, resident=True,
            gratuity_amount=5_000, years_of_service=20,
        )
        self.assertAlmostEqual(regular, with_gratuity, places=2)

    def test_gratuity_plus_bonus_combined(self):
        """Gratuity and bonus in same period: both irregular amounts combined.

        Gratuity RM15,000 (10 yrs → exempt RM10,000 → taxable RM5,000)
        Bonus RM10,000
        Total irregular = 5,000 + 10,000 = 15,000

        annual = 60,000; single; relief = 9,000
        Regular: chargeable = 51,000; tax = 1,930
        With irregular 15,000:
          total_chargeable = 60,000 + 15,000 - 9,000 = 66,000
          tax:
            0%  on  5,000 =     0
            1%  on 15,000 =   150
            3%  on 15,000 =   450
            8%  on 15,000 = 1,200
            13% on 16,000 = 2,080
            Total = 3,880
          irregular_pcb = 3,880 - 1,930 = 1,950
          total = 1,930/12 + 1,950
        """
        annual = 60_000
        result = calculate_pcb(
            annual, resident=True,
            bonus_amount=10_000,
            gratuity_amount=15_000, years_of_service=10,
        )
        regular_monthly = 1_930 / 12
        irregular_pcb = 3_880 - 1_930  # = 1,950
        expected = round(regular_monthly + irregular_pcb, 2)
        self.assertAlmostEqual(result, expected, places=2)

    def test_non_resident_gratuity_exemption_applies(self):
        """Non-resident: flat 30% on taxable gratuity (after exemption).

        Gratuity RM15,000, 10 years → exempt RM10,000, taxable RM5,000.
        Non-resident irregular PCB = 5,000 × 30% = 1,500.
        """
        annual = 60_000
        result = calculate_pcb(
            annual, resident=False,
            gratuity_amount=15_000, years_of_service=10,
        )
        expected_regular = (annual * 0.30) / 12  # 1,500
        expected_irregular = 5_000 * 0.30  # 1,500
        expected = round(expected_regular + expected_irregular, 2)
        self.assertAlmostEqual(result, expected, places=2)

    def test_gratuity_exemption_reduces_taxable_vs_no_exemption(self):
        """With exemption, PCB must be lower than treating full gratuity as bonus."""
        annual = 60_000
        gratuity = 20_000
        years = 10  # exempt RM10,000

        with_exemption = calculate_pcb(
            annual, resident=True,
            gratuity_amount=gratuity, years_of_service=years,
        )
        no_exemption = calculate_pcb(
            annual, resident=True,
            bonus_amount=gratuity,  # full amount as bonus, no exemption
        )
        self.assertLess(with_exemption, no_exemption)

    def test_gratuity_only_no_regular_income(self):
        """Gratuity with zero annual income — only taxable portion matters.

        Gratuity RM15,000 with 10 years: exempt RM10,000, taxable RM5,000.
        Chargeable = max(0, 0 + 5,000 - 9,000) = 0 → no tax.
        """
        result = calculate_pcb(
            0, resident=True,
            gratuity_amount=15_000, years_of_service=10,
        )
        self.assertAlmostEqual(result, 0.0, places=2)


class TestCalculatePcbProration(FrappeTestCase):
    """Test calculate_pcb() with mid-month proration — US-036.

    LHDN PCB proration for mid-month join/leave:
    When worked_days < total_days, monthly income is prorated:
        prorated_monthly = monthly_income * (worked_days / total_days)
        prorated_annual = prorated_monthly * 12
    PCB is then calculated on the prorated annual income.
    """

    def test_full_month_no_proration(self):
        """worked_days == total_days → no proration, same as default."""
        annual = 60_000
        regular = calculate_pcb(annual, resident=True)
        full_month = calculate_pcb(
            annual, resident=True,
            worked_days=30, total_days=30,
        )
        self.assertAlmostEqual(regular, full_month, places=2)

    def test_half_month_prorated_pcb_lower(self):
        """15 out of 30 days → half income → lower PCB than full month."""
        annual = 60_000
        full = calculate_pcb(annual, resident=True)
        half = calculate_pcb(
            annual, resident=True,
            worked_days=15, total_days=30,
        )
        self.assertLess(half, full)

    def test_half_month_prorated_calculation(self):
        """15/30 days, annual RM 60,000.

        Monthly = 60,000 / 12 = 5,000
        Prorated monthly = 5,000 * (15/30) = 2,500
        Prorated annual = 2,500 * 12 = 30,000
        Chargeable = 30,000 - 9,000 = 21,000
        Tax:
          0%  on  5,000 =   0
          1%  on 15,000 = 150
          3%  on  1,000 =  30
          Total = 180
        ITA s.6A personal rebate (chargeable 21,000 <= 35,000): max(0, 180-400) = 0
        Monthly PCB = 0.00
        """
        result = calculate_pcb(
            60_000, resident=True,
            worked_days=15, total_days=30,
        )
        self.assertAlmostEqual(result, 0.00, places=2)

    def test_none_worked_days_no_proration(self):
        """When worked_days is None, no proration applied."""
        annual = 60_000
        regular = calculate_pcb(annual, resident=True)
        no_proration = calculate_pcb(
            annual, resident=True,
            worked_days=None, total_days=30,
        )
        self.assertAlmostEqual(regular, no_proration, places=2)

    def test_none_total_days_no_proration(self):
        """When total_days is None, no proration applied."""
        annual = 60_000
        regular = calculate_pcb(annual, resident=True)
        no_proration = calculate_pcb(
            annual, resident=True,
            worked_days=15, total_days=None,
        )
        self.assertAlmostEqual(regular, no_proration, places=2)

    def test_non_resident_proration(self):
        """Non-resident with proration: flat 30% on prorated income.

        Annual 60,000; 15/30 days → prorated annual = 30,000
        Monthly PCB = (30,000 * 0.30) / 12 = 750.00
        """
        result = calculate_pcb(
            60_000, resident=False,
            worked_days=15, total_days=30,
        )
        self.assertAlmostEqual(result, 750.00, places=2)

    def test_proration_with_married_relief(self):
        """Married with children, 20/30 days.

        Annual 60,000; 20/30 → prorated annual = 40,000
        Relief = 9,000 + 4,000 + 2*2,000 = 17,000
        Chargeable = 40,000 - 17,000 = 23,000
        Tax:
          0%  on  5,000 =   0
          1%  on 15,000 = 150
          3%  on  3,000 =  90
          Total = 240
        ITA s.6A rebates (chargeable 23,000 <= 35,000, married=True):
          Personal: max(0, 240-400) = 0
          Spouse: max(0, 0-400) = 0
        Monthly = 0.00
        """
        result = calculate_pcb(
            60_000, resident=True, married=True, children=2,
            worked_days=20, total_days=30,
        )
        self.assertAlmostEqual(result, 0.00, places=2)

    def test_zero_total_days_no_division_error(self):
        """total_days=0 should not cause ZeroDivisionError; treated as no proration."""
        annual = 60_000
        regular = calculate_pcb(annual, resident=True)
        result = calculate_pcb(
            annual, resident=True,
            worked_days=0, total_days=0,
        )
        self.assertAlmostEqual(regular, result, places=2)


class TestValidatePcbAmountProration(FrappeTestCase):
    """Test validate_pcb_amount() uses prorated income — US-036."""

    def _make_deduction_row(self, component, amount):
        row = MagicMock()
        row.salary_component = component
        row.amount = amount
        return row

    @patch("lhdn_payroll_integration.services.pcb_calculator.frappe")
    def test_prorated_pcb_used_when_payment_days_less_than_total(self, mock_frappe):
        """validate_pcb_amount prorates when payment_days < total_working_days.

        Monthly gross = 5,000; payment_days = 15, total_working_days = 30
        Annual = 60,000; prorated annual = 30,000
        Chargeable = 30,000 - 9,000 = 21,000
        Tax = 180; ITA s.6A rebate (21,000 <= 35,000): max(0, 180-400) = 0
        Expected PCB at prorated income = 0.00
        """
        slip = MagicMock()
        slip.gross_pay = 5_000
        slip.employee = "EMP-001"
        slip.payment_days = 15
        slip.total_working_days = 30
        # Actual PCB = 0.00 to match rebated expected
        slip.deductions = [self._make_deduction_row("Monthly Tax Deduction", 0.00)]

        employee = MagicMock()
        employee.custom_is_non_resident = 0
        employee.custom_tax_resident_status = "Resident"
        employee.custom_marital_status = "Single"
        employee.custom_number_of_children = 0

        mock_frappe.get_doc.side_effect = lambda doctype, name: (
            slip if doctype == "Salary Slip" else employee
        )

        result = validate_pcb_amount("SLIP-001")
        # Expected monthly PCB should be 0.00 (rebate applied to prorated income)
        self.assertAlmostEqual(result["expected_monthly_pcb"], 0.00, places=2)
        self.assertFalse(result["warning"])


class TestCalculatePcbZakatOffset(FrappeTestCase):
    """Test calculate_pcb() with annual_zakat (US-053 — ITA 1967 s.6A(3)).

    Zakat is a ringgit-for-ringgit PCB credit, NOT a reduction in chargeable
    income. The offset is applied AFTER progressive tax computation:
        net_pcb = max(0, gross_monthly_pcb - annual_zakat / 12)
    """

    def test_zakat_reduces_pcb_ringgit_for_ringgit(self):
        """Annual Zakat / 12 is subtracted from monthly PCB.

        annual_income = 60,000; single resident
        gross_monthly_pcb = 1930 / 12 ≈ 160.83
        annual_zakat = 1,200 → monthly_zakat = 100
        net_pcb = 160.83 - 100 = 60.83
        """
        annual = 60_000
        gross_pcb = calculate_pcb(annual, resident=True)
        net_pcb = calculate_pcb(annual, resident=True, annual_zakat=1_200)
        expected_net = round(gross_pcb - 100.0, 2)
        self.assertAlmostEqual(net_pcb, expected_net, places=2)

    def test_zero_zakat_does_not_change_pcb(self):
        """Passing annual_zakat=0 returns same PCB as default."""
        annual = 60_000
        pcb_default = calculate_pcb(annual, resident=True)
        pcb_zero_zakat = calculate_pcb(annual, resident=True, annual_zakat=0)
        self.assertAlmostEqual(pcb_default, pcb_zero_zakat, places=2)

    def test_pcb_never_goes_negative(self):
        """PCB is floored at 0 even when Zakat exceeds gross PCB.

        annual_income = 20,000; single resident; gross_monthly_pcb = 5.00
        annual_zakat = 10,000 → monthly_zakat = 833.33 >> 5.00
        net_pcb = max(0, 5.00 - 833.33) = 0.0
        """
        annual = 20_000
        net_pcb = calculate_pcb(annual, resident=True, annual_zakat=10_000)
        self.assertEqual(net_pcb, 0.0)

    def test_zakat_matching_monthly_pcb_yields_zero(self):
        """When monthly_zakat == gross_monthly_pcb, net PCB is exactly 0."""
        annual = 60_000
        gross_monthly = calculate_pcb(annual, resident=True)  # 1930/12 ≈ 160.83
        annual_zakat = round(gross_monthly * 12, 2)  # exactly cancel out monthly PCB
        net_pcb = calculate_pcb(annual, resident=True, annual_zakat=annual_zakat)
        self.assertEqual(net_pcb, 0.0)

    def test_zakat_is_not_deducted_from_chargeable_income(self):
        """Zakat is a PCB credit, not a relief — chargeable income is unchanged.

        Verify by comparing: if Zakat were a relief, PCB reduction would follow
        the marginal tax rate (e.g. 1% band). But ringgit-for-ringgit means
        RM100/month Zakat => RM100/month PCB reduction exactly.
        """
        annual = 60_000
        annual_zakat = 1_200  # RM100/month
        gross_pcb = calculate_pcb(annual, resident=True)
        net_pcb = calculate_pcb(annual, resident=True, annual_zakat=annual_zakat)
        reduction = round(gross_pcb - net_pcb, 2)
        # Exact ringgit-for-ringgit: reduction should equal 100.00
        self.assertAlmostEqual(reduction, 100.0, places=2)

    def test_zakat_combined_with_married_children_reliefs(self):
        """Zakat offset stacks with standard reliefs correctly."""
        annual = 60_000
        pcb_married = calculate_pcb(annual, resident=True, married=True, children=2)
        pcb_zakat = calculate_pcb(annual, resident=True, married=True, children=2, annual_zakat=600)
        expected_net = round(pcb_married - 50.0, 2)  # 600/12 = 50 offset
        self.assertAlmostEqual(pcb_zakat, max(0.0, expected_net), places=2)

    def test_zakat_combined_with_tp1_reliefs(self):
        """Zakat offset applies after TP1 reliefs (which reduce chargeable income)."""
        annual = 120_000
        pcb_no_extras = calculate_pcb(annual, resident=True)
        pcb_tp1_only = calculate_pcb(annual, resident=True, tp1_total_reliefs=10_000)
        pcb_tp1_zakat = calculate_pcb(annual, resident=True, tp1_total_reliefs=10_000, annual_zakat=1_200)
        # Zakat further reduces PCB below TP1-only level
        self.assertGreater(pcb_no_extras, pcb_tp1_only)
        self.assertGreater(pcb_tp1_only, pcb_tp1_zakat)

    def test_zakat_combined_with_bonus(self):
        """Zakat offset applies to the combined regular + bonus PCB."""
        annual = 60_000
        bonus = 10_000
        gross_pcb_bonus = calculate_pcb(annual, resident=True, bonus_amount=bonus)
        net_pcb_bonus_zakat = calculate_pcb(
            annual, resident=True, bonus_amount=bonus, annual_zakat=1_200
        )
        reduction = round(gross_pcb_bonus - net_pcb_bonus_zakat, 2)
        self.assertAlmostEqual(reduction, 100.0, places=2)

    def test_zakat_non_resident_also_offset(self):
        """Non-resident Zakat offset: applied after flat 30% computation."""
        annual = 60_000
        annual_zakat = 1_200  # 100/month
        gross_nr = calculate_pcb(annual, resident=False)
        net_nr = calculate_pcb(annual, resident=False, annual_zakat=annual_zakat)
        self.assertAlmostEqual(gross_nr - net_nr, 100.0, places=2)

    def test_zakat_high_income_large_offset(self):
        """Large Zakat amount reduces high PCB significantly (not below 0)."""
        annual = 500_000
        annual_zakat = 24_000  # RM2,000/month
        gross_pcb = calculate_pcb(annual, resident=True)
        net_pcb = calculate_pcb(annual, resident=True, annual_zakat=annual_zakat)
        self.assertGreater(gross_pcb, net_pcb)
        reduction = round(gross_pcb - net_pcb, 2)
        self.assertAlmostEqual(reduction, 2_000.0, places=2)
        self.assertGreaterEqual(net_pcb, 0.0)


# ---------------------------------------------------------------------------
# US-054: CP38 Additional Deduction Tests
# ---------------------------------------------------------------------------

class TestGetCp38Amount(FrappeTestCase):
    """Tests for get_cp38_amount() function (US-054 - ITA s.107(1)(b))."""

    def test_cp38_active_notice_returns_amount(self):
        """Returns CP38 amount when expiry is in the future."""
        from datetime import date, timedelta

        future_date = (date.today() + timedelta(days=30)).isoformat()
        mock_employee = MagicMock()
        mock_employee.custom_cp38_amount = 500.0
        mock_employee.custom_cp38_expiry = future_date

        with patch("frappe.get_doc", return_value=mock_employee):
            result = get_cp38_amount("EMP-CP38-001")
        self.assertEqual(result, 500.0)

    def test_cp38_expired_notice_returns_zero(self):
        """Returns 0.0 when expiry date is in the past (notice expired)."""
        from datetime import date, timedelta

        past_date = (date.today() - timedelta(days=1)).isoformat()
        mock_employee = MagicMock()
        mock_employee.custom_cp38_amount = 500.0
        mock_employee.custom_cp38_expiry = past_date

        with patch("frappe.get_doc", return_value=mock_employee):
            result = get_cp38_amount("EMP-CP38-002")
        self.assertEqual(result, 0.0)

    def test_cp38_expiry_today_is_active(self):
        """Returns amount when expiry equals today (boundary - still active)."""
        from datetime import date

        today = date.today().isoformat()
        mock_employee = MagicMock()
        mock_employee.custom_cp38_amount = 200.0
        mock_employee.custom_cp38_expiry = today

        with patch("frappe.get_doc", return_value=mock_employee):
            result = get_cp38_amount("EMP-CP38-003")
        self.assertEqual(result, 200.0)

    def test_cp38_no_expiry_returns_zero(self):
        """Returns 0.0 when expiry field is None/not set."""
        mock_employee = MagicMock()
        mock_employee.custom_cp38_amount = 500.0
        mock_employee.custom_cp38_expiry = None

        with patch("frappe.get_doc", return_value=mock_employee):
            result = get_cp38_amount("EMP-CP38-004")
        self.assertEqual(result, 0.0)

    def test_cp38_zero_amount_returns_zero(self):
        """Returns 0.0 when CP38 amount is 0 even if expiry is in the future."""
        from datetime import date, timedelta

        future_date = (date.today() + timedelta(days=30)).isoformat()
        mock_employee = MagicMock()
        mock_employee.custom_cp38_amount = 0
        mock_employee.custom_cp38_expiry = future_date

        with patch("frappe.get_doc", return_value=mock_employee):
            result = get_cp38_amount("EMP-CP38-005")
        self.assertEqual(result, 0.0)

    def test_cp38_exception_returns_zero(self):
        """Returns 0.0 safely when frappe.get_doc raises (employee not found)."""
        with patch("frappe.get_doc", side_effect=Exception("DoesNotExist")):
            result = get_cp38_amount("EMP-NOTFOUND")
        self.assertEqual(result, 0.0)


class TestCp39ReportCp38Column(FrappeTestCase):
    """Tests for CP39 report CP38 column (US-054)."""

    def test_cp39_has_cp38_column(self):
        """CP39 report get_columns() must include cp38_amount column."""
        from lhdn_payroll_integration.lhdn_payroll_integration.report.cp39_pcb_remittance.cp39_pcb_remittance import (
            get_columns,
        )
        columns = get_columns()
        fieldnames = [c["fieldname"] for c in columns if isinstance(c, dict)]
        self.assertIn(
            "cp38_amount",
            fieldnames,
            "CP39 report must have cp38_amount column (US-054)",
        )

    def test_cp39_cp38_column_is_currency(self):
        """CP38 column in CP39 report must be Currency type."""
        from lhdn_payroll_integration.lhdn_payroll_integration.report.cp39_pcb_remittance.cp39_pcb_remittance import (
            get_columns,
        )
        columns = get_columns()
        cp38_col = next((c for c in columns if c.get("fieldname") == "cp38_amount"), None)
        self.assertIsNotNone(cp38_col, "cp38_amount column not found")
        self.assertEqual(cp38_col.get("fieldtype"), "Currency")


class TestBorangECp38Column(FrappeTestCase):
    """Tests for Borang E CP38 total column (US-054)."""

    def test_borang_e_has_total_cp38_column(self):
        """Borang E get_columns() must include total_cp38 column."""
        from lhdn_payroll_integration.lhdn_payroll_integration.report.borang_e.borang_e import (
            get_columns,
        )
        columns = get_columns()
        fieldnames = [c["fieldname"] for c in columns if isinstance(c, dict)]
        self.assertIn(
            "total_cp38",
            fieldnames,
            "Borang E must have total_cp38 column (US-054)",
        )

    def test_borang_e_total_cp38_is_currency(self):
        """total_cp38 column in Borang E must be Currency type."""
        from lhdn_payroll_integration.lhdn_payroll_integration.report.borang_e.borang_e import (
            get_columns,
        )
        columns = get_columns()
        cp38_col = next((c for c in columns if c.get("fieldname") == "total_cp38"), None)
        self.assertIsNotNone(cp38_col, "total_cp38 column not found in Borang E")
        self.assertEqual(cp38_col.get("fieldtype"), "Currency")


# ---------------------------------------------------------------------------
# US-058: ITA 1967 s.6A RM400 Personal and Spouse Tax Rebates
# ---------------------------------------------------------------------------

class TestPcbTaxRebates(FrappeTestCase):
    """Test ITA 1967 s.6A RM400 personal and spouse tax rebates — US-058.

    Rebates apply to residents with chargeable income <= RM35,000:
    - Personal rebate: RM400 for all categories
    - Spouse rebate: additional RM400 for Category 2 or 3 (or legacy married=True)
    Both applied as: annual_tax = max(0, annual_tax - 400)
    """

    def test_personal_rebate_category1_low_income(self):
        """Category 1: RM400 personal rebate reduces tax.

        annual = 39,000; self-relief = 9,000; chargeable = 30,000
        Tax on 30,000 = 150 + (30,000-20,000)*3% = 450
        Personal rebate (chargeable 30,000 <= 35,000): 450 - 400 = 50
        Monthly = 50 / 12 ≈ 4.17
        """
        annual = 39_000  # chargeable = 39,000 - 9,000 = 30,000
        result = calculate_pcb(annual, resident=True, category=1)
        expected = round(50 / 12, 2)
        self.assertAlmostEqual(result, expected, places=2)

    def test_personal_and_spouse_rebate_category2_low_income(self):
        """Category 2: RM400 personal + RM400 spouse rebate = RM800 total.

        annual = 43,000; self + spouse relief = 13,000; chargeable = 30,000
        Tax on 30,000 = 450
        Personal rebate: max(0, 450-400) = 50
        Spouse rebate (Category 2, chargeable <= 35,000): max(0, 50-400) = 0
        Monthly = 0.00
        """
        annual = 43_000  # chargeable = 43,000 - 9,000 - 4,000 = 30,000
        result = calculate_pcb(annual, resident=True, category=2)
        self.assertEqual(result, 0.0)

    def test_personal_and_spouse_rebate_category3_low_income(self):
        """Category 3 (single parent): same RM800 total rebate as Category 2.

        annual = 43,000; self + single-parent relief = 13,000; chargeable = 30,000
        Tax on 30,000 = 450; both rebates applied → 0
        Monthly = 0.00
        """
        annual = 43_000
        result = calculate_pcb(annual, resident=True, category=3)
        self.assertEqual(result, 0.0)

    def test_no_rebate_when_chargeable_exceeds_35000(self):
        """No rebate when chargeable income > RM35,000.

        annual = 49,000; self + spouse relief = 13,000; chargeable = 36,000
        Tax on 36,000 = 600 + (36,000-35,000)*8% = 680
        No rebate (36,000 > 35,000)
        Monthly = 680 / 12 ≈ 56.67
        """
        annual = 49_000  # chargeable = 49,000 - 9,000 - 4,000 = 36,000
        result = calculate_pcb(annual, resident=True, category=2)
        expected = round(680 / 12, 2)
        self.assertAlmostEqual(result, expected, places=2)

    def test_rebate_does_not_push_tax_below_zero(self):
        """Rebate floors annual_tax at 0 — cannot be negative.

        annual = 20,000; chargeable = 11,000; tax = 60
        Personal rebate: max(0, 60-400) = 0
        Monthly = 0.00
        """
        annual = 20_000  # chargeable = 11,000, tax = 60
        result = calculate_pcb(annual, resident=True, category=1)
        self.assertEqual(result, 0.0)

    def test_non_resident_no_rebate(self):
        """Non-residents are not entitled to ITA s.6A rebates (flat 30% only)."""
        annual = 39_000  # qualifies for rebate as resident, but not as non-resident
        result = calculate_pcb(annual, resident=False)
        expected = round((annual * 0.30) / 12, 2)
        self.assertAlmostEqual(result, expected, places=2)

    def test_rebate_applies_with_legacy_married_flag(self):
        """Spouse rebate applies when married=True (legacy flag, no category param).

        annual = 39,000; self + spouse relief = 13,000; chargeable = 26,000
        Tax on 26,000 = 150 + (26,000-20,000)*3% = 330
        Personal rebate: max(0, 330-400) = 0
        Spouse rebate (married=True): max(0, 0-400) = 0
        Monthly = 0.00
        """
        annual = 39_000  # with married, chargeable = 39,000 - 13,000 = 26,000
        result = calculate_pcb(annual, resident=True, married=True)
        self.assertEqual(result, 0.0)

    def test_rebate_at_exact_35000_boundary(self):
        """Chargeable income exactly RM35,000 qualifies for rebate (inclusive boundary).

        annual = 44,000; self-relief = 9,000; chargeable = 35,000
        Tax on 35,000 = 150 + (35,000-20,000)*3% = 150 + 450 = 600
        Personal rebate (35,000 <= 35,000): 600 - 400 = 200
        Monthly = 200 / 12 ≈ 16.67
        """
        annual = 44_000  # chargeable = 35,000 exactly
        result = calculate_pcb(annual, resident=True, category=1)
        expected = round(200 / 12, 2)
        self.assertAlmostEqual(result, expected, places=2)

    def test_just_above_35000_no_rebate(self):
        """Chargeable income of RM35,001 does NOT qualify — rebate boundary is strict.

        annual = 44,001; self-relief = 9,000; chargeable = 35,001
        Tax on 35,001 = 600 + 1 * 8% = 600.08
        No rebate (35,001 > 35,000)
        Monthly = 600.08 / 12 ≈ 50.01
        """
        annual = 44_001  # chargeable = 35,001
        result = calculate_pcb(annual, resident=True, category=1)
        expected = round(600.08 / 12, 2)
        self.assertAlmostEqual(result, expected, places=2)

    def test_rebate_stacks_with_zakat_offset(self):
        """Rebate is applied before Zakat offset — both reduce PCB independently.

        annual = 39,000; chargeable = 30,000; tax = 450
        Personal rebate: 450 - 400 = 50; monthly = 50/12 ≈ 4.17
        annual_zakat = 600 → monthly_zakat = 50
        net_pcb = max(0, 4.17 - 50) = 0.00
        """
        annual = 39_000
        result = calculate_pcb(annual, resident=True, category=1, annual_zakat=600)
        self.assertEqual(result, 0.0)


class TestApprovedPensionSchemeExemption(FrappeTestCase):
    """US-085: ITA 1967 Schedule 6 paragraph 30 — approved pension scheme full exemption.

    Para 30: retirement gratuity from an approved company pension scheme for
    employee retiring at age >= 55 is FULLY exempt (100%).
    Para 25 (default): RM1,000 per completed year of service.
    """

    def test_age_55_approved_scheme_full_gratuity_exempt(self):
        """Age 55 with approved pension scheme — full gratuity exempt (para 30).

        Without gratuity:
          annual=480,000; chargeable=471,000 (self-relief 9,000)
          tax on 471,000 = 82,700 + (471,000-400,000)*24.5% = 82,700 + 17,395 = 100,095
          monthly = 100,095 / 12 = 8,341.25

        With approved_pension_scheme=True, age=55, gratuity=30,000:
          exempt_gratuity = 30,000 (100% — para 30)
          taxable_gratuity = 0; total_irregular = 0
          Result should equal the regular monthly PCB (no incremental tax).
        """
        annual = 480_000
        gratuity = 30_000
        years = 10

        regular = calculate_pcb(annual, resident=True, category=1)

        with_gratuity_approved = calculate_pcb(
            annual,
            resident=True,
            category=1,
            gratuity_amount=gratuity,
            years_of_service=years,
            approved_pension_scheme=True,
            employee_age=55,
        )

        # Full exemption: gratuity adds zero incremental PCB
        self.assertAlmostEqual(regular, with_gratuity_approved, places=2)

    def test_age_60_approved_scheme_full_gratuity_exempt(self):
        """Age 60 (compulsory retirement) with approved pension scheme — still fully exempt."""
        annual = 360_000
        gratuity = 50_000

        regular = calculate_pcb(annual, resident=True, category=1)
        with_gratuity = calculate_pcb(
            annual,
            resident=True,
            category=1,
            gratuity_amount=gratuity,
            years_of_service=20,
            approved_pension_scheme=True,
            employee_age=60,
        )

        self.assertAlmostEqual(regular, with_gratuity, places=2)

    def test_age_55_without_approved_scheme_uses_para25(self):
        """Age 55 WITHOUT approved pension scheme — falls back to RM1,000/year (para 25).

        annual=480,000; gratuity=30,000; years=10
        Para 25 exempt = min(30,000, 10*1,000) = 10,000
        taxable_gratuity = 20,000

        chargeable base = 471,000
        tax_base = 100,095; monthly = 8,341.25

        total_chargeable = 471,000 + 20,000 = 491,000
        tax_with = 82,700 + (491,000-400,000)*24.5% = 82,700 + 22,295 = 105,000 - wait:
          471,000 - 9,000 relief = 462,000 + 20,000 = 482,000... let me recompute:
          chargeable = max(0, 480,000 - 9,000) = 471,000
          total_chargeable_with_irr = 471,000 + 20,000 = 491,000
          tax_with = 82,700 + (491,000-400,000)*24.5% = 82,700 + 22,295 = 105,000 - 5 = 104,995
          Actually: 491,000 - 400,000 = 91,000; 91,000 * 0.245 = 22,295
          tax_with = 82,700 + 22,295 = 104,995
          irregular_pcb = 104,995 - 100,095 = 4,900
          monthly = 8,341.25 + 4,900 = 13,241.25

        Without approved scheme, gratuity is taxable after para 25, so PCB > regular monthly.
        """
        annual = 480_000
        gratuity = 30_000
        years = 10

        regular = calculate_pcb(annual, resident=True, category=1)
        with_gratuity_no_scheme = calculate_pcb(
            annual,
            resident=True,
            category=1,
            gratuity_amount=gratuity,
            years_of_service=years,
            approved_pension_scheme=False,
            employee_age=55,
        )

        # Without approved scheme, taxable gratuity adds incremental PCB
        self.assertGreater(with_gratuity_no_scheme, regular)

    def test_age_below_55_approved_scheme_does_not_apply(self):
        """Approved scheme flag but age < 55 — para 25 applies (not para 30)."""
        annual = 480_000
        gratuity = 30_000
        years = 10

        result_age_54 = calculate_pcb(
            annual,
            resident=True,
            category=1,
            gratuity_amount=gratuity,
            years_of_service=years,
            approved_pension_scheme=True,
            employee_age=54,
        )

        result_age_55 = calculate_pcb(
            annual,
            resident=True,
            category=1,
            gratuity_amount=gratuity,
            years_of_service=years,
            approved_pension_scheme=True,
            employee_age=55,
        )

        # Age 54 with approved scheme: para 25 applies → taxable gratuity → higher PCB
        # Age 55 with approved scheme: para 30 applies → full exempt → lower PCB
        self.assertGreater(result_age_54, result_age_55)

    def test_approved_scheme_no_gratuity_no_effect(self):
        """Approved pension scheme flag with no gratuity — same as normal PCB."""
        annual = 240_000
        regular = calculate_pcb(annual, resident=True, category=1)
        with_scheme = calculate_pcb(
            annual,
            resident=True,
            category=1,
            approved_pension_scheme=True,
            employee_age=58,
        )
        self.assertEqual(regular, with_scheme)

    def test_approved_scheme_age_55_vs_para25_lower_pcb(self):
        """Para 30 (full exempt) always produces <= PCB vs para 25 (RM1,000/year).

        With RM30,000 gratuity and 10 years of service:
        - Para 25 exempts RM10,000 → RM20,000 taxable
        - Para 30 exempts RM30,000 → RM0 taxable
        Para 30 PCB must be strictly less than para 25 PCB for positive taxable gratuity.
        """
        annual = 300_000
        gratuity = 30_000
        years = 10

        pcb_para25 = calculate_pcb(
            annual,
            resident=True,
            category=1,
            gratuity_amount=gratuity,
            years_of_service=years,
            approved_pension_scheme=False,
        )

        pcb_para30 = calculate_pcb(
            annual,
            resident=True,
            category=1,
            gratuity_amount=gratuity,
            years_of_service=years,
            approved_pension_scheme=True,
            employee_age=55,
        )

        self.assertLess(pcb_para30, pcb_para25)
