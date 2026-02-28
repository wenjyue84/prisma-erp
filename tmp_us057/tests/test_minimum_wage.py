"""Tests for US-057: Minimum Wage Validation (RM1,700/month, Feb 2025 Amendment)."""

from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from lhdn_payroll_integration.utils.employment_compliance import (
    MINIMUM_WAGE_HOURLY,
    MINIMUM_WAGE_MONTHLY,
    check_minimum_wage,
)
from lhdn_payroll_integration.utils.validation import validate_document_for_lhdn


class TestMinimumWageConstants(FrappeTestCase):
    """Test that minimum wage constants are correct per the 2025 amendment."""

    def test_minimum_wage_monthly_is_1700(self):
        self.assertEqual(MINIMUM_WAGE_MONTHLY, 1700.0)

    def test_minimum_wage_hourly_is_8_17(self):
        self.assertAlmostEqual(MINIMUM_WAGE_HOURLY, 8.17, places=2)


class TestCheckMinimumWageFullTime(FrappeTestCase):
    """Test full-time and contract monthly salary checks."""

    def test_exact_minimum_wage_passes(self):
        result = check_minimum_wage(1700, employment_type="Full-time")
        self.assertTrue(result["compliant"])
        self.assertIsNone(result["warning"])

    def test_above_minimum_wage_passes(self):
        result = check_minimum_wage(2000, employment_type="Full-time")
        self.assertTrue(result["compliant"])
        self.assertIsNone(result["warning"])

    def test_below_minimum_wage_triggers_warning(self):
        result = check_minimum_wage(1699, employment_type="Full-time")
        self.assertFalse(result["compliant"])
        self.assertIsNotNone(result["warning"])
        self.assertIn("1699", result["warning"])
        self.assertIn("1700", result["warning"])

    def test_contract_below_minimum_triggers_warning(self):
        result = check_minimum_wage(1500, employment_type="Contract")
        self.assertFalse(result["compliant"])
        self.assertIsNotNone(result["warning"])

    def test_contract_at_minimum_passes(self):
        result = check_minimum_wage(1700, employment_type="Contract")
        self.assertTrue(result["compliant"])

    def test_default_employment_type_is_fulltime(self):
        result = check_minimum_wage(1700)
        self.assertEqual(result["employment_type"], "Full-time")
        self.assertTrue(result["compliant"])

    def test_result_contains_actual_salary(self):
        result = check_minimum_wage(1500, employment_type="Full-time")
        self.assertEqual(result["actual"], 1500.0)
        self.assertEqual(result["minimum"], MINIMUM_WAGE_MONTHLY)


class TestCheckMinimumWagePartTime(FrappeTestCase):
    """Test part-time hourly rate checks."""

    def test_part_time_hourly_at_minimum_passes(self):
        # 8.17/hour * 160 hours = 1307.20/month
        result = check_minimum_wage(
            monthly_salary=1307.20,
            employment_type="Part-time",
            contracted_hours=160,
        )
        self.assertTrue(result["compliant"])

    def test_part_time_hourly_above_minimum_passes(self):
        # 10/hour * 160 hours = 1600/month
        result = check_minimum_wage(
            monthly_salary=1600,
            employment_type="Part-time",
            contracted_hours=160,
        )
        self.assertTrue(result["compliant"])

    def test_part_time_hourly_below_minimum_triggers_warning(self):
        # 8.00/hour * 160 hours = 1280/month (below 8.17/hour)
        result = check_minimum_wage(
            monthly_salary=1280,
            employment_type="Part-time",
            contracted_hours=160,
        )
        self.assertFalse(result["compliant"])
        self.assertIsNotNone(result["warning"])
        self.assertIn("8.17", result["warning"])

    def test_part_time_no_contracted_hours_falls_back_to_monthly(self):
        # Without contracted_hours, falls back to monthly check
        result = check_minimum_wage(
            monthly_salary=1699,
            employment_type="Part-time",
            contracted_hours=None,
        )
        self.assertFalse(result["compliant"])

    def test_part_time_result_contains_hourly_rate(self):
        result = check_minimum_wage(
            monthly_salary=1600,
            employment_type="Part-time",
            contracted_hours=160,
        )
        self.assertAlmostEqual(result["actual"], 10.0, places=2)
        self.assertEqual(result["minimum"], MINIMUM_WAGE_HOURLY)


class TestValidateDocumentForLhdnSalarySlip(FrappeTestCase):
    """Test validate_document_for_lhdn() dispatches to minimum wage check for Salary Slip."""

    def _make_salary_slip(self, gross_pay, employee="EMP-0001"):
        doc = MagicMock()
        doc.get = lambda key, default=None: {
            "doctype": "Salary Slip",
            "base_gross_pay": gross_pay,
            "gross_pay": gross_pay,
            "employee": employee,
        }.get(key, default)
        doc.doctype = "Salary Slip"
        return doc

    @patch("lhdn_payroll_integration.utils.validation.frappe")
    @patch("lhdn_payroll_integration.utils.employment_compliance.frappe")
    def test_compliant_salary_no_msgprint(self, mock_emp_frappe, mock_val_frappe):
        mock_val_frappe.db.exists.return_value = True
        emp = MagicMock()
        emp.get = lambda key, default=None: {
            "custom_employment_type": "Full-time",
            "custom_contracted_hours_per_month": None,
        }.get(key, default)
        mock_val_frappe.get_cached_doc.return_value = emp

        doc = self._make_salary_slip(1700)
        validate_document_for_lhdn(doc)
        mock_val_frappe.msgprint.assert_not_called()

    @patch("lhdn_payroll_integration.utils.validation.frappe")
    @patch("lhdn_payroll_integration.utils.employment_compliance.frappe")
    def test_non_compliant_salary_triggers_msgprint(self, mock_emp_frappe, mock_val_frappe):
        mock_val_frappe.db.exists.return_value = True
        emp = MagicMock()
        emp.get = lambda key, default=None: {
            "custom_employment_type": "Full-time",
            "custom_contracted_hours_per_month": None,
        }.get(key, default)
        mock_val_frappe.get_cached_doc.return_value = emp

        doc = self._make_salary_slip(1699)
        validate_document_for_lhdn(doc)
        mock_val_frappe.msgprint.assert_called_once()
        call_kwargs = mock_val_frappe.msgprint.call_args
        self.assertIn("Minimum Wage", str(call_kwargs))

    @patch("lhdn_payroll_integration.utils.validation.frappe")
    def test_non_salary_slip_does_not_call_minimum_wage(self, mock_frappe):
        doc = MagicMock()
        doc.get = lambda key, default=None: {
            "doctype": "Employee",
            "custom_id_type": None,
            "custom_id_value": None,
        }.get(key, default)
        validate_document_for_lhdn(doc)
        mock_frappe.msgprint.assert_not_called()
