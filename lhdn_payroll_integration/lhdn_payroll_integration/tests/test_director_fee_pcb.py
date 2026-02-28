"""Tests for US-103: Director Fee-Only MTD Lump-Sum Formula.

Verifies:
- calculate_director_fee_pcb() implements LHDN PCB Spec 2026 Section 5 correctly
- Fee-only formula: MTD = tax_on(monthly_equivalent) x months_covered
  where monthly_equivalent = total_fee / months_covered
- Directors with monthly salary: existing bonus annualization formula used instead
- Custom field custom_director_fee_payment_frequency exists on Employee
- CP39 income type distinction (Director Fee uses 036 classification code)
"""
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from lhdn_payroll_integration.services.pcb_calculator import (
    _compute_tax_on_chargeable_income,
    calculate_director_fee_pcb,
    calculate_pcb,
)

# Standard self relief for resident (RM9,000)
_SELF_RELIEF = 9_000


class TestDirectorFeePcbFeeOnly(FrappeTestCase):
    """Tests for calculate_director_fee_pcb() -- fee-only director formula."""

    def test_monthly_fee_single_month_covered(self):
        """Monthly fee: months_covered=1, formula degenerates to regular monthly PCB.

        total_fee=RM5,000/month, single (category 1)
        monthly_equivalent = 5,000/1 = 5,000
        annual_equivalent = 60,000
        chargeable = 60,000 - 9,000 = 51,000
        annual_tax = 0+150+450+1200+130 = 1,930
        monthly_tax = 1,930/12 approx 160.83
        MTD = 160.83 * 1 = 160.83
        Should equal calculate_pcb(60,000, resident=True) approx 160.83
        """
        total_fee = 5_000.0  # monthly
        months = 1
        result = calculate_director_fee_pcb(total_fee, months, resident=True, category=1)
        expected = calculate_pcb(60_000, resident=True)
        self.assertAlmostEqual(result, expected, places=2)

    def test_quarterly_fee(self):
        """Quarterly fee: months_covered=3.

        total_fee = RM30,000 quarterly, category 1 (single)
        monthly_equivalent = 30,000/3 = 10,000
        annual_equivalent = 120,000
        chargeable = 120,000 - 9,000 = 111,000
        annual_tax = 10,700 + (111,000 - 100,000) * 0.24 = 10,700 + 2,640 = 13,340
        monthly_tax = 13,340/12 approx 1,111.67
        MTD = 1,111.67 * 3 = 3,335.00
        """
        total_fee = 30_000.0
        months = 3
        result = calculate_director_fee_pcb(total_fee, months, resident=True, category=1)
        annual = (total_fee / months) * 12  # 120,000
        chargeable = annual - _SELF_RELIEF  # 111,000
        annual_tax = _compute_tax_on_chargeable_income(chargeable)  # 13,340
        monthly_tax = annual_tax / 12
        expected = round(monthly_tax * months, 2)
        self.assertAlmostEqual(result, expected, places=2)

    def test_annual_fee(self):
        """Annual fee: months_covered=12, full year MTD.

        total_fee = RM60,000 annually, category 1 (single)
        monthly_equivalent = 60,000/12 = 5,000
        annual_equivalent = 60,000
        chargeable = 60,000 - 9,000 = 51,000
        annual_tax = 1,930
        monthly_tax = 1,930/12
        MTD = monthly_tax * 12 = 1,930 (full year)
        """
        total_fee = 60_000.0
        months = 12
        result = calculate_director_fee_pcb(total_fee, months, resident=True, category=1)
        annual = (total_fee / months) * 12  # = 60,000
        chargeable = annual - _SELF_RELIEF  # 51,000
        annual_tax = _compute_tax_on_chargeable_income(chargeable)  # 1,930
        monthly_tax = annual_tax / 12
        expected = round(monthly_tax * months, 2)
        self.assertAlmostEqual(result, expected, places=2)

    def test_high_annual_fee(self):
        """High annual fee for wealthy director.

        total_fee = RM600,000 annual, months=12, category 1
        monthly_equivalent = 50,000
        annual_equivalent = 600,000
        chargeable = 600,000 - 9,000 = 591,000
        annual_tax = 82,700 + (591,000 - 400,000) * 0.245 = 82,700 + 46,795 = 129,495
        monthly_tax = 129,495/12
        MTD = monthly_tax * 12 = 129,495.00
        """
        total_fee = 600_000.0
        months = 12
        result = calculate_director_fee_pcb(total_fee, months, resident=True, category=1)
        annual = (total_fee / months) * 12  # 600,000
        chargeable = annual - _SELF_RELIEF  # 591,000
        annual_tax = _compute_tax_on_chargeable_income(chargeable)
        monthly_tax = annual_tax / 12
        expected = round(monthly_tax * months, 2)
        self.assertAlmostEqual(result, expected, places=2)

    def test_non_resident_director_fee_flat_30_pct(self):
        """Non-resident director: flat 30% on total fee (no reliefs).

        total_fee = RM30,000, months=3
        MTD = 30,000 * 0.30 = 9,000
        """
        total_fee = 30_000.0
        months = 3
        result = calculate_director_fee_pcb(total_fee, months, resident=False)
        expected = round(total_fee * 0.30, 2)
        self.assertAlmostEqual(result, expected, places=2)

    def test_zero_fee_returns_zero(self):
        """Zero fee yields zero MTD."""
        result = calculate_director_fee_pcb(0.0, 3, resident=True)
        self.assertEqual(result, 0.0)

    def test_category2_spouse_relief_applied(self):
        """Category 2 (non-working spouse): RM4,000 spouse relief reduces MTD.

        total_fee = RM30,000 quarterly, months=3, category 2
        monthly_equivalent = 10,000
        annual_equivalent = 120,000
        chargeable = 120,000 - 9,000 - 4,000 = 107,000
        annual_tax = 10,700 + (107,000 - 100,000) * 0.24 = 10,700 + 1,680 = 12,380
        monthly_tax = 12,380/12
        MTD = monthly_tax * 3
        """
        total_fee = 30_000.0
        months = 3
        result = calculate_director_fee_pcb(total_fee, months, resident=True, category=2)
        annual = (total_fee / months) * 12  # 120,000
        chargeable = annual - _SELF_RELIEF - 4_000  # 107,000
        annual_tax = _compute_tax_on_chargeable_income(chargeable)
        monthly_tax = annual_tax / 12
        expected = round(monthly_tax * months, 2)
        self.assertAlmostEqual(result, expected, places=2)

    def test_quarterly_fee_annual_total_matches_monthly(self):
        """Verify fee-only formula gives same annual MTD regardless of payment frequency.

        For constant quarterly fees, annual MTD = 4 x quarterly MTD
        should be within RM1.00 of annual tax from 12 monthly payments
        (rounding differences accumulate across periods).
        total_fee=RM15,000 quarterly (=RM60,000/year), category 1
        """
        total_fee = 15_000.0
        months = 3
        quarterly_mtd = calculate_director_fee_pcb(total_fee, months, resident=True, category=1)
        annual_mtd = quarterly_mtd * 4
        # Compare against full-year PCB on RM60,000 annual income
        full_year_pcb = calculate_pcb(60_000, resident=True) * 12
        # Allow RM1.00 tolerance for per-period rounding accumulation
        self.assertAlmostEqual(annual_mtd, full_year_pcb, delta=1.0)

    def test_zakat_offset_applied_to_fee_pcb(self):
        """Annual Zakat reduces MTD ringgit-for-ringgit.

        total_fee=RM30,000 quarterly, months=3, annual_zakat=RM2,400
        Expected: MTD reduced by 2,400/12*3 = RM600 vs no-zakat case
        """
        total_fee = 30_000.0
        months = 3
        annual_zakat = 2_400.0
        result_no_zakat = calculate_director_fee_pcb(total_fee, months, resident=True, category=1)
        result_with_zakat = calculate_director_fee_pcb(
            total_fee, months, resident=True, category=1, annual_zakat=annual_zakat
        )
        zakat_monthly = annual_zakat / 12
        expected_reduction = round(zakat_monthly * months, 2)
        actual_reduction = round(result_no_zakat - result_with_zakat, 2)
        self.assertAlmostEqual(actual_reduction, expected_reduction, places=2)

    def test_monthly_vs_quarterly_same_annual_total(self):
        """Monthly (1-month) vs quarterly (3-month) gives same annual MTD.

        Both payment modes on same annual income imply same annual tax liability.
        monthly: 12 monthly payments of (fee RM10,000, months=1)
        quarterly: 4 quarterly payments of (fee RM30,000, months=3)
        Allow RM1.00 tolerance for per-period rounding accumulation.
        """
        monthly_fee = 10_000.0
        quarterly_fee = 30_000.0
        monthly_mtd = calculate_director_fee_pcb(monthly_fee, 1, resident=True, category=1)
        quarterly_mtd = calculate_director_fee_pcb(quarterly_fee, 3, resident=True, category=1)
        # Annual: 12 monthly payments vs 4 quarterly payments
        annual_via_monthly = round(monthly_mtd * 12, 2)
        annual_via_quarterly = round(quarterly_mtd * 4, 2)
        # Allow RM1.00 tolerance for per-period rounding accumulation
        self.assertAlmostEqual(annual_via_monthly, annual_via_quarterly, delta=1.0)


