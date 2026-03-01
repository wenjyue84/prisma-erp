"""Tests for US-144: Extend Minimum Wage Validation to Cover Micro-Employers from August 1, 2025.

Covers:
- MINIMUM_WAGE_SCHEDULE structure and entries
- get_applicable_minimum_wage() — date + headcount logic
- check_minimum_wage_with_headcount() — grace period, MOHR exemption, part-time
- _validate_salary_slip_minimum_wage() integration — headcount-aware, MOHR ref suppression
"""

from unittest.mock import MagicMock, patch

from frappe.tests.utils import FrappeTestCase

from lhdn_payroll_integration.utils.employment_compliance import (
    MINIMUM_WAGE_SCHEDULE,
    check_minimum_wage_with_headcount,
    get_applicable_minimum_wage,
)


class TestMinimumWageSchedule(FrappeTestCase):
    """Test the MINIMUM_WAGE_SCHEDULE constant structure."""

    def test_schedule_has_two_entries(self):
        self.assertEqual(len(MINIMUM_WAGE_SCHEDULE), 2)

    def test_first_entry_feb_2025_threshold_5(self):
        entry = next(e for e in MINIMUM_WAGE_SCHEDULE if e["effective_date"] == "2025-02-01")
        self.assertEqual(entry["min_wage"], 1700.0)
        self.assertEqual(entry["headcount_threshold"], 5)

    def test_second_entry_aug_2025_no_threshold(self):
        entry = next(e for e in MINIMUM_WAGE_SCHEDULE if e["effective_date"] == "2025-08-01")
        self.assertEqual(entry["min_wage"], 1700.0)
        self.assertIsNone(entry["headcount_threshold"])


class TestGetApplicableMinimumWage(FrappeTestCase):
    """Test get_applicable_minimum_wage() for various date + headcount combinations."""

    def test_before_feb_2025_no_minimum_any_employer(self):
        """Before Feb 2025, no entry is effective — returns None."""
        self.assertIsNone(get_applicable_minimum_wage("2025-01-31", employer_headcount=10))
        self.assertIsNone(get_applicable_minimum_wage("2025-01-15", employer_headcount=1))

    def test_grace_period_micro_employer_no_minimum(self):
        """Micro-employer (<5 employees) during grace period (Feb–Jul 2025) gets None."""
        for period_date in ["2025-02-01", "2025-04-15", "2025-07-31"]:
            result = get_applicable_minimum_wage(period_date, employer_headcount=4)
            self.assertIsNone(result, f"Expected None for {period_date}, headcount=4")

    def test_grace_period_exactly_4_employees_no_minimum(self):
        self.assertIsNone(get_applicable_minimum_wage("2025-06-30", employer_headcount=4))

    def test_grace_period_larger_employer_gets_1700(self):
        """Employer with >= 5 employees during grace period — RM1,700 enforced."""
        for period_date in ["2025-02-01", "2025-04-15", "2025-07-31"]:
            result = get_applicable_minimum_wage(period_date, employer_headcount=5)
            self.assertEqual(result, 1700.0, f"Expected RM1,700 for {period_date}, headcount=5")

    def test_grace_period_exactly_5_employees_enforced(self):
        self.assertEqual(get_applicable_minimum_wage("2025-06-30", employer_headcount=5), 1700.0)

    def test_post_aug_2025_micro_employer_enforced(self):
        """From Aug 2025, even 1-employee companies must comply."""
        for period_date in ["2025-08-01", "2025-09-30", "2026-01-31"]:
            result = get_applicable_minimum_wage(period_date, employer_headcount=1)
            self.assertEqual(result, 1700.0, f"Expected RM1,700 for {period_date}, headcount=1")

    def test_post_aug_2025_all_headcounts_enforced(self):
        for headcount in [1, 2, 3, 4, 5, 100]:
            result = get_applicable_minimum_wage("2025-08-01", employer_headcount=headcount)
            self.assertEqual(result, 1700.0, f"Expected RM1,700 for headcount={headcount}")

    def test_post_aug_2025_date_boundary(self):
        """Exact boundary: Aug 1 = enforced, Jul 31 = grace for micro."""
        self.assertIsNone(get_applicable_minimum_wage("2025-07-31", employer_headcount=3))
        self.assertEqual(get_applicable_minimum_wage("2025-08-01", employer_headcount=3), 1700.0)


