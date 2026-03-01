"""Tests for US-228: Enforce RM1,700 Minimum Wage for ALL Employers from 1 August 2025.

Covers:
- Post-Aug 2025 salary slip submission raises hard ValidationError (frappe.throw)
- Grace-period violations continue to warn (frappe.msgprint)
- Warning/error text cites Minimum Wages Order 2024, 1 August 2025, RM10,000 per employee
- get_min_wage_migration_alert_employees() queries RM1,500-RM1,699.99 salary slips
- MOHR exemption suppresses hard error for post-Aug 2025 periods
"""

from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from lhdn_payroll_integration.utils.employment_compliance import (
    check_minimum_wage_with_headcount,
    get_min_wage_migration_alert_employees,
)
from lhdn_payroll_integration.utils.validation import (
    _period_is_post_aug_2025,
    _validate_salary_slip_minimum_wage,
)


class TestPeriodIsPostAug2025(FrappeTestCase):
    """Test _period_is_post_aug_2025() helper function."""

    def test_aug_1_2025_is_post(self):
        self.assertTrue(_period_is_post_aug_2025("2025-08-01"))

    def test_aug_31_2025_is_post(self):
        self.assertTrue(_period_is_post_aug_2025("2025-08-31"))

    def test_sep_2025_is_post(self):
        self.assertTrue(_period_is_post_aug_2025("2025-09-30"))

    def test_jan_2026_is_post(self):
        self.assertTrue(_period_is_post_aug_2025("2026-01-31"))

    def test_jul_31_2025_is_not_post(self):
        self.assertFalse(_period_is_post_aug_2025("2025-07-31"))

    def test_jun_2025_is_not_post(self):
        self.assertFalse(_period_is_post_aug_2025("2025-06-30"))

    def test_feb_2025_is_not_post(self):
        self.assertFalse(_period_is_post_aug_2025("2025-02-01"))

    def test_none_returns_false(self):
        self.assertFalse(_period_is_post_aug_2025(None))

    def test_empty_string_returns_false(self):
        self.assertFalse(_period_is_post_aug_2025(""))

    def test_invalid_date_returns_false(self):
        self.assertFalse(_period_is_post_aug_2025("not-a-date"))


