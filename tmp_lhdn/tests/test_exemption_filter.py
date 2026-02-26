"""Tests for exemption filter service — TDD Red Phase (UT-007).

Tests should_submit_to_lhdn() logic for Salary Slip and Expense Claim.
Will fail with ImportError until US-007 implements the service.
"""
import frappe
from frappe.tests.utils import FrappeTestCase
from unittest.mock import MagicMock, patch

from lhdn_payroll_integration.services.exemption_filter import should_submit_to_lhdn


class TestExemptionFilter(FrappeTestCase):
    """Test should_submit_to_lhdn(doctype, doc) filtering logic."""

    def _make_employee(self, requires_self_billed=0):
        """Create a mock employee with custom_requires_self_billed_invoice flag."""
        emp = MagicMock()
        emp.custom_requires_self_billed_invoice = requires_self_billed
        return emp

    def _make_salary_slip(self, employee_name="HR-EMP-00001", net_pay=5000):
        """Create a mock Salary Slip doc."""
        doc = MagicMock()
        doc.employee = employee_name
        doc.net_pay = net_pay
        return doc

    def _make_expense_claim(self, employee_name="HR-EMP-00001", category="Self-Billed Required"):
        """Create a mock Expense Claim doc."""
        doc = MagicMock()
        doc.employee = employee_name
        doc.custom_expense_category = category
        return doc

    @patch("lhdn_payroll_integration.services.exemption_filter.frappe")
    def test_salary_slip_excluded_when_flag_off(self, mock_frappe):
        """Salary Slip excluded when employee.custom_requires_self_billed_invoice = 0."""
        employee = self._make_employee(requires_self_billed=0)
        mock_frappe.get_doc.return_value = employee

        doc = self._make_salary_slip(net_pay=5000)
        result = should_submit_to_lhdn("Salary Slip", doc)

        self.assertFalse(result)

    @patch("lhdn_payroll_integration.services.exemption_filter.frappe")
    def test_salary_slip_included_when_flag_on_positive_pay(self, mock_frappe):
        """Salary Slip included when employee flag = 1 and net_pay > 0."""
        employee = self._make_employee(requires_self_billed=1)
        mock_frappe.get_doc.return_value = employee

        doc = self._make_salary_slip(net_pay=5000)
        result = should_submit_to_lhdn("Salary Slip", doc)

        self.assertTrue(result)

    @patch("lhdn_payroll_integration.services.exemption_filter.frappe")
    def test_salary_slip_excluded_when_zero_pay(self, mock_frappe):
        """Salary Slip excluded when net_pay <= 0, even if flag is on."""
        employee = self._make_employee(requires_self_billed=1)
        mock_frappe.get_doc.return_value = employee

        doc = self._make_salary_slip(net_pay=0)
        result = should_submit_to_lhdn("Salary Slip", doc)

        self.assertFalse(result)

    @patch("lhdn_payroll_integration.services.exemption_filter.frappe")
    def test_expense_claim_excluded_overseas_exempt(self, mock_frappe):
        """Expense Claim excluded when category is 'Overseas - Exempt'."""
        employee = self._make_employee(requires_self_billed=1)
        mock_frappe.get_doc.return_value = employee

        doc = self._make_expense_claim(category="Overseas - Exempt")
        result = should_submit_to_lhdn("Expense Claim", doc)

        self.assertFalse(result)

    @patch("lhdn_payroll_integration.services.exemption_filter.frappe")
    def test_expense_claim_excluded_employee_receipt_provided(self, mock_frappe):
        """Expense Claim excluded when category is 'Employee Receipt Provided'."""
        employee = self._make_employee(requires_self_billed=1)
        mock_frappe.get_doc.return_value = employee

        doc = self._make_expense_claim(category="Employee Receipt Provided")
        result = should_submit_to_lhdn("Expense Claim", doc)

        self.assertFalse(result)

    @patch("lhdn_payroll_integration.services.exemption_filter.frappe")
    def test_expense_claim_included_self_billed_required(self, mock_frappe):
        """Expense Claim included when category is 'Self-Billed Required' and employee flag set."""
        employee = self._make_employee(requires_self_billed=1)
        mock_frappe.get_doc.return_value = employee

        doc = self._make_expense_claim(category="Self-Billed Required")
        result = should_submit_to_lhdn("Expense Claim", doc)

        self.assertTrue(result)
