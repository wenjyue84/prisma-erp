"""Tests for US-119: Public Holiday Work Pay Calculator (Section 60D Employment Act).

Employment Act 1955 Section 60D: EA-covered employees (wage <= RM4,000/month)
working on a public holiday are entitled to:
  - Their regular daily wage (already in monthly salary)
  - PLUS 2 additional days' wages (the "premium")
  Total effective pay = 3x normal daily wage.

Section 60A: Overtime on a public holiday (hours beyond normal working hours)
is paid at 3x the hourly ORP rate.

Section 60I: ORP daily = monthly_salary / 26 for monthly-rated employees.

Key test: RM3,000/month employee works 8h on PH:
  - ORP daily = 3000 / 26 = 115.3846...
  - Additional premium = 2 x 115.3846 = 230.77 (rounded)
  - OT per hour beyond 8h = 3 x (115.3846 / 8) = 3 x 14.4231 = 43.27/h
"""

from unittest.mock import MagicMock, patch

from frappe.tests.utils import FrappeTestCase

from lhdn_payroll_integration.utils.employment_compliance import (
    EA_PUBLIC_HOLIDAYS_PER_YEAR,
    ORP_SALARY_THRESHOLD,
    PH_OT_HOURLY_MULTIPLIER,
    PH_WORK_ADDITIONAL_MULTIPLIER,
    add_ph_oil_credit,
    calculate_ph_overtime,
    calculate_ph_work_premium,
    flag_payroll_public_holiday_dates,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class TestPHConstants(FrappeTestCase):
    """Verify PH pay constants are correct per Employment Act."""

    def test_ea_public_holidays_per_year_is_11(self):
        self.assertEqual(EA_PUBLIC_HOLIDAYS_PER_YEAR, 11)

    def test_ph_work_additional_multiplier_is_2(self):
        self.assertAlmostEqual(PH_WORK_ADDITIONAL_MULTIPLIER, 2.0)

    def test_ph_ot_hourly_multiplier_is_3(self):
        self.assertAlmostEqual(PH_OT_HOURLY_MULTIPLIER, 3.0)


# ---------------------------------------------------------------------------
# calculate_ph_work_premium()
# ---------------------------------------------------------------------------


class TestCalculatePHWorkPremium(FrappeTestCase):
    """Test the additional pay premium for working on a Public Holiday (S.60D)."""

    def test_rm3000_employee_premium_is_230_77(self):
        """Canonical acceptance criterion: RM3,000 employee, premium = RM3,000/26 x 2."""
        result = calculate_ph_work_premium(3000)
        # 3000 / 26 = 115.3846...; x 2 = 230.769...
        self.assertAlmostEqual(result["premium"], 3000 / 26.0 * 2, places=4)
        self.assertAlmostEqual(result["premium"], 230.769, places=2)

    def test_orp_daily_is_monthly_divided_by_26(self):
        result = calculate_ph_work_premium(3000)
        self.assertAlmostEqual(result["orp_daily"], 3000 / 26.0, places=4)

    def test_multiplier_is_2(self):
        result = calculate_ph_work_premium(3000)
        self.assertAlmostEqual(result["multiplier"], 2.0)

    def test_ea_covered_true_below_4000(self):
        result = calculate_ph_work_premium(3000)
        self.assertTrue(result["ea_covered"])

    def test_ea_covered_true_at_exactly_4000(self):
        result = calculate_ph_work_premium(4000)
        self.assertTrue(result["ea_covered"])

    def test_ea_covered_false_above_4000(self):
        result = calculate_ph_work_premium(4001)
        self.assertFalse(result["ea_covered"])

    def test_no_warning_for_ea_covered_employee(self):
        result = calculate_ph_work_premium(3000)
        self.assertIsNone(result["warning"])

    def test_warning_for_above_threshold_employee(self):
        result = calculate_ph_work_premium(5000)
        self.assertIsNotNone(result["warning"])
        self.assertIn("employment contract", result["warning"])
        self.assertIn("Section 60D", result["warning"])

    def test_rm2000_employee_premium(self):
        result = calculate_ph_work_premium(2000)
        self.assertAlmostEqual(result["premium"], 2000 / 26.0 * 2, places=4)

    def test_rm4000_employee_premium(self):
        result = calculate_ph_work_premium(4000)
        self.assertAlmostEqual(result["premium"], 4000 / 26.0 * 2, places=4)

    def test_result_has_required_keys(self):
        result = calculate_ph_work_premium(3000)
        self.assertIn("premium", result)
        self.assertIn("orp_daily", result)
        self.assertIn("multiplier", result)
        self.assertIn("ea_covered", result)
        self.assertIn("warning", result)

    def test_normal_daily_hours_param_does_not_affect_premium(self):
        """Premium is per-day (not per-hour); changing daily hours doesn't change premium."""
        result_8h = calculate_ph_work_premium(3000, normal_daily_hours=8)
        result_7h = calculate_ph_work_premium(3000, normal_daily_hours=7)
        self.assertAlmostEqual(result_8h["premium"], result_7h["premium"])

    def test_zero_salary_returns_zero_premium(self):
        result = calculate_ph_work_premium(0)
        self.assertAlmostEqual(result["premium"], 0.0)

    def test_invalid_salary_returns_zero_premium(self):
        result = calculate_ph_work_premium("invalid")
        self.assertAlmostEqual(result["premium"], 0.0)


# ---------------------------------------------------------------------------
# calculate_ph_overtime()
# ---------------------------------------------------------------------------


class TestCalculatePHOvertime(FrappeTestCase):
    """Test overtime pay for hours beyond normal working hours on a Public Holiday."""

    def test_rm3000_employee_1_ot_hour_pay(self):
        """Acceptance criterion: RM3,000/26/8 x 3 per OT hour."""
        result = calculate_ph_overtime(3000, ot_hours=1, normal_daily_hours=8)
        # orp_hourly = 3000 / 26 / 8 = 14.4231...
        # ot_pay = 3 x 14.4231 = 43.269...
        expected_orp_hourly = 3000 / 26.0 / 8.0
        expected_ot_pay = 3.0 * expected_orp_hourly * 1
        self.assertAlmostEqual(result["ot_pay"], expected_ot_pay, places=4)

    def test_rm3000_employee_2_ot_hours_pay(self):
        result = calculate_ph_overtime(3000, ot_hours=2, normal_daily_hours=8)
        expected = 3.0 * (3000 / 26.0 / 8.0) * 2
        self.assertAlmostEqual(result["ot_pay"], expected, places=4)

    def test_orp_hourly_is_daily_divided_by_normal_hours(self):
        result = calculate_ph_overtime(3000, ot_hours=1, normal_daily_hours=8)
        self.assertAlmostEqual(result["orp_hourly"], 3000 / 26.0 / 8.0, places=4)

    def test_multiplier_is_3(self):
        result = calculate_ph_overtime(3000, ot_hours=1)
        self.assertAlmostEqual(result["multiplier"], 3.0)

    def test_ot_hours_stored_in_result(self):
        result = calculate_ph_overtime(3000, ot_hours=2.5)
        self.assertAlmostEqual(result["ot_hours"], 2.5)

    def test_ea_covered_true_at_4000(self):
        result = calculate_ph_overtime(4000, ot_hours=1)
        self.assertTrue(result["ea_covered"])

    def test_ea_covered_false_above_4000(self):
        result = calculate_ph_overtime(4001, ot_hours=1)
        self.assertFalse(result["ea_covered"])

    def test_no_warning_for_ea_covered(self):
        result = calculate_ph_overtime(3000, ot_hours=1)
        self.assertIsNone(result["warning"])

    def test_warning_above_threshold(self):
        result = calculate_ph_overtime(5000, ot_hours=1)
        self.assertIsNotNone(result["warning"])
        self.assertIn("Section 60A", result["warning"])

    def test_zero_ot_hours_returns_zero_pay(self):
        result = calculate_ph_overtime(3000, ot_hours=0)
        self.assertAlmostEqual(result["ot_pay"], 0.0)

    def test_none_ot_hours_returns_zero_pay(self):
        result = calculate_ph_overtime(3000, ot_hours=None)
        self.assertAlmostEqual(result["ot_pay"], 0.0)

    def test_result_has_required_keys(self):
        result = calculate_ph_overtime(3000, ot_hours=1)
        self.assertIn("ot_pay", result)
        self.assertIn("orp_hourly", result)
        self.assertIn("multiplier", result)
        self.assertIn("ot_hours", result)
        self.assertIn("ea_covered", result)
        self.assertIn("warning", result)

    def test_custom_normal_daily_hours_changes_orp_hourly(self):
        """7-hour day yields higher hourly ORP than 8-hour day."""
        result_8h = calculate_ph_overtime(3000, ot_hours=1, normal_daily_hours=8)
        result_7h = calculate_ph_overtime(3000, ot_hours=1, normal_daily_hours=7)
        self.assertGreater(result_7h["orp_hourly"], result_8h["orp_hourly"])

    def test_rm2000_employee_ot_pay(self):
        result = calculate_ph_overtime(2000, ot_hours=3, normal_daily_hours=8)
        expected = 3.0 * (2000 / 26.0 / 8.0) * 3
        self.assertAlmostEqual(result["ot_pay"], expected, places=4)


# ---------------------------------------------------------------------------
# add_ph_oil_credit()
# ---------------------------------------------------------------------------


class TestAddPHOILCredit(FrappeTestCase):
    """Test Off-In-Lieu credit function."""

    @patch("lhdn_payroll_integration.utils.employment_compliance.frappe")
    def test_adds_credit_to_zero_balance(self, mock_frappe):
        emp_mock = MagicMock()
        emp_mock.custom_ph_oil_balance = 0
        mock_frappe.get_doc.return_value = emp_mock

        result = add_ph_oil_credit("EMP-001", days=1.0)

        self.assertTrue(result["success"])
        self.assertAlmostEqual(result["days_added"], 1.0)
        self.assertAlmostEqual(result["new_balance"], 1.0)
        emp_mock.save.assert_called_once()

    @patch("lhdn_payroll_integration.utils.employment_compliance.frappe")
    def test_accumulates_balance(self, mock_frappe):
        emp_mock = MagicMock()
        emp_mock.custom_ph_oil_balance = 2.0
        mock_frappe.get_doc.return_value = emp_mock

        result = add_ph_oil_credit("EMP-001", days=1.0)

        self.assertAlmostEqual(result["new_balance"], 3.0)

    @patch("lhdn_payroll_integration.utils.employment_compliance.frappe")
    def test_fractional_days_credit(self, mock_frappe):
        emp_mock = MagicMock()
        emp_mock.custom_ph_oil_balance = 0
        mock_frappe.get_doc.return_value = emp_mock

        result = add_ph_oil_credit("EMP-001", days=0.5)

        self.assertAlmostEqual(result["new_balance"], 0.5)

    @patch("lhdn_payroll_integration.utils.employment_compliance.frappe")
    def test_returns_employee_name(self, mock_frappe):
        emp_mock = MagicMock()
        emp_mock.custom_ph_oil_balance = 0
        mock_frappe.get_doc.return_value = emp_mock

        result = add_ph_oil_credit("EMP-TEST-123")

        self.assertEqual(result["employee"], "EMP-TEST-123")

    @patch("lhdn_payroll_integration.utils.employment_compliance.frappe")
    def test_returns_error_on_exception(self, mock_frappe):
        mock_frappe.get_doc.side_effect = Exception("Employee not found")

        result = add_ph_oil_credit("EMP-NONEXISTENT")

        self.assertFalse(result["success"])
        self.assertIsNotNone(result["error"])
        self.assertIn("Employee not found", result["error"])


# ---------------------------------------------------------------------------
# flag_payroll_public_holiday_dates()
# ---------------------------------------------------------------------------


class TestFlagPayrollPublicHolidayDates(FrappeTestCase):
    """Test flagging of payroll dates that fall on public holidays."""

    def test_flags_date_matching_public_holiday(self):
        result = flag_payroll_public_holiday_dates(
            payroll_dates=["2025-01-01", "2025-01-02"],
            malaysia_public_holidays=["2025-01-01"],  # New Year's Day
        )
        self.assertIn("2025-01-01", result["flagged_dates"])
        self.assertEqual(result["count"], 1)

    def test_does_not_flag_non_holiday_date(self):
        result = flag_payroll_public_holiday_dates(
            payroll_dates=["2025-01-15"],
            malaysia_public_holidays=["2025-01-01"],
        )
        self.assertEqual(result["count"], 0)
        self.assertEqual(result["flagged_dates"], [])

    def test_multiple_ph_dates_flagged(self):
        result = flag_payroll_public_holiday_dates(
            payroll_dates=["2025-01-01", "2025-02-01", "2025-05-01"],
            malaysia_public_holidays=["2025-01-01", "2025-02-01", "2025-05-01"],
        )
        self.assertEqual(result["count"], 3)

    def test_empty_payroll_dates_returns_empty(self):
        result = flag_payroll_public_holiday_dates(
            payroll_dates=[],
            malaysia_public_holidays=["2025-01-01"],
        )
        self.assertEqual(result["count"], 0)

    def test_empty_public_holidays_returns_empty(self):
        result = flag_payroll_public_holiday_dates(
            payroll_dates=["2025-01-01"],
            malaysia_public_holidays=[],
        )
        self.assertEqual(result["count"], 0)

    def test_result_has_required_keys(self):
        result = flag_payroll_public_holiday_dates([], [])
        self.assertIn("flagged_dates", result)
        self.assertIn("count", result)

    def test_national_public_holidays_2025(self):
        """Spot-check 2025 Malaysian national public holidays."""
        malaysia_ph_2025 = [
            "2025-01-01",  # New Year's Day
            "2025-02-01",  # Federal Territory Day
            "2025-05-01",  # Labour Day
            "2025-08-31",  # National Day
            "2025-09-16",  # Malaysia Day
            "2025-12-25",  # Christmas
        ]
        payroll_dates = ["2025-05-01", "2025-05-02", "2025-08-31"]
        result = flag_payroll_public_holiday_dates(payroll_dates, malaysia_ph_2025)
        self.assertIn("2025-05-01", result["flagged_dates"])
        self.assertIn("2025-08-31", result["flagged_dates"])
        self.assertNotIn("2025-05-02", result["flagged_dates"])
        self.assertEqual(result["count"], 2)