class TestUniversalMinWageHardError(FrappeTestCase):
    """Aug 2025+ salary slips below RM1,700 raise hard ValidationError (not soft warning)."""

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

    def _setup_emp_mock(self, mock_frappe, headcount=5):
        mock_frappe.db.exists.return_value = True
        mock_frappe.db.count.return_value = headcount
        emp = MagicMock()
        emp.get = lambda key, default=None: {
            "custom_employment_type": "Full-time",
            "custom_contracted_hours_per_month": None,
        }.get(key, default)
        mock_frappe.get_cached_doc.return_value = emp

    @patch("lhdn_payroll_integration.utils.validation.frappe")
    def test_aug_2025_below_1700_calls_throw(self, mock_frappe):
        """Post-Aug 2025: salary below RM1,700 calls frappe.throw (hard error)."""
        self._setup_emp_mock(mock_frappe)
        doc = self._make_doc(1500, period_end="2025-08-31")
        _validate_salary_slip_minimum_wage(doc)
        mock_frappe.throw.assert_called_once()
        mock_frappe.msgprint.assert_not_called()

    @patch("lhdn_payroll_integration.utils.validation.frappe")
    def test_sep_2025_below_1700_calls_throw(self, mock_frappe):
        """Post-Aug 2025 (Sep 2025): salary below RM1,700 calls frappe.throw."""
        self._setup_emp_mock(mock_frappe, headcount=50)
        doc = self._make_doc(1699, period_end="2025-09-30")
        _validate_salary_slip_minimum_wage(doc)
        mock_frappe.throw.assert_called_once()
        mock_frappe.msgprint.assert_not_called()

    @patch("lhdn_payroll_integration.utils.validation.frappe")
    def test_aug_2025_at_1700_no_error(self, mock_frappe):
        """Post-Aug 2025: salary exactly RM1,700 — no throw, no msgprint."""
        self._setup_emp_mock(mock_frappe, headcount=1)
        doc = self._make_doc(1700, period_end="2025-08-31")
        _validate_salary_slip_minimum_wage(doc)
        mock_frappe.throw.assert_not_called()
        mock_frappe.msgprint.assert_not_called()

    @patch("lhdn_payroll_integration.utils.validation.frappe")
    def test_aug_2025_above_1700_no_error(self, mock_frappe):
        """Post-Aug 2025: salary above RM1,700 — compliant."""
        self._setup_emp_mock(mock_frappe, headcount=2)
        doc = self._make_doc(2500, period_end="2025-08-31")
        _validate_salary_slip_minimum_wage(doc)
        mock_frappe.throw.assert_not_called()
        mock_frappe.msgprint.assert_not_called()

    @patch("lhdn_payroll_integration.utils.validation.frappe")
    def test_aug_2025_throw_title_cites_order_2024(self, mock_frappe):
        """throw() title cites Minimum Wages Order 2024."""
        self._setup_emp_mock(mock_frappe, headcount=1)
        doc = self._make_doc(1600, period_end="2025-08-31")
        _validate_salary_slip_minimum_wage(doc)
        mock_frappe.throw.assert_called_once()
        call_str = str(mock_frappe.throw.call_args)
        self.assertIn("2024", call_str)

    @patch("lhdn_payroll_integration.utils.validation.frappe")
    def test_grace_period_large_employer_below_1700_warns_not_throws(self, mock_frappe):
        """Grace period (Jun 2025): large employer below RM1,700 warns (not throws)."""
        self._setup_emp_mock(mock_frappe, headcount=10)
        doc = self._make_doc(1500, period_end="2025-06-30")
        _validate_salary_slip_minimum_wage(doc)
        mock_frappe.throw.assert_not_called()
        mock_frappe.msgprint.assert_called_once()

    @patch("lhdn_payroll_integration.utils.validation.frappe")
    def test_mohr_exemption_suppresses_throw_post_aug(self, mock_frappe):
        """MOHR exemption reference suppresses hard error even post-Aug 2025."""
        self._setup_emp_mock(mock_frappe, headcount=1)
        doc = self._make_doc(1000, period_end="2025-08-31", mohr_ref="MOHR-2025-001234")
        _validate_salary_slip_minimum_wage(doc)
        mock_frappe.throw.assert_not_called()
        mock_frappe.msgprint.assert_not_called()

    @patch("lhdn_payroll_integration.utils.validation.frappe")
    def test_micro_employer_aug_2025_below_1700_throws(self, mock_frappe):
        """Micro-employer (1 employee) in Aug 2025 — universal enforcement, throws."""
        self._setup_emp_mock(mock_frappe, headcount=1)
        doc = self._make_doc(1550, period_end="2025-08-01")
        _validate_salary_slip_minimum_wage(doc)
        mock_frappe.throw.assert_called_once()


class TestPenaltyTextUs228(FrappeTestCase):
    """Warning/error text references Minimum Wages Order 2024, 1 August 2025, RM10,000."""

    def test_post_aug_warning_cites_minimum_wages_order_2024(self):
        """check_minimum_wage_with_headcount warning cites Minimum Wages Order 2024."""
        result = check_minimum_wage_with_headcount(
            monthly_salary=1699,
            period_end_date="2025-08-31",
            employer_headcount=1,
        )
        self.assertFalse(result["compliant"])
        self.assertIn("2024", result["warning"])

    def test_post_aug_warning_cites_1_august_2025(self):
        """Warning text cites universal enforcement from 1 August 2025."""
        result = check_minimum_wage_with_headcount(
            monthly_salary=1600,
            period_end_date="2025-09-30",
            employer_headcount=2,
        )
        self.assertFalse(result["compliant"])
        self.assertIn("1 August 2025", result["warning"])

    def test_post_aug_warning_cites_rm10000_per_employee(self):
        """Warning text cites RM10,000 per employee fine."""
        result = check_minimum_wage_with_headcount(
            monthly_salary=1500,
            period_end_date="2026-01-31",
            employer_headcount=100,
        )
        self.assertFalse(result["compliant"])
        self.assertIn("10,000", result["warning"])
        self.assertIn("per employee", result["warning"])

    def test_post_aug_warning_contains_actual_salary(self):
        """Warning text includes the actual salary amount."""
        result = check_minimum_wage_with_headcount(
            monthly_salary=1650,
            period_end_date="2025-08-31",
            employer_headcount=1,
        )
        self.assertIn("1650", result["warning"])

    def test_post_aug_warning_contains_minimum_wage(self):
        """Warning text includes the minimum wage (RM1,700)."""
        result = check_minimum_wage_with_headcount(
            monthly_salary=1500,
            period_end_date="2025-08-31",
            employer_headcount=1,
        )
        self.assertIn("1700", result["warning"])


