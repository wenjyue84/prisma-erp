"""Tests for US-119: Public Holiday Work Pay Calculator (Employment Act 1955 Section 60D).

Employment Act 1955 references:
  - Section 60D: Public holiday entitlements — 11 paid public holidays per year;
    additional 2x ORP when required to work (triple-pay total with base day pay)
  - Section 60A: Overtime on public holiday at 3x hourly rate
  - Section 60I: Ordinary Rate of Pay (ORP) = monthly_salary / 26 for monthly-rated employees
  - Post-2022 amendment: EA covers employees with monthly wages <= RM4,000

Key test scenario (from acceptance criteria):
  - Monthly RM3,000 employee works 8 hours on a PH:
    additional premium = RM3,000 / 26 * 2 = RM230.769...  (≈ RM230.77)
  - OT beyond 8 hours on PH: RM3,000 / 26 / 8 * 3 per OT hour = RM43.27/h
"""

from unittest.mock import MagicMock, patch

from frappe.tests.utils import FrappeTestCase

from lhdn_payroll_integration.utils.employment_compliance import (
    ORP_SALARY_THRESHOLD,
    PH_WORK_PREMIUM_MULTIPLIER,
    PH_OT_MULTIPLIER,
    NORMAL_DAILY_HOURS,
    MALAYSIA_FIXED_PUBLIC_HOLIDAYS,
    calculate_public_holiday_work_premium,
    calculate_public_holiday_ot_pay,
    check_ea_coverage_for_public_holiday,
    get_public_holiday_oil_balance,
    add_public_holiday_oil_credit,
    is_malaysia_public_holiday,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class TestPublicHolidayPayConstants(FrappeTestCase):
    """Verify US-119 constants are correct per Employment Act."""

    def test_premium_multiplier_is_2(self):
        """Additional PH work premium = 2x ORP daily (S.60D)."""
        self.assertEqual(PH_WORK_PREMIUM_MULTIPLIER, 2)

    def test_ot_multiplier_is_3(self):
        """OT on public holiday = 3x hourly rate (S.60A)."""
        self.assertEqual(PH_OT_MULTIPLIER, 3)

    def test_normal_daily_hours_is_8(self):
        """Standard working day default = 8 hours."""
        self.assertEqual(NORMAL_DAILY_HOURS, 8)

    def test_ea_salary_threshold_is_4000(self):
        """EA coverage ceiling = RM4,000/month (post-2022 amendment)."""
        self.assertEqual(ORP_SALARY_THRESHOLD, 4000.0)

    def test_fixed_public_holidays_is_frozenset(self):
        """MALAYSIA_FIXED_PUBLIC_HOLIDAYS is immutable (frozenset)."""
        self.assertIsInstance(MALAYSIA_FIXED_PUBLIC_HOLIDAYS, frozenset)

    def test_fixed_public_holidays_has_minimum_entries(self):
        """At least 5 fixed-date federal public holidays gazetted."""
        self.assertGreaterEqual(len(MALAYSIA_FIXED_PUBLIC_HOLIDAYS), 5)

    def test_merdeka_day_in_fixed_holidays(self):
        """31 Aug (Merdeka Day) must be in fixed public holidays."""
        self.assertIn((8, 31), MALAYSIA_FIXED_PUBLIC_HOLIDAYS)

    def test_malaysia_day_in_fixed_holidays(self):
        """16 Sept (Malaysia Day) must be in fixed public holidays."""
        self.assertIn((9, 16), MALAYSIA_FIXED_PUBLIC_HOLIDAYS)

    def test_workers_day_in_fixed_holidays(self):
        """1 May (Workers' Day) must be in fixed public holidays."""
        self.assertIn((5, 1), MALAYSIA_FIXED_PUBLIC_HOLIDAYS)

    def test_new_year_day_in_fixed_holidays(self):
        """1 Jan (New Year's Day) must be in fixed public holidays."""
        self.assertIn((1, 1), MALAYSIA_FIXED_PUBLIC_HOLIDAYS)


# ---------------------------------------------------------------------------
# calculate_public_holiday_work_premium()
# ---------------------------------------------------------------------------


class TestCalculatePublicHolidayWorkPremium(FrappeTestCase):
    """Test calculate_public_holiday_work_premium() — EA S.60D additional premium."""

    def test_acceptance_criteria_rm3000_employee(self):
        """AC: RM3,000/month → additional premium = RM3,000/26 * 2 = RM230.769..."""
        result = calculate_public_holiday_work_premium(3000)
        expected_premium = 3000 / 26 * 2
        self.assertAlmostEqual(result["premium"], expected_premium, places=4)

    def test_acceptance_criteria_premium_value(self):
        """AC: RM3,000 premium ≈ RM230.77."""
        result = calculate_public_holiday_work_premium(3000)
        self.assertAlmostEqual(result["premium"], 230.769, places=2)

    def test_orp_daily_is_monthly_divided_by_26(self):
        """ORP daily = monthly_salary / 26 per EA S.60I."""
        result = calculate_public_holiday_work_premium(2600)
        self.assertAlmostEqual(result["orp_daily"], 100.0, places=4)

    def test_premium_is_2x_orp_daily(self):
        """Premium = 2 × ORP daily."""
        result = calculate_public_holiday_work_premium(2600)
        self.assertAlmostEqual(result["premium"], 200.0, places=4)

    def test_multiplier_field_is_2(self):
        """Result multiplier field must equal PH_WORK_PREMIUM_MULTIPLIER (2)."""
        result = calculate_public_holiday_work_premium(3000)
        self.assertEqual(result["multiplier"], 2)

    def test_ea_covered_true_at_4000(self):
        """RM4,000 exactly — EA applies."""
        result = calculate_public_holiday_work_premium(4000)
        self.assertTrue(result["ea_covered"])

    def test_ea_covered_false_above_4000(self):
        """Above RM4,000 — EA does not apply."""
        result = calculate_public_holiday_work_premium(4001)
        self.assertFalse(result["ea_covered"])

    def test_ea_covered_true_below_4000(self):
        """Below RM4,000 — EA applies."""
        result = calculate_public_holiday_work_premium(3999)
        self.assertTrue(result["ea_covered"])

    def test_result_has_required_keys(self):
        """Result dict must have premium, orp_daily, multiplier, ea_covered."""
        result = calculate_public_holiday_work_premium(3000)
        self.assertIn("premium", result)
        self.assertIn("orp_daily", result)
        self.assertIn("multiplier", result)
        self.assertIn("ea_covered", result)

    def test_zero_salary_returns_zero_premium(self):
        """Zero salary → zero premium."""
        result = calculate_public_holiday_work_premium(0)
        self.assertAlmostEqual(result["premium"], 0.0)

    def test_high_salary_still_computes_premium(self):
        """High salary computes premium regardless of EA coverage."""
        result = calculate_public_holiday_work_premium(10000)
        expected = 10000 / 26 * 2
        self.assertAlmostEqual(result["premium"], expected, places=4)
        self.assertFalse(result["ea_covered"])


# ---------------------------------------------------------------------------
# calculate_public_holiday_ot_pay()
# ---------------------------------------------------------------------------


class TestCalculatePublicHolidayOTPay(FrappeTestCase):
    """Test calculate_public_holiday_ot_pay() — EA S.60A 3x OT on public holiday."""

    def test_acceptance_criteria_rm3000_hourly_ot_rate(self):
        """AC: RM3,000/month, 8h day → ORP hourly = RM3,000/26/8 = RM14.4231..."""
        result = calculate_public_holiday_ot_pay(3000, ot_hours=1, normal_daily_hours=8)
        expected_hourly = 3000 / 26 / 8
        self.assertAlmostEqual(result["orp_hourly"], expected_hourly, places=4)

    def test_acceptance_criteria_ot_pay_per_hour(self):
        """AC: OT pay per hour = RM3,000/26/8 * 3 ≈ RM43.27 per OT hour."""
        result = calculate_public_holiday_ot_pay(3000, ot_hours=1, normal_daily_hours=8)
        expected_per_hour = 3000 / 26 / 8 * 3
        self.assertAlmostEqual(result["ot_pay"], expected_per_hour, places=4)

    def test_two_ot_hours_doubles_pay(self):
        """2 OT hours = 2 × single-hour OT pay."""
        result_1h = calculate_public_holiday_ot_pay(3000, ot_hours=1)
        result_2h = calculate_public_holiday_ot_pay(3000, ot_hours=2)
        self.assertAlmostEqual(result_2h["ot_pay"], result_1h["ot_pay"] * 2, places=4)

    def test_ot_multiplier_is_3(self):
        """Result multiplier field must equal PH_OT_MULTIPLIER (3)."""
        result = calculate_public_holiday_ot_pay(3000, ot_hours=2)
        self.assertEqual(result["multiplier"], 3)

    def test_zero_ot_hours_gives_zero_pay(self):
        """0 OT hours → 0 OT pay."""
        result = calculate_public_holiday_ot_pay(3000, ot_hours=0)
        self.assertAlmostEqual(result["ot_pay"], 0.0)

    def test_none_ot_hours_gives_zero_pay(self):
        """None OT hours treated as 0."""
        result = calculate_public_holiday_ot_pay(3000, ot_hours=None)
        self.assertAlmostEqual(result["ot_pay"], 0.0)

    def test_ot_hours_stored_in_result(self):
        """OT hours passed in are returned in the result."""
        result = calculate_public_holiday_ot_pay(3000, ot_hours=3.5)
        self.assertAlmostEqual(result["ot_hours"], 3.5)

    def test_ea_covered_below_threshold(self):
        """Employee below RM4,000 is EA-covered."""
        result = calculate_public_holiday_ot_pay(3000, ot_hours=2)
        self.assertTrue(result["ea_covered"])

    def test_ea_covered_false_above_threshold(self):
        """Employee above RM4,000 is not EA-covered."""
        result = calculate_public_holiday_ot_pay(5000, ot_hours=2)
        self.assertFalse(result["ea_covered"])

    def test_custom_normal_daily_hours(self):
        """Custom normal_daily_hours affects hourly ORP calculation."""
        # 6-hour day instead of 8
        result_8h = calculate_public_holiday_ot_pay(3000, ot_hours=1, normal_daily_hours=8)
        result_6h = calculate_public_holiday_ot_pay(3000, ot_hours=1, normal_daily_hours=6)
        # Shorter day → higher hourly ORP
        self.assertGreater(result_6h["orp_hourly"], result_8h["orp_hourly"])

    def test_result_has_required_keys(self):
        """Result dict must have ot_pay, orp_hourly, multiplier, ot_hours, ea_covered."""
        result = calculate_public_holiday_ot_pay(3000, ot_hours=2)
        for key in ("ot_pay", "orp_hourly", "multiplier", "ot_hours", "ea_covered"):
            self.assertIn(key, result)

    def test_orp_hourly_formula(self):
        """ORP hourly = monthly / 26 / daily_hours."""
        result = calculate_public_holiday_ot_pay(2600, ot_hours=1, normal_daily_hours=8)
        # ORP daily = 2600/26 = 100; hourly = 100/8 = 12.5
        self.assertAlmostEqual(result["orp_hourly"], 12.5, places=4)

    def test_ot_pay_formula_complete(self):
        """OT pay = orp_hourly * 3 * ot_hours."""
        result = calculate_public_holiday_ot_pay(2600, ot_hours=2, normal_daily_hours=8)
        # ORP daily = 100, hourly = 12.5, OT = 12.5 * 3 * 2 = 75
        self.assertAlmostEqual(result["ot_pay"], 75.0, places=4)


# ---------------------------------------------------------------------------
# check_ea_coverage_for_public_holiday()
# ---------------------------------------------------------------------------


class TestCheckEACoverageForPublicHoliday(FrappeTestCase):
    """Test check_ea_coverage_for_public_holiday() — EA coverage validation."""

    def test_salary_below_4000_is_covered(self):
        """Employees earning < RM4,000 are EA-covered."""
        result = check_ea_coverage_for_public_holiday(3000)
        self.assertTrue(result["covered"])
        self.assertIsNone(result["reminder"])

    def test_salary_exactly_4000_is_covered(self):
        """Employees earning exactly RM4,000 are EA-covered."""
        result = check_ea_coverage_for_public_holiday(4000)
        self.assertTrue(result["covered"])
        self.assertIsNone(result["reminder"])

    def test_salary_above_4000_not_covered(self):
        """Employees earning > RM4,000 are NOT EA-covered."""
        result = check_ea_coverage_for_public_holiday(4001)
        self.assertFalse(result["covered"])

    def test_above_threshold_has_reminder_message(self):
        """Employees above threshold receive a reminder to check employment contract."""
        result = check_ea_coverage_for_public_holiday(5000)
        self.assertIsNotNone(result["reminder"])
        self.assertIn("employment contract", result["reminder"].lower())

    def test_above_threshold_reminder_mentions_salary(self):
        """Reminder message includes the actual salary."""
        result = check_ea_coverage_for_public_holiday(5000)
        self.assertIn("5000", result["reminder"])

    def test_result_contains_salary_field(self):
        """Result must include salary field."""
        result = check_ea_coverage_for_public_holiday(3000)
        self.assertAlmostEqual(result["salary"], 3000.0)

    def test_result_has_required_keys(self):
        """Result must have covered, reminder, salary keys."""
        result = check_ea_coverage_for_public_holiday(3000)
        self.assertIn("covered", result)
        self.assertIn("reminder", result)
        self.assertIn("salary", result)

    def test_zero_salary_is_covered(self):
        """Zero salary is considered EA-covered."""
        result = check_ea_coverage_for_public_holiday(0)
        self.assertTrue(result["covered"])

    def test_just_below_threshold_is_covered(self):
        """RM3,999 is EA-covered."""
        result = check_ea_coverage_for_public_holiday(3999)
        self.assertTrue(result["covered"])

    def test_just_above_threshold_not_covered(self):
        """RM4,001 is NOT EA-covered."""
        result = check_ea_coverage_for_public_holiday(4001)
        self.assertFalse(result["covered"])


# ---------------------------------------------------------------------------
# get_public_holiday_oil_balance() and add_public_holiday_oil_credit()
# ---------------------------------------------------------------------------


class TestPublicHolidayOILBalance(FrappeTestCase):
    """Test Off-In-Lieu balance tracking for public holiday work."""

    @patch("lhdn_payroll_integration.utils.employment_compliance.frappe")
    def test_get_oil_balance_returns_field_value(self, mock_frappe):
        """get_public_holiday_oil_balance() reads custom_ph_oil_balance from Employee."""
        emp = MagicMock()
        emp.get = lambda key, default=None: {"custom_ph_oil_balance": 3.0}.get(key, default)
        mock_frappe.get_doc.return_value = emp

        balance = get_public_holiday_oil_balance("EMP-001")
        self.assertAlmostEqual(balance, 3.0)

    @patch("lhdn_payroll_integration.utils.employment_compliance.frappe")
    def test_get_oil_balance_returns_zero_when_field_none(self, mock_frappe):
        """get_public_holiday_oil_balance() returns 0.0 when field is None."""
        emp = MagicMock()
        emp.get = lambda key, default=None: {"custom_ph_oil_balance": None}.get(key, default)
        mock_frappe.get_doc.return_value = emp

        balance = get_public_holiday_oil_balance("EMP-001")
        self.assertAlmostEqual(balance, 0.0)

    @patch("lhdn_payroll_integration.utils.employment_compliance.frappe")
    def test_get_oil_balance_returns_zero_on_exception(self, mock_frappe):
        """get_public_holiday_oil_balance() returns 0.0 if get_doc raises."""
        mock_frappe.get_doc.side_effect = Exception("Not found")

        balance = get_public_holiday_oil_balance("EMP-NONEXISTENT")
        self.assertAlmostEqual(balance, 0.0)

    @patch("lhdn_payroll_integration.utils.employment_compliance.frappe")
    def test_add_oil_credit_increments_balance(self, mock_frappe):
        """add_public_holiday_oil_credit() increments existing OIL balance."""
        emp = MagicMock()
        emp.get = lambda key, default=None: {"custom_ph_oil_balance": 2.0}.get(key, default)
        mock_frappe.get_doc.return_value = emp

        result = add_public_holiday_oil_credit("EMP-001", days=1)
        self.assertTrue(result["success"])
        self.assertAlmostEqual(result["new_balance"], 3.0)
        self.assertAlmostEqual(result["days_credited"], 1.0)

    @patch("lhdn_payroll_integration.utils.employment_compliance.frappe")
    def test_add_oil_credit_from_zero_balance(self, mock_frappe):
        """add_public_holiday_oil_credit() works from zero balance."""
        emp = MagicMock()
        emp.get = lambda key, default=None: {"custom_ph_oil_balance": 0.0}.get(key, default)
        mock_frappe.get_doc.return_value = emp

        result = add_public_holiday_oil_credit("EMP-001", days=1)
        self.assertTrue(result["success"])
        self.assertAlmostEqual(result["new_balance"], 1.0)

    @patch("lhdn_payroll_integration.utils.employment_compliance.frappe")
    def test_add_oil_credit_custom_days(self, mock_frappe):
        """add_public_holiday_oil_credit() accepts fractional/custom days."""
        emp = MagicMock()
        emp.get = lambda key, default=None: {"custom_ph_oil_balance": 1.5}.get(key, default)
        mock_frappe.get_doc.return_value = emp

        result = add_public_holiday_oil_credit("EMP-001", days=0.5)
        self.assertTrue(result["success"])
        self.assertAlmostEqual(result["new_balance"], 2.0)

    @patch("lhdn_payroll_integration.utils.employment_compliance.frappe")
    def test_add_oil_credit_saves_employee(self, mock_frappe):
        """add_public_holiday_oil_credit() calls emp.save()."""
        emp = MagicMock()
        emp.get = lambda key, default=None: {"custom_ph_oil_balance": 0.0}.get(key, default)
        mock_frappe.get_doc.return_value = emp

        add_public_holiday_oil_credit("EMP-001", days=1)
        emp.save.assert_called_once()

    @patch("lhdn_payroll_integration.utils.employment_compliance.frappe")
    def test_add_oil_credit_failure_returns_false(self, mock_frappe):
        """add_public_holiday_oil_credit() returns success=False on exception."""
        mock_frappe.get_doc.side_effect = Exception("DB error")

        result = add_public_holiday_oil_credit("EMP-NONEXISTENT", days=1)
        self.assertFalse(result["success"])

    def test_add_oil_credit_result_has_required_keys(self):
        """Result from add_public_holiday_oil_credit() has success, new_balance, days_credited."""
        with patch("lhdn_payroll_integration.utils.employment_compliance.frappe") as mf:
            emp = MagicMock()
            emp.get = lambda key, default=None: 0.0 if key == "custom_ph_oil_balance" else None
            mf.get_doc.return_value = emp
            result = add_public_holiday_oil_credit("EMP-001", days=1)

        self.assertIn("success", result)
        self.assertIn("new_balance", result)
        self.assertIn("days_credited", result)


# ---------------------------------------------------------------------------
# is_malaysia_public_holiday()
# ---------------------------------------------------------------------------


class TestIsMalaysiaPublicHoliday(FrappeTestCase):
    """Test is_malaysia_public_holiday() — fixed-date federal PH calendar."""

    def test_merdeka_day_is_public_holiday(self):
        """31 Aug is Merdeka Day — gazetted public holiday."""
        result = is_malaysia_public_holiday("2025-08-31")
        self.assertTrue(result["is_public_holiday"])

    def test_malaysia_day_is_public_holiday(self):
        """16 Sep is Malaysia Day — gazetted public holiday."""
        result = is_malaysia_public_holiday("2025-09-16")
        self.assertTrue(result["is_public_holiday"])

    def test_workers_day_is_public_holiday(self):
        """1 May is Workers' Day — gazetted public holiday."""
        result = is_malaysia_public_holiday("2025-05-01")
        self.assertTrue(result["is_public_holiday"])

    def test_new_year_is_public_holiday(self):
        """1 Jan is New Year's Day — gazetted public holiday."""
        result = is_malaysia_public_holiday("2025-01-01")
        self.assertTrue(result["is_public_holiday"])

    def test_christmas_is_public_holiday(self):
        """25 Dec is Christmas Day — gazetted public holiday."""
        result = is_malaysia_public_holiday("2025-12-25")
        self.assertTrue(result["is_public_holiday"])

    def test_random_workday_is_not_public_holiday(self):
        """A normal working day is not a public holiday."""
        result = is_malaysia_public_holiday("2025-03-15")
        self.assertFalse(result["is_public_holiday"])

    def test_result_has_is_public_holiday_key(self):
        """Result dict must have is_public_holiday key."""
        result = is_malaysia_public_holiday("2025-03-15")
        self.assertIn("is_public_holiday", result)

    def test_result_has_date_key(self):
        """Result dict must have date key."""
        result = is_malaysia_public_holiday("2025-08-31")
        self.assertIn("date", result)

    def test_result_has_note_key(self):
        """Result dict must have note key explaining partial coverage."""
        result = is_malaysia_public_holiday("2025-08-31")
        self.assertIn("note", result)
        self.assertIn("Lunar", result["note"])

    def test_invalid_date_returns_false(self):
        """Invalid date string returns is_public_holiday=False."""
        result = is_malaysia_public_holiday("not-a-date")
        self.assertFalse(result["is_public_holiday"])

    def test_same_date_different_years(self):
        """8 May 2025 is not a fixed public holiday (varies by year — Wesak)."""
        result = is_malaysia_public_holiday("2026-08-31")
        self.assertTrue(result["is_public_holiday"])  # Merdeka Day is always 31 Aug

    def test_merdeka_day_works_across_years(self):
        """31 Aug is a public holiday regardless of year."""
        for year in [2024, 2025, 2026]:
            result = is_malaysia_public_holiday(f"{year}-08-31")
            self.assertTrue(result["is_public_holiday"], f"Expected 31 Aug {year} to be a PH")


# ---------------------------------------------------------------------------
# Integration: Full acceptance-criteria scenario
# ---------------------------------------------------------------------------


class TestPublicHolidayPayIntegration(FrappeTestCase):
    """End-to-end test for the acceptance-criteria scenarios."""

    def test_rm3000_employee_full_day_ph_premium(self):
        """AC: RM3,000 employee works full day on PH → premium = RM3,000/26*2."""
        monthly = 3000.0
        result = calculate_public_holiday_work_premium(monthly)

        expected_orp = monthly / 26
        expected_premium = expected_orp * 2

        self.assertAlmostEqual(result["orp_daily"], expected_orp, places=4)
        self.assertAlmostEqual(result["premium"], expected_premium, places=4)
        self.assertTrue(result["ea_covered"])

    def test_rm3000_employee_ot_hours_on_ph(self):
        """AC: RM3,000 employee, 8h normal day, OT hours on PH → 3x hourly rate."""
        monthly = 3000.0
        ot_hours = 2
        result = calculate_public_holiday_ot_pay(monthly, ot_hours=ot_hours, normal_daily_hours=8)

        expected_orp_hourly = monthly / 26 / 8
        expected_ot_pay = expected_orp_hourly * 3 * ot_hours

        self.assertAlmostEqual(result["orp_hourly"], expected_orp_hourly, places=4)
        self.assertAlmostEqual(result["ot_pay"], expected_ot_pay, places=4)
        self.assertTrue(result["ea_covered"])

    def test_above_threshold_employee_ph_reminder(self):
        """AC: Employees above RM4,000 get a reminder to check employment contract."""
        result_coverage = check_ea_coverage_for_public_holiday(5000)
        self.assertFalse(result_coverage["covered"])
        self.assertIsNotNone(result_coverage["reminder"])
        # Premium still computed but EA does not mandate the rate
        result_premium = calculate_public_holiday_work_premium(5000)
        self.assertFalse(result_premium["ea_covered"])

    def test_merdeka_day_flagged_as_public_holiday(self):
        """AC: System flags payroll runs on Malaysia's gazetted public holidays."""
        ph_result = is_malaysia_public_holiday("2025-08-31")
        self.assertTrue(ph_result["is_public_holiday"])

    def test_premium_plus_ot_pay_total(self):
        """Combined: premium + OT pay for RM3,000 employee, 8h day + 2h OT on PH."""
        monthly = 3000.0
        premium_result = calculate_public_holiday_work_premium(monthly)
        ot_result = calculate_public_holiday_ot_pay(monthly, ot_hours=2, normal_daily_hours=8)

        total = premium_result["premium"] + ot_result["ot_pay"]

        # Premium = 3000/26*2 = 230.769...
        # OT = 3000/26/8*3*2 = 86.538...
        # Total ≈ 317.307...
        expected_total = (3000 / 26 * 2) + (3000 / 26 / 8 * 3 * 2)
        self.assertAlmostEqual(total, expected_total, places=4)
