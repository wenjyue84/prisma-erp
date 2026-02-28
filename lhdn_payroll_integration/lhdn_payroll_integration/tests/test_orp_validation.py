"""Tests for US-069: Ordinary Rate of Pay (ORP) Calculator and Overtime Validation.

Employment Act 1955 S.60A(3):
  - OT 1.5x on Normal day
  - OT 2.0x on Rest Day (full day)
  - OT 3.0x on Public Holiday
  - Applies to EA-covered employees earning <= RM4,000/month
"""

from unittest.mock import MagicMock, patch

from frappe.tests.utils import FrappeTestCase

from lhdn_payroll_integration.utils.employment_compliance import (
    ORP_SALARY_THRESHOLD,
    OT_MULTIPLIERS,
    calculate_orp,
    check_overtime_rate,
)
from lhdn_payroll_integration.utils.validation import validate_document_for_lhdn


# ---------------------------------------------------------------------------
# ORP Constants
# ---------------------------------------------------------------------------


class TestORPConstants(FrappeTestCase):
    """Verify ORP-related constants are correct per Employment Act."""

    def test_salary_threshold_is_4000(self):
        self.assertEqual(ORP_SALARY_THRESHOLD, 4000.0)

    def test_normal_multiplier_is_1_5(self):
        self.assertAlmostEqual(OT_MULTIPLIERS["Normal"], 1.5)

    def test_rest_day_multiplier_is_2_0(self):
        self.assertAlmostEqual(OT_MULTIPLIERS["Rest Day"], 2.0)

    def test_public_holiday_multiplier_is_3_0(self):
        self.assertAlmostEqual(OT_MULTIPLIERS["Public Holiday"], 3.0)

    def test_all_three_day_types_present(self):
        self.assertIn("Normal", OT_MULTIPLIERS)
        self.assertIn("Rest Day", OT_MULTIPLIERS)
        self.assertIn("Public Holiday", OT_MULTIPLIERS)


# ---------------------------------------------------------------------------
# calculate_orp()
# ---------------------------------------------------------------------------


class TestCalculateORP(FrappeTestCase):
    """Test calculate_orp() utility."""

    def test_daily_orp_is_monthly_divided_by_26(self):
        result = calculate_orp(2600)
        self.assertAlmostEqual(result["daily"], 100.0)

    def test_daily_orp_standard_salary(self):
        result = calculate_orp(3000)
        self.assertAlmostEqual(result["daily"], 3000 / 26.0)

    def test_hourly_orp_returned_when_hours_provided(self):
        result = calculate_orp(2600, contracted_hours_per_month=160)
        self.assertAlmostEqual(result["hourly"], 2600 / 160.0)

    def test_hourly_orp_is_none_without_hours(self):
        result = calculate_orp(2600)
        self.assertIsNone(result["hourly"])

    def test_zero_hours_returns_none_hourly(self):
        result = calculate_orp(2600, contracted_hours_per_month=0)
        self.assertIsNone(result["hourly"])

    def test_result_has_daily_and_hourly_keys(self):
        result = calculate_orp(2000, contracted_hours_per_month=160)
        self.assertIn("daily", result)
        self.assertIn("hourly", result)

    def test_orp_with_4000_salary(self):
        result = calculate_orp(4000, contracted_hours_per_month=160)
        self.assertAlmostEqual(result["daily"], 4000 / 26.0)
        self.assertAlmostEqual(result["hourly"], 4000 / 160.0)


# ---------------------------------------------------------------------------
# check_overtime_rate()
# ---------------------------------------------------------------------------