class TestCheckMinimumWageWithHeadcount(FrappeTestCase):
    """Test check_minimum_wage_with_headcount() — the core US-144 function."""

    # --- Grace period (micro-employer exempt) ---

    def test_grace_period_micro_employer_below_wage_is_compliant(self):
        """Micro-employer during grace period: even RM1,500 is compliant."""
        result = check_minimum_wage_with_headcount(
            monthly_salary=1500,
            period_end_date="2025-06-30",
            employer_headcount=3,
        )
        self.assertTrue(result["compliant"])
        self.assertIsNone(result["warning"])
        self.assertTrue(result["grace_period"])
        self.assertIsNone(result["minimum"])

    def test_grace_period_larger_employer_below_wage_fails(self):
        """Employer with >= 5 employees during grace period below RM1,700 fails."""
        result = check_minimum_wage_with_headcount(
            monthly_salary=1500,
            period_end_date="2025-06-30",
            employer_headcount=5,
        )
        self.assertFalse(result["compliant"])
        self.assertIsNotNone(result["warning"])
        self.assertFalse(result["grace_period"])

    def test_grace_period_larger_employer_at_minimum_passes(self):
        result = check_minimum_wage_with_headcount(
            monthly_salary=1700,
            period_end_date="2025-06-30",
            employer_headcount=6,
        )
        self.assertTrue(result["compliant"])
        self.assertFalse(result["grace_period"])

    # --- Post-Aug 2025 (all employers enforced) ---

    def test_post_aug_micro_employer_below_wage_fails(self):
        """From Aug 2025, micro-employer with salary below RM1,700 fails."""
        result = check_minimum_wage_with_headcount(
            monthly_salary=1500,
            period_end_date="2025-08-01",
            employer_headcount=2,
        )
        self.assertFalse(result["compliant"])
        self.assertIsNotNone(result["warning"])
        self.assertFalse(result["grace_period"])
        self.assertIn("1500", result["warning"])
        self.assertIn("1700", result["warning"])

    def test_post_aug_micro_employer_at_minimum_passes(self):
        result = check_minimum_wage_with_headcount(
            monthly_salary=1700,
            period_end_date="2025-08-31",
            employer_headcount=1,
        )
        self.assertTrue(result["compliant"])
        self.assertIsNone(result["warning"])

    def test_post_aug_any_employer_above_minimum_passes(self):
        result = check_minimum_wage_with_headcount(
            monthly_salary=2500,
            period_end_date="2026-01-31",
            employer_headcount=1,
        )
        self.assertTrue(result["compliant"])

    # --- MOHR exemption ---

    def test_mohr_exemption_ref_bypasses_check(self):
        """A MOHR exemption reference suppresses validation entirely."""
        result = check_minimum_wage_with_headcount(
            monthly_salary=1000,
            period_end_date="2025-08-31",
            employer_headcount=1,
            mohr_exemption_ref="MOHR-2025-001234",
        )
        self.assertTrue(result["compliant"])
        self.assertIsNone(result["warning"])
        self.assertTrue(result["mohr_exempt"])
        self.assertFalse(result["grace_period"])

    def test_empty_mohr_ref_does_not_bypass(self):
        result = check_minimum_wage_with_headcount(
            monthly_salary=1000,
            period_end_date="2025-08-31",
            employer_headcount=1,
            mohr_exemption_ref="",
        )
        self.assertFalse(result["compliant"])
        self.assertFalse(result["mohr_exempt"])

    def test_none_mohr_ref_does_not_bypass(self):
        result = check_minimum_wage_with_headcount(
            monthly_salary=1000,
            period_end_date="2025-08-31",
            employer_headcount=1,
            mohr_exemption_ref=None,
        )
        self.assertFalse(result["compliant"])
        self.assertFalse(result["mohr_exempt"])

    # --- Part-time ---

    def test_part_time_grace_period_micro_employer_compliant(self):
        """Part-time micro-employer during grace period — always compliant."""
        result = check_minimum_wage_with_headcount(
            monthly_salary=1000,
            period_end_date="2025-06-30",
            employer_headcount=2,
            employment_type="Part-time",
            contracted_hours=120,
        )
        self.assertTrue(result["compliant"])
        self.assertTrue(result["grace_period"])

    def test_part_time_post_aug_below_hourly_fails(self):
        """Post-Aug 2025 part-time with hourly rate below RM8.17 fails."""
        # 1000 / 160 = 6.25/hour < 8.17
        result = check_minimum_wage_with_headcount(
            monthly_salary=1000,
            period_end_date="2025-08-31",
            employer_headcount=1,
            employment_type="Part-time",
            contracted_hours=160,
        )
        self.assertFalse(result["compliant"])
        self.assertIn("8.17", result["warning"])

    def test_part_time_post_aug_at_hourly_minimum_passes(self):
        # 8.17 * 160 = 1307.20
        result = check_minimum_wage_with_headcount(
            monthly_salary=1307.20,
            period_end_date="2025-08-31",
            employer_headcount=1,
            employment_type="Part-time",
            contracted_hours=160,
        )
        self.assertTrue(result["compliant"])

    # --- Return dict structure ---

    def test_result_has_all_required_keys(self):
        result = check_minimum_wage_with_headcount(
            monthly_salary=1700,
            period_end_date="2025-08-31",
            employer_headcount=1,
        )
        for key in ["compliant", "warning", "employment_type", "minimum", "actual", "grace_period", "mohr_exempt"]:
            self.assertIn(key, result, f"Missing key: {key}")

    def test_actual_reflects_input_salary(self):
        result = check_minimum_wage_with_headcount(
            monthly_salary=1800,
            period_end_date="2025-08-31",
            employer_headcount=1,
        )
        self.assertEqual(result["actual"], 1800.0)


