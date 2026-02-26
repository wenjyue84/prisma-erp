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

    def _make_employee(self, requires_self_billed=0, worker_type="Contractor"):
        """Create a mock employee with custom_requires_self_billed_invoice flag."""
        emp = MagicMock()
        emp.custom_requires_self_billed_invoice = requires_self_billed
        emp.custom_worker_type = worker_type
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


def _import_get_default_classification_code():
    """Lazy import to avoid breaking existing tests if function doesn't exist yet."""
    from lhdn_payroll_integration.services.exemption_filter import get_default_classification_code
    return get_default_classification_code


class TestWorkerTypeGate(FrappeTestCase):
    """Test worker type gate: Employee vs Contractor vs Director.

    Verifies:
    - Regular employees always exempt regardless of flag
    - Contractors and directors in-scope when flag is set
    - Default classification codes differ by worker type
    - Unknown worker types default to exempt
    """

    def _make_employee(self, worker_type="Employee", requires_self_billed=1):
        emp = MagicMock()
        emp.custom_requires_self_billed_invoice = requires_self_billed
        emp.custom_worker_type = worker_type
        return emp

    def _make_salary_slip(self, net_pay=5000):
        doc = MagicMock()
        doc.employee = "HR-EMP-00001"
        doc.net_pay = net_pay
        return doc

    @patch("lhdn_payroll_integration.services.exemption_filter.frappe")
    def test_regular_employee_always_exempt_regardless_of_flag(self, mock_frappe):
        """Regular employee (custom_worker_type='Employee') is always exempt,
        even when custom_requires_self_billed_invoice=1."""
        employee = self._make_employee(worker_type="Employee", requires_self_billed=1)
        mock_frappe.get_doc.return_value = employee

        doc = self._make_salary_slip(net_pay=5000)
        result = should_submit_to_lhdn("Salary Slip", doc)

        self.assertFalse(result,
            "Regular employees must be exempt regardless of self-billed flag")

    @patch("lhdn_payroll_integration.services.exemption_filter.frappe")
    def test_contractor_with_flag_is_in_scope(self, mock_frappe):
        """Contractor with self-billed flag=1 should be in scope."""
        employee = self._make_employee(worker_type="Contractor", requires_self_billed=1)
        mock_frappe.get_doc.return_value = employee

        doc = self._make_salary_slip(net_pay=5000)
        result = should_submit_to_lhdn("Salary Slip", doc)

        self.assertTrue(result,
            "Contractors with self-billed flag must be in scope")

    @patch("lhdn_payroll_integration.services.exemption_filter.frappe")
    def test_director_with_flag_is_in_scope(self, mock_frappe):
        """Director with self-billed flag=1 should be in scope."""
        employee = self._make_employee(worker_type="Director", requires_self_billed=1)
        mock_frappe.get_doc.return_value = employee

        doc = self._make_salary_slip(net_pay=5000)
        result = should_submit_to_lhdn("Salary Slip", doc)

        self.assertTrue(result,
            "Directors with self-billed flag must be in scope")

    def test_director_default_classification_code_is_036(self):
        """Director default classification code should be '036'."""
        get_default_classification_code = _import_get_default_classification_code()
        result = get_default_classification_code("Director")
        self.assertEqual(result, "036",
            f"Director classification code should be '036', got '{result}'")

    def test_contractor_default_classification_code_is_037(self):
        """Contractor default classification code should be '037'."""
        get_default_classification_code = _import_get_default_classification_code()
        result = get_default_classification_code("Contractor")
        self.assertEqual(result, "037",
            f"Contractor classification code should be '037', got '{result}'")

    @patch("lhdn_payroll_integration.services.exemption_filter.frappe")
    def test_unknown_worker_type_defaults_to_exempt(self, mock_frappe):
        """Unknown worker type should default to exempt (return False)."""
        employee = self._make_employee(worker_type="Intern", requires_self_billed=1)
        mock_frappe.get_doc.return_value = employee

        doc = self._make_salary_slip(net_pay=5000)
        result = should_submit_to_lhdn("Salary Slip", doc)

        self.assertFalse(result,
            "Unknown worker types should default to exempt")