class TestCheckOvertimeRate(FrappeTestCase):
    """Test check_overtime_rate() for statutory OT compliance."""

    # --- Normal day (1.5x) ---

    def test_normal_day_ot_compliant(self):
        # ORP = 3000/160 = 18.75/h, 1.5x, 2h → min = 56.25; pay 60 → OK
        result = check_overtime_rate(3000, 60.0, 2, "Normal", 160)
        self.assertTrue(result["compliant"])
        self.assertIsNone(result["warning"])

    def test_normal_day_ot_underpaid_triggers_warning(self):
        # ORP = 3000/160 = 18.75/h, 1.5x, 2h → min = 56.25; pay 30 → underpaid
        result = check_overtime_rate(3000, 30.0, 2, "Normal", 160)
        self.assertFalse(result["compliant"])
        self.assertIsNotNone(result["warning"])
        self.assertIn("1.5", result["warning"])

    def test_normal_day_multiplier_in_result(self):
        result = check_overtime_rate(3000, 60.0, 2, "Normal", 160)
        self.assertAlmostEqual(result["multiplier"], 1.5)

    # --- Rest Day (2.0x) ---

    def test_rest_day_ot_underpaid_triggers_warning(self):
        # ORP = 3000/160 = 18.75/h, 2.0x, 2h → min = 75; pay 30 → underpaid
        result = check_overtime_rate(3000, 30.0, 2, "Rest Day", 160)
        self.assertFalse(result["compliant"])
        self.assertIsNotNone(result["warning"])
        self.assertIn("2.0", result["warning"])

    def test_rest_day_ot_compliant(self):
        # ORP = 3000/160 = 18.75/h, 2.0x, 2h → min = 75; pay 80 → OK
        result = check_overtime_rate(3000, 80.0, 2, "Rest Day", 160)
        self.assertTrue(result["compliant"])

    # --- Public Holiday (3.0x) ---

    def test_public_holiday_ot_underpaid_triggers_warning(self):
        # ORP = 3000/160 = 18.75/h, 3.0x, 2h → min = 112.5; pay 30 → underpaid
        result = check_overtime_rate(3000, 30.0, 2, "Public Holiday", 160)
        self.assertFalse(result["compliant"])
        self.assertIsNotNone(result["warning"])
        self.assertIn("3.0", result["warning"])

    def test_public_holiday_ot_compliant(self):
        result = check_overtime_rate(3000, 120.0, 2, "Public Holiday", 160)
        self.assertTrue(result["compliant"])

    # --- Salary threshold ---

    def test_above_salary_threshold_not_checked(self):
        # EA does not apply above RM4,000/month
        result = check_overtime_rate(4001, 1.0, 2, "Normal", 160)
        self.assertTrue(result["compliant"])
        self.assertIsNone(result["warning"])

    def test_exact_salary_threshold_is_checked(self):
        # RM4,000 exactly — EA still applies
        # ORP = 4000/160 = 25/h, 1.5x, 2h → min = 75; pay 30 → underpaid
        result = check_overtime_rate(4000, 30.0, 2, "Normal", 160)
        self.assertFalse(result["compliant"])

    def test_just_below_threshold_is_checked(self):
        result = check_overtime_rate(3999, 30.0, 2, "Normal", 160)
        self.assertFalse(result["compliant"])

    # --- Edge cases ---

    def test_zero_ot_hours_no_warning(self):
        result = check_overtime_rate(3000, 0.0, 0, "Normal", 160)
        self.assertTrue(result["compliant"])
        self.assertIsNone(result["warning"])

    def test_none_ot_hours_no_warning(self):
        result = check_overtime_rate(3000, 0.0, None, "Normal", 160)
        self.assertTrue(result["compliant"])

    def test_result_contains_minimum_amount(self):
        # ORP = 3000/160 = 18.75/h, 1.5x, 2h → min = 56.25
        result = check_overtime_rate(3000, 60.0, 2, "Normal", 160)
        self.assertAlmostEqual(result["minimum_amount"], 56.25)

    def test_result_contains_orp_hourly(self):
        result = check_overtime_rate(3000, 60.0, 2, "Normal", 160)
        self.assertAlmostEqual(result["orp_hourly"], 3000 / 160.0)

    def test_fallback_orp_without_contracted_hours(self):
        # Without contracted_hours, uses daily/8 = (3000/26)/8
        result = check_overtime_rate(3000, 200.0, 2, "Normal")
        self.assertIn("compliant", result)
        expected_orp = (3000 / 26.0) / 8.0
        self.assertAlmostEqual(result["orp_hourly"], expected_orp, places=4)