class TestSalarySlipMinimumWageIntegration(FrappeTestCase):
    """Integration tests: _validate_salary_slip_minimum_wage uses headcount-aware check."""

    def _make_doc(self, gross_pay, period_end="2025-08-31", company="Test Co", mohr_ref=None):
        doc = MagicMock()
        data = {
            "doctype": "Salary Slip",
            "base_gross_pay": gross_pay,
            "gross_pay": gross_pay,
            "employee": "EMP-0001",
            "period_end": period_end,
            "company": company,
            "custom_mohr_exemption_ref": mohr_ref,
        }
        doc.get = lambda key, default=None: data.get(key, default)
        doc.doctype = "Salary Slip"
        return doc

    @patch("lhdn_payroll_integration.utils.validation.frappe")
    def test_post_aug_micro_employer_below_wage_warns(self, mock_frappe):
        """Post Aug 2025 micro-employer with RM1,500 triggers warning."""
        mock_frappe.db.exists.return_value = True
        mock_frappe.db.count.return_value = 2  # micro-employer
        emp = MagicMock()
        emp.get = lambda key, default=None: {
            "custom_employment_type": "Full-time",
            "custom_contracted_hours_per_month": None,
        }.get(key, default)
        mock_frappe.get_cached_doc.return_value = emp

        doc = self._make_doc(1500, period_end="2025-08-31")
        from lhdn_payroll_integration.utils.validation import _validate_salary_slip_minimum_wage
        _validate_salary_slip_minimum_wage(doc)
        mock_frappe.msgprint.assert_called_once()

    @patch("lhdn_payroll_integration.utils.validation.frappe")
    def test_grace_period_micro_employer_no_warning(self, mock_frappe):
        """Grace period micro-employer (RM1,500) — no warning."""
        mock_frappe.db.exists.return_value = True
        mock_frappe.db.count.return_value = 3  # micro-employer
        emp = MagicMock()
        emp.get = lambda key, default=None: {
            "custom_employment_type": "Full-time",
            "custom_contracted_hours_per_month": None,
        }.get(key, default)
        mock_frappe.get_cached_doc.return_value = emp

        doc = self._make_doc(1500, period_end="2025-06-30")
        from lhdn_payroll_integration.utils.validation import _validate_salary_slip_minimum_wage
        _validate_salary_slip_minimum_wage(doc)
        mock_frappe.msgprint.assert_not_called()

    @patch("lhdn_payroll_integration.utils.validation.frappe")
    def test_mohr_exemption_ref_suppresses_warning(self, mock_frappe):
        """MOHR exemption reference on salary slip suppresses warning."""
        mock_frappe.db.exists.return_value = True
        mock_frappe.db.count.return_value = 1  # micro-employer
        emp = MagicMock()
        emp.get = lambda key, default=None: {
            "custom_employment_type": "Full-time",
            "custom_contracted_hours_per_month": None,
        }.get(key, default)
        mock_frappe.get_cached_doc.return_value = emp

        doc = self._make_doc(1000, period_end="2025-08-31", mohr_ref="MOHR-2025-001234")
        from lhdn_payroll_integration.utils.validation import _validate_salary_slip_minimum_wage
        _validate_salary_slip_minimum_wage(doc)
        mock_frappe.msgprint.assert_not_called()

    @patch("lhdn_payroll_integration.utils.validation.frappe")
    def test_larger_employer_grace_period_still_checked(self, mock_frappe):
        """Employer with >= 5 employees — grace period doesn't apply, RM1,500 warns."""
        mock_frappe.db.exists.return_value = True
        mock_frappe.db.count.return_value = 7  # large employer
        emp = MagicMock()
        emp.get = lambda key, default=None: {
            "custom_employment_type": "Full-time",
            "custom_contracted_hours_per_month": None,
        }.get(key, default)
        mock_frappe.get_cached_doc.return_value = emp

        doc = self._make_doc(1500, period_end="2025-06-30")
        from lhdn_payroll_integration.utils.validation import _validate_salary_slip_minimum_wage
        _validate_salary_slip_minimum_wage(doc)
        mock_frappe.msgprint.assert_called_once()
