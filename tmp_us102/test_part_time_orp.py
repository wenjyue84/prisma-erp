"""Tests for US-102: Part-Time Employee ORP Proration and Overtime Eligibility
under EA Third Schedule.

Employment Act 1955, Third Schedule (Part-Time Employees):
  - Part-time definition: works fewer than 70% of normal full-time hours
  - ORP = agreed_monthly_wage / contracted_hours_per_month
    where contracted_hours_per_month = contracted_hours_per_week * 52 / 12
  - EA coverage: salary <= RM4,000/month (Employment Amendment Act 2022)
  - OT cap: 104 hours/month for EA-covered part-time employees
  - OT multipliers: 1.5x Normal, 2.0x Public Holiday
"""

from frappe.tests.utils import FrappeTestCase

from lhdn_payroll_integration.utils.employment_compliance import (
    PART_TIME_OT_HOURS_CAP,
    PART_TIME_OT_MULTIPLIERS,
    ORP_SALARY_THRESHOLD,
    calculate_part_time_orp,
    check_part_time_ea_coverage,
    check_part_time_ot_hours_cap,
    check_part_time_ot_rate,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class TestPartTimeORPConstants(FrappeTestCase):
    """Verify part-time ORP constants per EA Third Schedule."""

    def test_ot_hours_cap_is_104(self):
        self.assertEqual(PART_TIME_OT_HOURS_CAP, 104)

    def test_normal_multiplier_is_1_5(self):
        self.assertAlmostEqual(PART_TIME_OT_MULTIPLIERS["Normal"], 1.5)

    def test_public_holiday_multiplier_is_2_0(self):
        self.assertAlmostEqual(PART_TIME_OT_MULTIPLIERS["Public Holiday"], 2.0)

    def test_both_day_types_present(self):
        self.assertIn("Normal", PART_TIME_OT_MULTIPLIERS)
        self.assertIn("Public Holiday", PART_TIME_OT_MULTIPLIERS)

    def test_ea_salary_threshold_is_4000(self):
        self.assertEqual(ORP_SALARY_THRESHOLD, 4000.0)


# ---------------------------------------------------------------------------
# calculate_part_time_orp()
# ---------------------------------------------------------------------------


class TestCalculatePartTimeORP(FrappeTestCase):
    """Test calculate_part_time_orp() — EA Third Schedule Reg. 5(3)."""

    def test_contracted_hours_per_month_formula(self):
        # 20 hrs/week * 52 / 12 = 86.6667
        result = calculate_part_time_orp(2000, 20)
        expected_hours = 20 * 52 / 12
        self.assertAlmostEqual(result["contracted_hours_per_month"], expected_hours, places=4)

    def test_hourly_orp_calculation(self):
        # wage = 2000, hours = 20*52/12 = 86.667
        result = calculate_part_time_orp(2000, 20)
        expected = 2000 / (20 * 52 / 12)
        self.assertAlmostEqual(result["hourly"], expected, places=4)

    def test_hourly_orp_standard_example(self):
        # 3000/month, 30 hrs/week → monthly = 30*52/12 = 130h → ORP = 3000/130
        result = calculate_part_time_orp(3000, 30)
        expected = 3000 / (30 * 52 / 12)
        self.assertAlmostEqual(result["hourly"], expected, places=4)

    def test_result_has_hourly_key(self):
        result = calculate_part_time_orp(2000, 20)
        self.assertIn("hourly", result)

    def test_result_has_contracted_hours_per_month_key(self):
        result = calculate_part_time_orp(2000, 20)
        self.assertIn("contracted_hours_per_month", result)

    def test_zero_hours_per_week_returns_none(self):
        result = calculate_part_time_orp(2000, 0)
        self.assertIsNone(result["hourly"])
        self.assertIsNone(result["contracted_hours_per_month"])

    def test_negative_hours_returns_none(self):
        result = calculate_part_time_orp(2000, -5)
        self.assertIsNone(result["hourly"])

    def test_zero_wage_gives_zero_orp(self):
        result = calculate_part_time_orp(0, 20)
        self.assertAlmostEqual(result["hourly"], 0.0)

    def test_high_salary_example(self):
        # RM4000/month, 28 hrs/week
        result = calculate_part_time_orp(4000, 28)
        expected = 4000 / (28 * 52 / 12)
        self.assertAlmostEqual(result["hourly"], expected, places=4)

    def test_fractional_hours(self):
        # 22.5 hrs/week
        result = calculate_part_time_orp(2500, 22.5)
        expected = 2500 / (22.5 * 52 / 12)
        self.assertAlmostEqual(result["hourly"], expected, places=4)


# ---------------------------------------------------------------------------
# check_part_time_ea_coverage()
# ---------------------------------------------------------------------------


class TestCheckPartTimeEACoverage(FrappeTestCase):
    """Test check_part_time_ea_coverage() for EA coverage threshold."""

    def test_salary_below_4000_is_covered(self):
        self.assertTrue(check_part_time_ea_coverage(2000))

    def test_salary_at_4000_is_covered(self):
        self.assertTrue(check_part_time_ea_coverage(4000))

    def test_salary_above_4000_not_covered(self):
        self.assertFalse(check_part_time_ea_coverage(4001))

    def test_salary_zero_is_covered(self):
        self.assertTrue(check_part_time_ea_coverage(0))

    def test_salary_3999_is_covered(self):
        self.assertTrue(check_part_time_ea_coverage(3999.99))

    def test_salary_4000_01_not_covered(self):
        self.assertFalse(check_part_time_ea_coverage(4000.01))

    def test_returns_bool(self):
        result = check_part_time_ea_coverage(3000)
        self.assertIsInstance(result, bool)


# ---------------------------------------------------------------------------
# check_part_time_ot_hours_cap()
# ---------------------------------------------------------------------------


class TestCheckPartTimeOTHoursCap(FrappeTestCase):
    """Test check_part_time_ot_hours_cap() — 104 hour/month limit."""

    def test_within_cap_is_compliant(self):
        result = check_part_time_ot_hours_cap(50)
        self.assertTrue(result["compliant"])
        self.assertIsNone(result["warning"])

    def test_exactly_at_cap_is_compliant(self):
        result = check_part_time_ot_hours_cap(104)
        self.assertTrue(result["compliant"])

    def test_above_cap_triggers_warning(self):
        result = check_part_time_ot_hours_cap(105)
        self.assertFalse(result["compliant"])
        self.assertIsNotNone(result["warning"])

    def test_warning_contains_104(self):
        result = check_part_time_ot_hours_cap(110)
        self.assertIn("104", result["warning"])

    def test_cap_value_in_result(self):
        result = check_part_time_ot_hours_cap(50)
        self.assertEqual(result["cap"], 104)

    def test_zero_hours_is_compliant(self):
        result = check_part_time_ot_hours_cap(0)
        self.assertTrue(result["compliant"])

    def test_just_above_cap(self):
        result = check_part_time_ot_hours_cap(104.1)
        self.assertFalse(result["compliant"])

    def test_result_has_compliant_key(self):
        result = check_part_time_ot_hours_cap(50)
        self.assertIn("compliant", result)

    def test_result_has_warning_key(self):
        result = check_part_time_ot_hours_cap(50)
        self.assertIn("warning", result)


# ---------------------------------------------------------------------------
# check_part_time_ot_rate()
# ---------------------------------------------------------------------------


class TestCheckPartTimeOTRate(FrappeTestCase):
    """Test check_part_time_ot_rate() — OT pay validation for part-time."""

    # --- Normal day (1.5x) ---

    def test_normal_day_ot_compliant(self):
        # ORP = 2000 / (20*52/12) = 2000/86.667 ≈ 23.077/h
        # 1.5x, 2h → min ≈ 69.23; pay 80 → OK
        result = check_part_time_ot_rate(2000, 20, 80.0, 2, "Normal")
        self.assertTrue(result["compliant"])
        self.assertIsNone(result["warning"])

    def test_normal_day_ot_underpaid_triggers_warning(self):
        # ORP ≈ 23.077/h, 1.5x, 2h → min ≈ 69.23; pay 10 → underpaid
        result = check_part_time_ot_rate(2000, 20, 10.0, 2, "Normal")
        self.assertFalse(result["compliant"])
        self.assertIsNotNone(result["warning"])

    def test_normal_day_multiplier_in_result(self):
        result = check_part_time_ot_rate(2000, 20, 80.0, 2, "Normal")
        self.assertAlmostEqual(result["multiplier"], 1.5)

    # --- Public Holiday (2.0x) ---

    def test_public_holiday_ot_compliant(self):
        # ORP ≈ 23.077/h, 2.0x, 2h → min ≈ 92.31; pay 100 → OK
        result = check_part_time_ot_rate(2000, 20, 100.0, 2, "Public Holiday")
        self.assertTrue(result["compliant"])

    def test_public_holiday_ot_underpaid_triggers_warning(self):
        # min ≈ 92.31; pay 20 → underpaid
        result = check_part_time_ot_rate(2000, 20, 20.0, 2, "Public Holiday")
        self.assertFalse(result["compliant"])
        self.assertIn("2.0", result["warning"])

    def test_public_holiday_multiplier_in_result(self):
        result = check_part_time_ot_rate(2000, 20, 100.0, 2, "Public Holiday")
        self.assertAlmostEqual(result["multiplier"], 2.0)

    # --- EA coverage threshold ---

    def test_salary_above_4000_not_checked(self):
        # EA does not apply above RM4,000/month
        result = check_part_time_ot_rate(4001, 20, 1.0, 2, "Normal")
        self.assertTrue(result["compliant"])
        self.assertIsNone(result["warning"])

    def test_salary_exactly_4000_is_checked(self):
        # ORP = 4000/(20*52/12) ≈ 46.154/h, 1.5x, 2h → min ≈ 138.46; pay 1 → underpaid
        result = check_part_time_ot_rate(4000, 20, 1.0, 2, "Normal")
        self.assertFalse(result["compliant"])

    def test_salary_just_below_threshold_is_checked(self):
        result = check_part_time_ot_rate(3999, 20, 1.0, 2, "Normal")
        self.assertFalse(result["compliant"])

    # --- Edge cases ---

    def test_zero_ot_hours_is_compliant(self):
        result = check_part_time_ot_rate(2000, 20, 0.0, 0, "Normal")
        self.assertTrue(result["compliant"])

    def test_result_contains_minimum_amount(self):
        result = check_part_time_ot_rate(2000, 20, 80.0, 2, "Normal")
        expected_orp = 2000 / (20 * 52 / 12)
        expected_min = expected_orp * 2 * 1.5
        self.assertAlmostEqual(result["minimum_amount"], expected_min, places=4)

    def test_result_contains_orp_hourly(self):
        result = check_part_time_ot_rate(2000, 20, 80.0, 2, "Normal")
        expected = 2000 / (20 * 52 / 12)
        self.assertAlmostEqual(result["orp_hourly"], expected, places=4)

    def test_warning_contains_part_time_reference(self):
        result = check_part_time_ot_rate(2000, 20, 1.0, 2, "Normal")
        self.assertIn("Part-time", result["warning"])

    def test_zero_contracted_hours_returns_compliant(self):
        # Cannot compute ORP without contracted hours — skip check
        result = check_part_time_ot_rate(2000, 0, 80.0, 2, "Normal")
        self.assertTrue(result["compliant"])

    def test_result_has_compliant_key(self):
        result = check_part_time_ot_rate(2000, 20, 80.0, 2, "Normal")
        self.assertIn("compliant", result)

    def test_result_has_warning_key(self):
        result = check_part_time_ot_rate(2000, 20, 80.0, 2, "Normal")
        self.assertIn("warning", result)

    def test_result_has_multiplier_key(self):
        result = check_part_time_ot_rate(2000, 20, 80.0, 2, "Normal")
        self.assertIn("multiplier", result)

    def test_result_has_orp_hourly_key(self):
        result = check_part_time_ot_rate(2000, 20, 80.0, 2, "Normal")
        self.assertIn("orp_hourly", result)

    def test_result_has_minimum_amount_key(self):
        result = check_part_time_ot_rate(2000, 20, 80.0, 2, "Normal")
        self.assertIn("minimum_amount", result)

    def test_high_contracted_hours_example(self):
        # 28 hrs/week (70% of 40h FT), wage=3500
        result = check_part_time_ot_rate(3500, 28, 1.0, 2, "Normal")
        # ORP = 3500 / (28*52/12) ≈ 3500/121.33 ≈ 28.85/h
        # min = 28.85 * 2 * 1.5 = 86.54; pay 1 → underpaid
        self.assertFalse(result["compliant"])

    def test_orp_values_consistent_with_calculate_part_time_orp(self):
        orp_result = calculate_part_time_orp(2000, 20)
        ot_result = check_part_time_ot_rate(2000, 20, 80.0, 2, "Normal")
        self.assertAlmostEqual(ot_result["orp_hourly"], orp_result["hourly"], places=4)