# ---------------------------------------------------------------------------
# validate_document_for_lhdn() — OT integration
# ---------------------------------------------------------------------------


class TestValidateDocumentForLhdnOT(FrappeTestCase):
    """Test OT validation integrated into validate_document_for_lhdn()."""

    def _make_salary_slip(self, gross_pay, earnings=None):
        doc = MagicMock()
        doc.get = lambda key, default=None: {
            "doctype": "Salary Slip",
            "base_gross_pay": gross_pay,
            "gross_pay": gross_pay,
            "employee": "EMP-OT-001",
            "earnings": earnings or [],
        }.get(key, default)
        doc.doctype = "Salary Slip"
        return doc

    def _make_ot_component(self, amount, ot_hours, day_type="Normal"):
        comp = MagicMock()
        comp.get = lambda key, default=None: {
            "salary_component": "OT Pay",
            "amount": amount,
            "custom_day_type": day_type,
            "custom_ot_hours_claimed": ot_hours,
        }.get(key, default)
        return comp

    def _make_emp_mock(self, contracted_hours=160):
        emp = MagicMock()
        emp.get = lambda key, default=None: {
            "custom_employment_type": "Full-time",
            "custom_contracted_hours_per_month": contracted_hours,
        }.get(key, default)
        return emp

    @patch("lhdn_payroll_integration.utils.validation.frappe")
    @patch("lhdn_payroll_integration.utils.employment_compliance.frappe")
    def test_normal_day_ot_underpaid_triggers_msgprint(self, mock_emp_frappe, mock_val_frappe):
        mock_val_frappe.db.exists.return_value = True
        mock_val_frappe.get_cached_doc.return_value = self._make_emp_mock()

        # ORP = 3000/160 = 18.75, 1.5x, 2h → min = 56.25; pay 10 → warning
        comp = self._make_ot_component(amount=10.0, ot_hours=2, day_type="Normal")
        doc = self._make_salary_slip(gross_pay=3000, earnings=[comp])
        validate_document_for_lhdn(doc)

        ot_calls = [
            c for c in mock_val_frappe.msgprint.call_args_list
            if "Overtime" in str(c) or "overtime" in str(c) or "OT" in str(c)
        ]
        self.assertTrue(len(ot_calls) >= 1, "Expected at least one OT warning msgprint")

    @patch("lhdn_payroll_integration.utils.validation.frappe")
    @patch("lhdn_payroll_integration.utils.employment_compliance.frappe")
    def test_normal_day_ot_compliant_no_ot_msgprint(self, mock_emp_frappe, mock_val_frappe):
        mock_val_frappe.db.exists.return_value = True
        mock_val_frappe.get_cached_doc.return_value = self._make_emp_mock()

        # ORP = 3000/160 = 18.75, 1.5x, 2h → min = 56.25; pay 60 → compliant
        comp = self._make_ot_component(amount=60.0, ot_hours=2, day_type="Normal")
        doc = self._make_salary_slip(gross_pay=3000, earnings=[comp])
        validate_document_for_lhdn(doc)

        ot_calls = [
            c for c in mock_val_frappe.msgprint.call_args_list
            if "Overtime" in str(c)
        ]
        self.assertEqual(len(ot_calls), 0, "No OT warning expected when rate is compliant")

    @patch("lhdn_payroll_integration.utils.validation.frappe")
    @patch("lhdn_payroll_integration.utils.employment_compliance.frappe")
    def test_rest_day_ot_triggers_2x_warning(self, mock_emp_frappe, mock_val_frappe):
        mock_val_frappe.db.exists.return_value = True
        mock_val_frappe.get_cached_doc.return_value = self._make_emp_mock()

        comp = self._make_ot_component(amount=30.0, ot_hours=2, day_type="Rest Day")
        doc = self._make_salary_slip(gross_pay=3000, earnings=[comp])
        validate_document_for_lhdn(doc)

        ot_calls = [c for c in mock_val_frappe.msgprint.call_args_list if "Overtime" in str(c)]
        self.assertTrue(len(ot_calls) >= 1)

    @patch("lhdn_payroll_integration.utils.validation.frappe")
    @patch("lhdn_payroll_integration.utils.employment_compliance.frappe")
    def test_public_holiday_ot_triggers_3x_warning(self, mock_emp_frappe, mock_val_frappe):
        mock_val_frappe.db.exists.return_value = True
        mock_val_frappe.get_cached_doc.return_value = self._make_emp_mock()

        comp = self._make_ot_component(amount=30.0, ot_hours=2, day_type="Public Holiday")
        doc = self._make_salary_slip(gross_pay=3000, earnings=[comp])
        validate_document_for_lhdn(doc)

        ot_calls = [c for c in mock_val_frappe.msgprint.call_args_list if "Overtime" in str(c)]
        self.assertTrue(len(ot_calls) >= 1)

    @patch("lhdn_payroll_integration.utils.validation.frappe")
    @patch("lhdn_payroll_integration.utils.employment_compliance.frappe")
    def test_salary_above_4000_no_ot_warning(self, mock_emp_frappe, mock_val_frappe):
        mock_val_frappe.db.exists.return_value = True
        mock_val_frappe.get_cached_doc.return_value = self._make_emp_mock()

        # Salary above RM4,000 — EA OT provisions do not apply
        comp = self._make_ot_component(amount=10.0, ot_hours=2, day_type="Normal")
        doc = self._make_salary_slip(gross_pay=5000, earnings=[comp])
        validate_document_for_lhdn(doc)

        ot_calls = [
            c for c in mock_val_frappe.msgprint.call_args_list
            if "Overtime" in str(c) or "overtime" in str(c)
        ]
        self.assertEqual(len(ot_calls), 0)

    @patch("lhdn_payroll_integration.utils.validation.frappe")
    def test_component_without_day_type_skipped(self, mock_val_frappe):
        mock_val_frappe.db.exists.return_value = False

        comp = MagicMock()
        comp.get = lambda key, default=None: {
            "salary_component": "Basic Salary",
            "amount": 3000.0,
            "custom_day_type": None,
            "custom_ot_hours_claimed": None,
        }.get(key, default)
        doc = self._make_salary_slip(gross_pay=3000, earnings=[comp])
        validate_document_for_lhdn(doc)

        ot_calls = [c for c in mock_val_frappe.msgprint.call_args_list if "Overtime" in str(c)]
        self.assertEqual(len(ot_calls), 0)

    @patch("lhdn_payroll_integration.utils.validation.frappe")
    @patch("lhdn_payroll_integration.utils.employment_compliance.frappe")
    def test_multiple_ot_components_each_checked(self, mock_emp_frappe, mock_val_frappe):
        mock_val_frappe.db.exists.return_value = True
        mock_val_frappe.get_cached_doc.return_value = self._make_emp_mock()

        comp_normal = self._make_ot_component(amount=5.0, ot_hours=2, day_type="Normal")
        comp_ph = self._make_ot_component(amount=5.0, ot_hours=2, day_type="Public Holiday")
        doc = self._make_salary_slip(gross_pay=3000, earnings=[comp_normal, comp_ph])
        validate_document_for_lhdn(doc)

        ot_calls = [c for c in mock_val_frappe.msgprint.call_args_list if "Overtime" in str(c)]
        # Both components are underpaid → 2 warnings
        self.assertEqual(len(ot_calls), 2)
