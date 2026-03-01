"""Tests for US-184: Enforce Part-Time Employee Minimum Hourly Rate
Against RM1,700 Monthly Wage Floor Proration.

Minimum Wages Order 2022 (P.U.(A) 268/2022): RM1,700/month effective 1 February 2023.
Part-time proration: RM1,700 ÷ 26 working days ÷ 8 hours = RM8.17/hour minimum.
= RM1,700 ÷ 208 hours = RM8.17/hour minimum.

Applies to ALL employers from August 2025 (micro-employer extension).

NWCC Act exemptions:
  - Apprentices under the National Apprenticeship Act
  - Disabled workers under specific MOHR disabled worker schemes
  - Contract trainees under MOHR gazette
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


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class TestPartTimeMinHourlyConstants(FrappeTestCase):
    """Verify module constants match statutory requirements."""

    def test_working_days_per_month_is_26(self):
        """LHDN/MOHR standard: 26 working days per month."""
        self.assertEqual(PART_TIME_WORKING_DAYS_PER_MONTH, 26)

    def test_hours_per_day_is_8(self):
        """Standard working hours per day."""
        self.assertEqual(PART_TIME_HOURS_PER_DAY, 8)

    def test_working_hours_per_month_is_208(self):
        """26 days × 8 hours = 208 hours per month."""
        self.assertEqual(PART_TIME_WORKING_HOURS_PER_MONTH, 208)

    def test_exempt_categories_contains_apprentice(self):
        """National Apprenticeship Act exemption must be present."""
        self.assertIn("apprentice", EXEMPT_CATEGORIES)

    def test_exempt_categories_contains_disabled_worker(self):
        """MOHR Disabled Worker Scheme exemption must be present."""
        self.assertIn("disabled_worker", EXEMPT_CATEGORIES)

    def test_exempt_categories_contains_trainee(self):
        """Contract trainee under MOHR gazette must be present."""
        self.assertIn("trainee", EXEMPT_CATEGORIES)

    def test_exempt_categories_has_three_entries(self):
        self.assertEqual(len(EXEMPT_CATEGORIES), 3)


# ---------------------------------------------------------------------------
# compute_minimum_hourly_rate()
# ---------------------------------------------------------------------------


class TestComputeMinimumHourlyRate(FrappeTestCase):
    """Test compute_minimum_hourly_rate() — RM1,700 ÷ 208 hours."""

    def test_default_minimum_hourly_is_8_17(self):
        """RM1,700 / 208 = RM8.1731... rounds to RM8.17."""
        result = compute_minimum_hourly_rate()
        self.assertAlmostEqual(result["minimum_hourly"], 8.17, places=2)

    def test_default_monthly_minimum_is_1700(self):
        result = compute_minimum_hourly_rate()
        self.assertAlmostEqual(result["monthly_minimum"], 1700.0)

    def test_working_hours_per_month_in_result_is_208(self):
        result = compute_minimum_hourly_rate()
        self.assertEqual(result["working_hours_per_month"], 208)

    def test_custom_monthly_minimum_adjusts_rate(self):
        """When minimum wage changes, the hourly rate auto-adjusts."""
        result = compute_minimum_hourly_rate(monthly_minimum=2000.0)
        expected = round(2000.0 / 208, 2)
        self.assertAlmostEqual(result["minimum_hourly"], expected, places=2)
        self.assertAlmostEqual(result["monthly_minimum"], 2000.0)

    def test_custom_monthly_minimum_lower_gives_lower_hourly(self):
        result = compute_minimum_hourly_rate(monthly_minimum=1500.0)
        expected = round(1500.0 / 208, 2)
        self.assertAlmostEqual(result["minimum_hourly"], expected, places=2)

    def test_result_has_all_required_keys(self):
        result = compute_minimum_hourly_rate()
        self.assertIn("minimum_hourly", result)
        self.assertIn("monthly_minimum", result)
        self.assertIn("working_hours_per_month", result)


# ---------------------------------------------------------------------------
# validate_part_time_hourly_rate() — compliant cases
# ---------------------------------------------------------------------------


class TestValidatePartTimeHourlyRateCompliant(FrappeTestCase):
    """Test validate_part_time_hourly_rate() for compliant employees."""

    def test_rate_above_minimum_is_compliant(self):
        """RM10.00/hour > RM8.17 minimum → compliant."""
        result = validate_part_time_hourly_rate(hourly_rate=10.00)
        self.assertTrue(result["compliant"])

    def test_rate_at_minimum_is_compliant(self):
        """Rate exactly at minimum (RM8.17) → compliant."""
        result = validate_part_time_hourly_rate(hourly_rate=8.17)
        self.assertTrue(result["compliant"])

    def test_compliant_not_blocked(self):
        result = validate_part_time_hourly_rate(hourly_rate=10.00)
        self.assertFalse(result["blocked"])

    def test_compliant_no_warning(self):
        result = validate_part_time_hourly_rate(hourly_rate=10.00)
        self.assertIsNone(result["warning"])

    def test_compliant_no_shortfall(self):
        result = validate_part_time_hourly_rate(hourly_rate=10.00)
        self.assertIsNone(result["shortfall"])

    def test_compliant_result_has_hourly_rate(self):
        result = validate_part_time_hourly_rate(hourly_rate=10.00)
        self.assertAlmostEqual(result["hourly_rate"], 10.00)

    def test_compliant_result_has_minimum_hourly(self):
        result = validate_part_time_hourly_rate(hourly_rate=10.00)
        self.assertAlmostEqual(result["minimum_hourly"], 8.17, places=2)

    def test_high_rate_is_compliant(self):
        """RM50/hour is well above minimum."""
        result = validate_part_time_hourly_rate(hourly_rate=50.00)
        self.assertTrue(result["compliant"])
        self.assertFalse(result["blocked"])


# ---------------------------------------------------------------------------
# validate_part_time_hourly_rate() — non-compliant cases
# ---------------------------------------------------------------------------


class TestValidatePartTimeHourlyRateNonCompliant(FrappeTestCase):
    """Test validate_part_time_hourly_rate() for non-compliant employees."""

    def test_rate_below_minimum_not_compliant(self):
        """RM5.00/hour < RM8.17 minimum → non-compliant."""
        result = validate_part_time_hourly_rate(hourly_rate=5.00)
        self.assertFalse(result["compliant"])

    def test_rate_below_minimum_blocked(self):
        """Non-compliant without exemption → payroll blocked."""
        result = validate_part_time_hourly_rate(hourly_rate=5.00)
        self.assertTrue(result["blocked"])

    def test_rate_below_minimum_has_warning(self):
        """Non-compliant → warning message is populated."""
        result = validate_part_time_hourly_rate(hourly_rate=5.00)
        self.assertIsNotNone(result["warning"])

    def test_warning_mentions_minimum_wage_order(self):
        result = validate_part_time_hourly_rate(hourly_rate=5.00)
        self.assertIn("Minimum Wages Order", result["warning"])

    def test_warning_mentions_actual_rate(self):
        result = validate_part_time_hourly_rate(hourly_rate=5.00)
        self.assertIn("5.00", result["warning"])

    def test_warning_mentions_minimum_hourly(self):
        result = validate_part_time_hourly_rate(hourly_rate=5.00)
        self.assertIn("8.17", result["warning"])

    def test_shortfall_computed_correctly(self):
        """RM8.17 - RM5.00 = RM3.17 shortfall."""
        result = validate_part_time_hourly_rate(hourly_rate=5.00)
        self.assertIsNotNone(result["shortfall"])
        # 8.17 - 5.00 = 3.17 (approximately)
        self.assertAlmostEqual(result["shortfall"], 8.17 - 5.00, places=1)

    def test_shortfall_is_positive(self):
        result = validate_part_time_hourly_rate(hourly_rate=3.00)
        self.assertGreater(result["shortfall"], 0)

    def test_rate_just_below_minimum_blocked(self):
        """RM8.16 is just below RM8.17 → non-compliant."""
        result = validate_part_time_hourly_rate(hourly_rate=8.16)
        self.assertFalse(result["compliant"])
        self.assertTrue(result["blocked"])

    def test_zero_rate_is_non_compliant(self):
        result = validate_part_time_hourly_rate(hourly_rate=0.0)
        self.assertFalse(result["compliant"])
        self.assertTrue(result["blocked"])

    def test_result_has_minimum_hourly(self):
        result = validate_part_time_hourly_rate(hourly_rate=5.00)
        self.assertAlmostEqual(result["minimum_hourly"], 8.17, places=2)

    def test_result_not_exempt(self):
        result = validate_part_time_hourly_rate(hourly_rate=5.00)
        self.assertFalse(result["exempt"])


# ---------------------------------------------------------------------------
# validate_part_time_hourly_rate() — exemption cases
# ---------------------------------------------------------------------------


class TestValidatePartTimeHourlyRateExemptions(FrappeTestCase):
    """Test that recognised NWCC Act exemptions suppress the compliance block."""

    def test_apprentice_exemption_suppresses_block(self):
        """Apprentice under National Apprenticeship Act → block suppressed."""
        result = validate_part_time_hourly_rate(
            hourly_rate=5.00, exemption_category="apprentice"
        )
        self.assertFalse(result["blocked"])
        self.assertTrue(result["exempt"])

    def test_disabled_worker_exemption_suppresses_block(self):
        """MOHR Disabled Worker Scheme → block suppressed."""
        result = validate_part_time_hourly_rate(
            hourly_rate=5.00, exemption_category="disabled_worker"
        )
        self.assertFalse(result["blocked"])
        self.assertTrue(result["exempt"])

    def test_trainee_exemption_suppresses_block(self):
        """Contract trainee under MOHR gazette → block suppressed."""
        result = validate_part_time_hourly_rate(
            hourly_rate=5.00, exemption_category="trainee"
        )
        self.assertFalse(result["blocked"])
        self.assertTrue(result["exempt"])

    def test_exempt_result_stores_exemption_category(self):
        result = validate_part_time_hourly_rate(
            hourly_rate=5.00, exemption_category="apprentice"
        )
        self.assertEqual(result["exemption_category"], "apprentice")

    def test_exempt_still_shows_non_compliant_flag(self):
        """Exempt employee is not blocked, but is still non-compliant (rate still below min)."""
        result = validate_part_time_hourly_rate(
            hourly_rate=5.00, exemption_category="apprentice"
        )
        self.assertFalse(result["compliant"])
        self.assertTrue(result["exempt"])

    def test_exemption_case_insensitive(self):
        """Exemption category matching is case-insensitive."""
        result = validate_part_time_hourly_rate(
            hourly_rate=5.00, exemption_category="APPRENTICE"
        )
        self.assertFalse(result["blocked"])
        self.assertTrue(result["exempt"])

    def test_unknown_exemption_does_not_suppress_block(self):
        """An unrecognised exemption category does NOT suppress the block."""
        result = validate_part_time_hourly_rate(
            hourly_rate=5.00, exemption_category="unknown_category"
        )
        self.assertTrue(result["blocked"])
        self.assertFalse(result["exempt"])

    def test_no_exemption_for_compliant_rate(self):
        """Compliant rate with no exemption → no block, exempt=False."""
        result = validate_part_time_hourly_rate(
            hourly_rate=10.00, exemption_category=None
        )
        self.assertTrue(result["compliant"])
        self.assertFalse(result["blocked"])
        self.assertFalse(result["exempt"])

    def test_exemption_with_compliant_rate(self):
        """Compliant rate + exemption → still compliant and not blocked."""
        result = validate_part_time_hourly_rate(
            hourly_rate=10.00, exemption_category="apprentice"
        )
        self.assertTrue(result["compliant"])
        self.assertFalse(result["blocked"])


# ---------------------------------------------------------------------------
# validate_part_time_hourly_rate() — auto-adjust for minimum wage changes
# ---------------------------------------------------------------------------


class TestValidatePartTimeHourlyRateAutoAdjust(FrappeTestCase):
    """Test that minimum hourly rate auto-adjusts when minimum wage changes."""

    def test_custom_minimum_wage_adjusts_validation(self):
        """When monthly minimum wage is raised to RM2,000, hourly threshold rises too."""
        # RM2,000 / 208 = RM9.615... → RM9.62 hourly minimum
        result = validate_part_time_hourly_rate(
            hourly_rate=8.50, monthly_minimum=2000.0
        )
        # 8.50 < 9.62 → non-compliant
        self.assertFalse(result["compliant"])
        self.assertTrue(result["blocked"])

    def test_rate_compliant_under_old_minimum_blocked_under_new(self):
        """Rate that was compliant at RM1,700 minimum may fail at RM2,000."""
        # At RM1,700: min = 8.17, rate 8.50 → compliant
        old_result = validate_part_time_hourly_rate(
            hourly_rate=8.50, monthly_minimum=1700.0
        )
        self.assertTrue(old_result["compliant"])

        # At RM2,000: min = 9.62, rate 8.50 → non-compliant
        new_result = validate_part_time_hourly_rate(
            hourly_rate=8.50, monthly_minimum=2000.0
        )
        self.assertFalse(new_result["compliant"])

    def test_minimum_hourly_in_result_reflects_custom_wage(self):
        result = validate_part_time_hourly_rate(
            hourly_rate=10.00, monthly_minimum=2080.0
        )
        # RM2,080 / 208 = RM10.00 exactly
        self.assertAlmostEqual(result["minimum_hourly"], 10.00, places=2)


# ---------------------------------------------------------------------------
# generate_part_time_compliance_report()
# ---------------------------------------------------------------------------


class TestGeneratePartTimeComplianceReport(FrappeTestCase):
    """Test generate_part_time_compliance_report() for batch validation."""

    def _make_employees(self):
        return [
            {"name": "EMP-001", "hourly_rate": 10.00, "exemption_category": None},       # PASS
            {"name": "EMP-002", "hourly_rate": 5.00, "exemption_category": None},        # FAIL
            {"name": "EMP-003", "hourly_rate": 5.00, "exemption_category": "apprentice"},  # EXEMPT
            {"name": "EMP-004", "hourly_rate": 8.17, "exemption_category": None},        # PASS (at limit)
            {"name": "EMP-005", "hourly_rate": 3.00, "exemption_category": "trainee"},   # EXEMPT
        ]

    def test_total_employees_count(self):
        report = generate_part_time_compliance_report(self._make_employees())
        self.assertEqual(report["total_employees"], 5)

    def test_compliant_count(self):
        report = generate_part_time_compliance_report(self._make_employees())
        self.assertEqual(report["compliant_count"], 2)  # EMP-001, EMP-004

    def test_non_compliant_count(self):
        report = generate_part_time_compliance_report(self._make_employees())
        self.assertEqual(report["non_compliant_count"], 1)  # EMP-002

    def test_exempt_count(self):
        report = generate_part_time_compliance_report(self._make_employees())
        self.assertEqual(report["exempt_count"], 2)  # EMP-003, EMP-005

    def test_rows_count_matches_employees(self):
        report = generate_part_time_compliance_report(self._make_employees())
        self.assertEqual(len(report["rows"]), 5)

    def test_row_pass_status_for_compliant(self):
        report = generate_part_time_compliance_report(self._make_employees())
        emp001_row = next(r for r in report["rows"] if r["employee"] == "EMP-001")
        self.assertEqual(emp001_row["status"], "PASS")

    def test_row_fail_status_for_non_compliant(self):
        report = generate_part_time_compliance_report(self._make_employees())
        emp002_row = next(r for r in report["rows"] if r["employee"] == "EMP-002")
        self.assertEqual(emp002_row["status"], "FAIL")

    def test_row_exempt_status_for_exempted(self):
        report = generate_part_time_compliance_report(self._make_employees())
        emp003_row = next(r for r in report["rows"] if r["employee"] == "EMP-003")
        self.assertEqual(emp003_row["status"], "EXEMPT")

    def test_report_contains_minimum_hourly(self):
        report = generate_part_time_compliance_report([])
        self.assertIn("minimum_hourly", report)
        self.assertAlmostEqual(report["minimum_hourly"], 8.17, places=2)

    def test_report_contains_monthly_minimum(self):
        report = generate_part_time_compliance_report([])
        self.assertIn("monthly_minimum", report)
        self.assertAlmostEqual(report["monthly_minimum"], 1700.0)

    def test_empty_employee_list(self):
        report = generate_part_time_compliance_report([])
        self.assertEqual(report["total_employees"], 0)
        self.assertEqual(report["compliant_count"], 0)
        self.assertEqual(report["non_compliant_count"], 0)
        self.assertEqual(report["exempt_count"], 0)
        self.assertEqual(report["rows"], [])

    def test_row_shortfall_for_fail(self):
        report = generate_part_time_compliance_report(self._make_employees())
        emp002_row = next(r for r in report["rows"] if r["employee"] == "EMP-002")
        # RM8.17 - RM5.00 = RM3.17 shortfall
        self.assertIsNotNone(emp002_row["shortfall"])
        self.assertGreater(emp002_row["shortfall"], 0)

    def test_row_no_shortfall_for_pass(self):
        report = generate_part_time_compliance_report(self._make_employees())
        emp001_row = next(r for r in report["rows"] if r["employee"] == "EMP-001")
        self.assertIsNone(emp001_row["shortfall"])

    def test_row_contains_actual_hourly_rate(self):
        report = generate_part_time_compliance_report(self._make_employees())
        emp001_row = next(r for r in report["rows"] if r["employee"] == "EMP-001")
        self.assertAlmostEqual(emp001_row["hourly_rate"], 10.00)

    def test_row_contains_minimum_hourly(self):
        report = generate_part_time_compliance_report(self._make_employees())
        emp001_row = next(r for r in report["rows"] if r["employee"] == "EMP-001")
        self.assertAlmostEqual(emp001_row["minimum_hourly"], 8.17, places=2)

    def test_department_and_company_included_in_row(self):
        employees = [
            {
                "name": "EMP-006",
                "hourly_rate": 10.00,
                "exemption_category": None,
                "department": "Sales",
                "company": "Prisma Tech",
            }
        ]
        report = generate_part_time_compliance_report(employees)
        row = report["rows"][0]
        self.assertEqual(row["department"], "Sales")
        self.assertEqual(row["company"], "Prisma Tech")

    def test_custom_monthly_minimum_propagates_to_report(self):
        """Report uses custom minimum wage if provided."""
        employees = [
            {"name": "EMP-007", "hourly_rate": 8.50, "exemption_category": None}
        ]
        # At RM2,000/month, minimum = RM9.62 → 8.50 fails
        report = generate_part_time_compliance_report(employees, monthly_minimum=2000.0)
        self.assertEqual(report["non_compliant_count"], 1)
        self.assertAlmostEqual(report["minimum_hourly"], round(2000.0 / 208, 2), places=2)

    def test_all_compliant_report(self):
        employees = [
            {"name": "EMP-A", "hourly_rate": 10.00, "exemption_category": None},
            {"name": "EMP-B", "hourly_rate": 15.00, "exemption_category": None},
        ]
        report = generate_part_time_compliance_report(employees)
        self.assertEqual(report["compliant_count"], 2)
        self.assertEqual(report["non_compliant_count"], 0)
        self.assertEqual(report["exempt_count"], 0)

    def test_all_non_compliant_report(self):
        employees = [
            {"name": "EMP-A", "hourly_rate": 5.00, "exemption_category": None},
            {"name": "EMP-B", "hourly_rate": 3.00, "exemption_category": None},
        ]
        report = generate_part_time_compliance_report(employees)
        self.assertEqual(report["compliant_count"], 0)
        self.assertEqual(report["non_compliant_count"], 2)
        self.assertEqual(report["exempt_count"], 0)
