"""Tests for US-184: Enforce Part-Time Employee Minimum Hourly Rate Against
RM1,700 Monthly Wage Floor Proration.

Minimum Wages Order 2022 (P.U.(A) 268/2022): RM1,700 ÷ 208 hours = RM8.17/hour minimum.
"""

from frappe.tests.utils import FrappeTestCase

from lhdn_payroll_integration.services.part_time_min_hourly_service import (
    EXEMPT_CATEGORIES,
    PART_TIME_HOURS_PER_DAY,
    PART_TIME_WORKING_DAYS_PER_MONTH,
    PART_TIME_WORKING_HOURS_PER_MONTH,
    compute_minimum_hourly_rate,
    generate_part_time_compliance_report,
    validate_part_time_hourly_rate,
)
from lhdn_payroll_integration.utils.employment_compliance import (
    MINIMUM_WAGE_MONTHLY,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class TestPartTimeMinHourlyConstants(FrappeTestCase):
    """Verify statutory constants for part-time hourly minimum rate calculation."""

    def test_working_days_per_month_is_26(self):
        self.assertEqual(PART_TIME_WORKING_DAYS_PER_MONTH, 26)

    def test_hours_per_day_is_8(self):
        self.assertEqual(PART_TIME_HOURS_PER_DAY, 8)

    def test_working_hours_per_month_is_208(self):
        self.assertEqual(PART_TIME_WORKING_HOURS_PER_MONTH, 208)

    def test_exempt_categories_contains_apprentice(self):
        self.assertIn("apprentice", EXEMPT_CATEGORIES)

    def test_exempt_categories_contains_disabled_worker(self):
        self.assertIn("disabled_worker", EXEMPT_CATEGORIES)

    def test_exempt_categories_contains_trainee(self):
        self.assertIn("trainee", EXEMPT_CATEGORIES)

    def test_minimum_wage_monthly_is_1700(self):
        # Imported from employment_compliance — ensure it's still RM1,700
        self.assertEqual(MINIMUM_WAGE_MONTHLY, 1700.0)


# ---------------------------------------------------------------------------
# compute_minimum_hourly_rate()
# ---------------------------------------------------------------------------


class TestComputeMinimumHourlyRate(FrappeTestCase):
    """Test compute_minimum_hourly_rate() — derives hourly floor from monthly wage."""

    def test_default_minimum_hourly_is_8_17(self):
        result = compute_minimum_hourly_rate()
        self.assertAlmostEqual(result["minimum_hourly"], 8.17, places=2)

    def test_default_uses_1700_monthly(self):
        result = compute_minimum_hourly_rate()
        self.assertEqual(result["monthly_minimum"], 1700.0)

    def test_default_working_hours_is_208(self):
        result = compute_minimum_hourly_rate()
        self.assertEqual(result["working_hours_per_month"], 208)

    def test_custom_monthly_minimum_overrides_default(self):
        result = compute_minimum_hourly_rate(monthly_minimum=2000.0)
        expected = round(2000.0 / 208, 2)
        self.assertAlmostEqual(result["minimum_hourly"], expected, places=2)

    def test_custom_monthly_minimum_stored_in_result(self):
        result = compute_minimum_hourly_rate(monthly_minimum=2500.0)
        self.assertEqual(result["monthly_minimum"], 2500.0)

    def test_result_has_minimum_hourly_key(self):
        result = compute_minimum_hourly_rate()
        self.assertIn("minimum_hourly", result)

    def test_result_has_monthly_minimum_key(self):
        result = compute_minimum_hourly_rate()
        self.assertIn("monthly_minimum", result)

    def test_result_has_working_hours_per_month_key(self):
        result = compute_minimum_hourly_rate()
        self.assertIn("working_hours_per_month", result)

    def test_formula_is_monthly_divided_by_208(self):
        # 1700 / 208 = 8.173...  rounded to 8.17
        result = compute_minimum_hourly_rate(monthly_minimum=1700.0)
        self.assertAlmostEqual(result["minimum_hourly"], 1700.0 / 208, places=2)

    def test_higher_future_minimum_wage_auto_adjusts(self):
        # Simulate future RM1,900 minimum wage
        result = compute_minimum_hourly_rate(monthly_minimum=1900.0)
        self.assertGreater(result["minimum_hourly"], 8.17)


# ---------------------------------------------------------------------------
# validate_part_time_hourly_rate()
# ---------------------------------------------------------------------------


class TestValidatePartTimeHourlyRate(FrappeTestCase):
    """Test validate_part_time_hourly_rate() — per-employee compliance gate."""

    # --- Compliant cases ---

    def test_rate_at_minimum_is_compliant(self):
        result = validate_part_time_hourly_rate(8.17)
        self.assertTrue(result["compliant"])
        self.assertIsNone(result["warning"])

    def test_rate_above_minimum_is_compliant(self):
        result = validate_part_time_hourly_rate(10.00)
        self.assertTrue(result["compliant"])
        self.assertFalse(result["blocked"])

    def test_high_rate_is_compliant(self):
        result = validate_part_time_hourly_rate(25.00)
        self.assertTrue(result["compliant"])

    # --- Non-compliant cases ---

    def test_rate_below_minimum_is_non_compliant(self):
        result = validate_part_time_hourly_rate(8.00)
        self.assertFalse(result["compliant"])

    def test_rate_below_minimum_raises_warning(self):
        result = validate_part_time_hourly_rate(7.50)
        self.assertIsNotNone(result["warning"])

    def test_warning_mentions_actual_rate(self):
        result = validate_part_time_hourly_rate(7.50)
        self.assertIn("7.50", result["warning"])

    def test_warning_mentions_minimum_rate(self):
        result = validate_part_time_hourly_rate(7.50)
        self.assertIn("8.17", result["warning"])

    def test_non_compliant_is_blocked(self):
        result = validate_part_time_hourly_rate(5.00)
        self.assertTrue(result["blocked"])

    def test_shortfall_is_computed(self):
        result = validate_part_time_hourly_rate(8.00)
        self.assertIsNotNone(result["shortfall"])
        self.assertGreater(result["shortfall"], 0)

    def test_shortfall_value_correct(self):
        result = validate_part_time_hourly_rate(8.00)
        # 8.17 - 8.00 = 0.17
        self.assertAlmostEqual(result["shortfall"], 0.17, places=2)

    def test_compliant_shortfall_is_none(self):
        result = validate_part_time_hourly_rate(9.00)
        self.assertIsNone(result["shortfall"])

    # --- Exemption cases ---

    def test_apprentice_exemption_suppresses_block(self):
        result = validate_part_time_hourly_rate(5.00, exemption_category="apprentice")
        self.assertFalse(result["blocked"])

    def test_apprentice_exemption_marks_exempt(self):
        result = validate_part_time_hourly_rate(5.00, exemption_category="apprentice")
        self.assertTrue(result["exempt"])

    def test_disabled_worker_exemption_suppresses_block(self):
        result = validate_part_time_hourly_rate(6.00, exemption_category="disabled_worker")
        self.assertFalse(result["blocked"])

    def test_trainee_exemption_suppresses_block(self):
        result = validate_part_time_hourly_rate(6.50, exemption_category="trainee")
        self.assertFalse(result["blocked"])

    def test_unknown_exemption_does_not_suppress_block(self):
        result = validate_part_time_hourly_rate(5.00, exemption_category="foreign_worker")
        self.assertTrue(result["blocked"])

    def test_no_exemption_non_compliant_has_no_exempt_flag(self):
        result = validate_part_time_hourly_rate(5.00)
        self.assertFalse(result["exempt"])

    def test_exemption_category_stored_in_result(self):
        result = validate_part_time_hourly_rate(5.00, exemption_category="apprentice")
        self.assertEqual(result["exemption_category"], "apprentice")

    def test_warning_suppressed_when_exempt_below_minimum(self):
        result = validate_part_time_hourly_rate(5.00, exemption_category="trainee")
        self.assertIsNone(result["warning"])

    # --- Custom monthly minimum (auto-adjust) ---

    def test_custom_monthly_minimum_changes_threshold(self):
        # With RM2,000/month minimum → hourly = 2000/208 ≈ 9.62
        result = validate_part_time_hourly_rate(9.00, monthly_minimum=2000.0)
        self.assertFalse(result["compliant"])

    def test_custom_monthly_minimum_passes_above(self):
        result = validate_part_time_hourly_rate(10.00, monthly_minimum=2000.0)
        self.assertTrue(result["compliant"])

    # --- Result shape ---

    def test_result_has_compliant_key(self):
        result = validate_part_time_hourly_rate(8.17)
        self.assertIn("compliant", result)

    def test_result_has_blocked_key(self):
        result = validate_part_time_hourly_rate(8.17)
        self.assertIn("blocked", result)

    def test_result_has_exempt_key(self):
        result = validate_part_time_hourly_rate(8.17)
        self.assertIn("exempt", result)

    def test_result_has_hourly_rate_key(self):
        result = validate_part_time_hourly_rate(8.17)
        self.assertIn("hourly_rate", result)

    def test_result_has_minimum_hourly_key(self):
        result = validate_part_time_hourly_rate(8.17)
        self.assertIn("minimum_hourly", result)

    def test_result_has_shortfall_key(self):
        result = validate_part_time_hourly_rate(8.17)
        self.assertIn("shortfall", result)

    def test_result_has_warning_key(self):
        result = validate_part_time_hourly_rate(8.17)
        self.assertIn("warning", result)

    def test_hourly_rate_echoed_in_result(self):
        result = validate_part_time_hourly_rate(8.50)
        self.assertAlmostEqual(result["hourly_rate"], 8.50)


# ---------------------------------------------------------------------------
# generate_part_time_compliance_report()
# ---------------------------------------------------------------------------


class TestGeneratePartTimeComplianceReport(FrappeTestCase):
    """Test generate_part_time_compliance_report() — batch compliance check."""

    def _make_employees(self):
        return [
            {"name": "EMP-001", "hourly_rate": 10.00, "department": "Operations", "company": "Acme"},
            {"name": "EMP-002", "hourly_rate": 7.50, "department": "Retail", "company": "Acme"},
            {"name": "EMP-003", "hourly_rate": 5.00, "exemption_category": "apprentice",
             "department": "Training", "company": "Acme"},
        ]

    def test_report_has_total_employees(self):
        report = generate_part_time_compliance_report(self._make_employees())
        self.assertEqual(report["total_employees"], 3)

    def test_compliant_count_correct(self):
        report = generate_part_time_compliance_report(self._make_employees())
        self.assertEqual(report["compliant_count"], 1)  # EMP-001 only

    def test_non_compliant_count_correct(self):
        report = generate_part_time_compliance_report(self._make_employees())
        self.assertEqual(report["non_compliant_count"], 1)  # EMP-002

    def test_exempt_count_correct(self):
        report = generate_part_time_compliance_report(self._make_employees())
        self.assertEqual(report["exempt_count"], 1)  # EMP-003

    def test_rows_count_matches_employees(self):
        report = generate_part_time_compliance_report(self._make_employees())
        self.assertEqual(len(report["rows"]), 3)

    def test_row_status_pass_for_compliant(self):
        report = generate_part_time_compliance_report(self._make_employees())
        emp001_row = next(r for r in report["rows"] if r["employee"] == "EMP-001")
        self.assertEqual(emp001_row["status"], "PASS")

    def test_row_status_fail_for_non_compliant(self):
        report = generate_part_time_compliance_report(self._make_employees())
        emp002_row = next(r for r in report["rows"] if r["employee"] == "EMP-002")
        self.assertEqual(emp002_row["status"], "FAIL")

    def test_row_status_exempt_for_exempted(self):
        report = generate_part_time_compliance_report(self._make_employees())
        emp003_row = next(r for r in report["rows"] if r["employee"] == "EMP-003")
        self.assertEqual(emp003_row["status"], "EXEMPT")

    def test_row_contains_minimum_hourly(self):
        report = generate_part_time_compliance_report(self._make_employees())
        self.assertAlmostEqual(report["rows"][0]["minimum_hourly"], 8.17, places=2)

    def test_row_contains_department(self):
        report = generate_part_time_compliance_report(self._make_employees())
        emp001_row = next(r for r in report["rows"] if r["employee"] == "EMP-001")
        self.assertEqual(emp001_row["department"], "Operations")

    def test_row_contains_company(self):
        report = generate_part_time_compliance_report(self._make_employees())
        emp001_row = next(r for r in report["rows"] if r["employee"] == "EMP-001")
        self.assertEqual(emp001_row["company"], "Acme")

    def test_report_minimum_hourly_is_8_17(self):
        report = generate_part_time_compliance_report(self._make_employees())
        self.assertAlmostEqual(report["minimum_hourly"], 8.17, places=2)

    def test_report_monthly_minimum_is_1700(self):
        report = generate_part_time_compliance_report(self._make_employees())
        self.assertEqual(report["monthly_minimum"], 1700.0)

    def test_empty_employees_returns_zero_counts(self):
        report = generate_part_time_compliance_report([])
        self.assertEqual(report["total_employees"], 0)
        self.assertEqual(report["compliant_count"], 0)
        self.assertEqual(report["non_compliant_count"], 0)
        self.assertEqual(report["exempt_count"], 0)
        self.assertEqual(report["rows"], [])

    def test_custom_monthly_minimum_applied_to_all_rows(self):
        # RM2,000 minimum → hourly = 9.62 → EMP-001 at 10.00 still passes
        employees = [{"name": "EMP-001", "hourly_rate": 10.00}]
        report = generate_part_time_compliance_report(employees, monthly_minimum=2000.0)
        self.assertEqual(report["compliant_count"], 1)

    def test_custom_monthly_minimum_fails_previously_compliant(self):
        # RM2,000 minimum → hourly ≈ 9.62 → rate of 9.00 now fails
        employees = [{"name": "EMP-A", "hourly_rate": 9.00}]
        report = generate_part_time_compliance_report(employees, monthly_minimum=2000.0)
        self.assertEqual(report["non_compliant_count"], 1)

    def test_all_compliant_report(self):
        employees = [
            {"name": "E1", "hourly_rate": 10.00},
            {"name": "E2", "hourly_rate": 15.00},
        ]
        report = generate_part_time_compliance_report(employees)
        self.assertEqual(report["non_compliant_count"], 0)
        self.assertEqual(report["compliant_count"], 2)

    def test_all_non_compliant_report(self):
        employees = [
            {"name": "E1", "hourly_rate": 5.00},
            {"name": "E2", "hourly_rate": 6.00},
        ]
        report = generate_part_time_compliance_report(employees)
        self.assertEqual(report["non_compliant_count"], 2)
        self.assertEqual(report["compliant_count"], 0)

    def test_report_has_rows_key(self):
        report = generate_part_time_compliance_report([])
        self.assertIn("rows", report)

    def test_report_has_minimum_hourly_key(self):
        report = generate_part_time_compliance_report([])
        self.assertIn("minimum_hourly", report)

    def test_report_has_monthly_minimum_key(self):
        report = generate_part_time_compliance_report([])
        self.assertIn("monthly_minimum", report)
