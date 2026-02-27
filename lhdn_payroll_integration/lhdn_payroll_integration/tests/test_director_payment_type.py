"""Tests for Director Fee vs Director Salary classification.

US-020: Distinguish director fee vs director salary at invoice level.

Acceptance criteria:
- New field custom_director_payment_type (Select: Director Salary/Director Fee)
  on Employee, visible only when custom_worker_type = Director
- get_default_classification_code() returns 036 for Director Fee,
  004 for Director Salary
- Test verifies correct classification codes per director payment type
"""
import frappe
from frappe.tests.utils import FrappeTestCase
from unittest.mock import MagicMock

from lhdn_payroll_integration.lhdn_payroll_integration.services.exemption_filter import (
    get_default_classification_code,
)


def _make_employee(worker_type="Director", director_payment_type=""):
    emp = MagicMock()
    emp.custom_worker_type = worker_type
    emp.custom_director_payment_type = director_payment_type
    return emp


class TestDirectorPaymentTypeClassification(FrappeTestCase):
    """Tests for get_default_classification_code() with director sub-type."""

    def test_director_fee_returns_036(self):
        """Director Fee should return classification code 036."""
        emp = _make_employee(worker_type="Director", director_payment_type="Director Fee")
        code = get_default_classification_code("Director", employee=emp)
        self.assertEqual(code, "036", "Director Fee must map to classification 036")

    def test_director_salary_returns_004(self):
        """Director Salary should return classification code 004."""
        emp = _make_employee(worker_type="Director", director_payment_type="Director Salary")
        code = get_default_classification_code("Director", employee=emp)
        self.assertEqual(code, "004", "Director Salary must map to classification 004")

    def test_director_no_subtype_defaults_to_036(self):
        """Director with no payment type set defaults to 036 (Director Fee)."""
        emp = _make_employee(worker_type="Director", director_payment_type="")
        code = get_default_classification_code("Director", employee=emp)
        self.assertEqual(code, "036", "Director with no subtype should default to 036")

    def test_director_without_employee_arg_defaults_to_036(self):
        """When employee is not passed, Director defaults to 036."""
        code = get_default_classification_code("Director")
        self.assertEqual(code, "036")

    def test_contractor_classification_unchanged(self):
        """Contractor still returns 037 regardless of employee arg."""
        code = get_default_classification_code("Contractor")
        self.assertEqual(code, "037")

    def test_employee_classification_returns_022(self):
        """Regular Employee returns 022 (Others)."""
        code = get_default_classification_code("Employee")
        self.assertEqual(code, "022")

    def test_unknown_worker_type_returns_022(self):
        """Unknown worker type returns 022."""
        code = get_default_classification_code("Unknown")
        self.assertEqual(code, "022")


class TestDirectorPaymentTypeCustomField(FrappeTestCase):
    """Tests for custom_director_payment_type custom field on Employee."""

    def test_custom_director_payment_type_field_exists(self):
        exists = frappe.db.exists(
            "Custom Field", {"dt": "Employee", "fieldname": "custom_director_payment_type"}
        )
        self.assertTrue(
            exists, "Custom Field 'custom_director_payment_type' not found on Employee"
        )

    def test_custom_director_payment_type_is_select(self):
        field = frappe.db.get_value(
            "Custom Field",
            {"dt": "Employee", "fieldname": "custom_director_payment_type"},
            "fieldtype",
        )
        self.assertEqual(field, "Select", "custom_director_payment_type should be fieldtype=Select")

    def test_custom_director_payment_type_options_include_both_values(self):
        options = frappe.db.get_value(
            "Custom Field",
            {"dt": "Employee", "fieldname": "custom_director_payment_type"},
            "options",
        )
        self.assertIn("Director Salary", options or "")
        self.assertIn("Director Fee", options or "")
