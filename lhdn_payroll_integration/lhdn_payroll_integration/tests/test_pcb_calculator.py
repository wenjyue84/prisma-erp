"""Tests for PCB/MTD calculator — US-004, US-018, and US-035.

Covers:
- Single resident: progressive tax bands
- Married with children: reliefs reduce chargeable income
- Non-resident: flat 30%
- Zero income: returns 0.0
- validate_pcb_amount: returns warning dict
- Bonus/irregular payment: one-twelfth annualisation rule (US-018)
- Gratuity/leave encashment: Schedule 6 para 25 exemption (US-035)
"""
from unittest.mock import MagicMock, patch

from frappe.tests.utils import FrappeTestCase

from lhdn_payroll_integration.services.pcb_calculator import (
    calculate_pcb,
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
        Annual tax = 60; Monthly = 5.00
        """
        result = calculate_pcb(20_000, resident=True, married=False, children=0)
        self.assertAlmostEqual(result, 5.00, places=2)

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