class TestMigrationAlertEmployees(FrappeTestCase):
    """Test get_min_wage_migration_alert_employees() — RM1,500-RM1,699.99 range."""

    @patch("lhdn_payroll_integration.utils.employment_compliance.frappe")
    def test_returns_employees_in_violation_range(self, mock_frappe):
        """Employees with submitted salary slips RM1,500-RM1,699.99 are returned."""
        mock_frappe.get_all.return_value = [
            {"employee": "EMP-001", "employee_name": "Ali", "gross_pay": 1500, "company": "Test"},
            {"employee": "EMP-002", "employee_name": "Siti", "gross_pay": 1699, "company": "Test"},
        ]
        result = get_min_wage_migration_alert_employees()
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["employee"], "EMP-001")

    @patch("lhdn_payroll_integration.utils.employment_compliance.frappe")
    def test_returns_empty_when_all_above_1700(self, mock_frappe):
        """Returns empty list when no salary slips are in the violation range."""
        mock_frappe.get_all.return_value = []
        result = get_min_wage_migration_alert_employees()
        self.assertEqual(result, [])

    @patch("lhdn_payroll_integration.utils.employment_compliance.frappe")
    def test_queries_salary_slip_doctype(self, mock_frappe):
        """Queries Salary Slip (not Employee) doctype."""
        mock_frappe.get_all.return_value = []
        get_min_wage_migration_alert_employees()
        mock_frappe.get_all.assert_called_once()
        call_args = mock_frappe.get_all.call_args
        positional_or_keyword = call_args[0][0] if call_args[0] else call_args[1].get("doctype", "")
        self.assertEqual(positional_or_keyword, "Salary Slip")

    @patch("lhdn_payroll_integration.utils.employment_compliance.frappe")
    def test_queries_correct_salary_range(self, mock_frappe):
        """frappe.get_all is called with RM1,500-RM1,699.99 range."""
        mock_frappe.get_all.return_value = []
        get_min_wage_migration_alert_employees()
        call_str = str(mock_frappe.get_all.call_args)
        self.assertIn("1500", call_str)
        self.assertIn("1699", call_str)

    @patch("lhdn_payroll_integration.utils.employment_compliance.frappe")
    def test_filters_by_company_when_provided(self, mock_frappe):
        """When company is provided, filters are applied."""
        mock_frappe.get_all.return_value = []
        get_min_wage_migration_alert_employees(company="Acme Sdn Bhd")
        call_str = str(mock_frappe.get_all.call_args)
        self.assertIn("Acme Sdn Bhd", call_str)

    @patch("lhdn_payroll_integration.utils.employment_compliance.frappe")
    def test_no_company_filter_when_not_provided(self, mock_frappe):
        """Without company argument, filters dict has no 'company' key."""
        mock_frappe.get_all.return_value = []
        get_min_wage_migration_alert_employees()
        mock_frappe.get_all.assert_called_once()
        call_kwargs = mock_frappe.get_all.call_args[1]
        filters = call_kwargs.get("filters", {})
        self.assertNotIn("company", filters)