class TestDirectorFeePcbVsBonusFormula(FrappeTestCase):
    """Verify that directors WITH monthly salary use bonus annualization (existing logic)."""

    def test_director_with_salary_bonus_formula_differs_from_fee_only(self):
        """Director with RM5,000/month salary + RM15,000 quarterly fee.

        For mixed income, calculate_pcb() bonus formula is used (adds fee to salary).
        Fee-only formula is only for directors WITHOUT monthly salary.
        The two formulas produce different results for mixed income.
        """
        annual_salary = 60_000.0  # RM5,000/month
        bonus_amount = 15_000.0   # quarterly director fee treated as bonus

        # Bonus annualization (existing calculate_pcb)
        bonus_mtd = calculate_pcb(annual_salary, resident=True, bonus_amount=bonus_amount)

        # Fee-only formula on just the fee portion (not correct path for mixed income)
        fee_only_mtd = calculate_director_fee_pcb(bonus_amount, 3, resident=True, category=1)

        # Both return positive floats
        self.assertGreater(bonus_mtd, 0)
        self.assertGreater(fee_only_mtd, 0)
        # The bonus formula result for combined income differs from fee-only
        self.assertNotAlmostEqual(bonus_mtd, fee_only_mtd, places=2)


class TestDirectorFeePaymentFrequencyField(FrappeTestCase):
    """Tests for custom_director_fee_payment_frequency custom field on Employee."""

    def test_custom_director_fee_payment_frequency_field_exists(self):
        """Custom field custom_director_fee_payment_frequency must exist on Employee."""
        exists = frappe.db.exists(
            "Custom Field",
            {"dt": "Employee", "fieldname": "custom_director_fee_payment_frequency"},
        )
        self.assertTrue(
            exists,
            "Custom Field 'custom_director_fee_payment_frequency' not found on Employee",
        )

    def test_custom_director_fee_payment_frequency_is_select(self):
        """Field type must be Select."""
        fieldtype = frappe.db.get_value(
            "Custom Field",
            {"dt": "Employee", "fieldname": "custom_director_fee_payment_frequency"},
            "fieldtype",
        )
        self.assertEqual(fieldtype, "Select")

    def test_custom_director_fee_payment_frequency_options(self):
        """Options must include Monthly, Quarterly, Annually, Irregular."""
        options = frappe.db.get_value(
            "Custom Field",
            {"dt": "Employee", "fieldname": "custom_director_fee_payment_frequency"},
            "options",
        )
        options_str = options or ""
        for expected in ("Monthly", "Quarterly", "Annually", "Irregular"):
            self.assertIn(expected, options_str, f"Missing option: {expected}")


class TestDirectorFeeIncomeTypeClassification(FrappeTestCase):
    """Tests for CP39/EA Form income type classification for director fees."""

    def test_director_fee_classification_code_is_036(self):
        """Director Fee must map to CP39 classification code 036."""
        from lhdn_payroll_integration.lhdn_payroll_integration.services.exemption_filter import (
            get_default_classification_code,
        )
        emp = MagicMock()
        emp.custom_worker_type = "Director"
        emp.custom_director_payment_type = "Director Fee"
        code = get_default_classification_code("Director", employee=emp)
        self.assertEqual(code, "036")

    def test_director_salary_classification_code_is_004(self):
        """Director Salary must map to CP39 classification code 004."""
        from lhdn_payroll_integration.lhdn_payroll_integration.services.exemption_filter import (
            get_default_classification_code,
        )
        emp = MagicMock()
        emp.custom_worker_type = "Director"
        emp.custom_director_payment_type = "Director Salary"
        code = get_default_classification_code("Director", employee=emp)
        self.assertEqual(code, "004")
