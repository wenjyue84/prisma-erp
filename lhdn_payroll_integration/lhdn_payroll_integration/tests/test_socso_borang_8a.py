"""Tests for SOCSO Borang 8A Script Report.

US-016: Generate SOCSO Borang 8A monthly contribution schedule.

Acceptance criteria:
- New Script Report socso_borang_8a with filters: Company, Month, Year
- Columns: Employee Name, NRIC, SOCSO Number, Wages,
           Employee SOCSO, Employer SOCSO, Total
- New field custom_socso_member_number (Data) on Employee
- Test verifies amounts sourced from SOCSO deduction lines
"""
import frappe
from frappe.tests.utils import FrappeTestCase

from lhdn_payroll_integration.lhdn_payroll_integration.report.socso_borang_8a.socso_borang_8a import (
    execute,
    get_columns,
    get_data,
)

REQUIRED_FIELDNAMES = {
    "employee",
    "employee_name",
    "nric",
    "socso_member_number",
    "wages",
    "employee_socso",
    "employer_socso",
    "total_socso",
}


class TestSOCSOBorang8AColumns(FrappeTestCase):
    """Tests for get_columns()."""

    def test_get_columns_returns_list(self):
        columns = get_columns()
        self.assertIsInstance(columns, list)

    def test_get_columns_minimum_count(self):
        columns = get_columns()
        self.assertGreaterEqual(len(columns), 8)

    def test_get_columns_required_fieldnames(self):
        columns = get_columns()
        fieldnames = {col["fieldname"] for col in columns if isinstance(col, dict)}
        for required in REQUIRED_FIELDNAMES:
            self.assertIn(required, fieldnames, f"Missing column: {required}")

    def test_wages_column_is_currency(self):
        columns = get_columns()
        wages_col = next((c for c in columns if c.get("fieldname") == "wages"), None)
        self.assertIsNotNone(wages_col, "wages column missing")
        self.assertEqual(wages_col.get("fieldtype"), "Currency")

    def test_total_socso_column_is_currency(self):
        columns = get_columns()
        total_col = next((c for c in columns if c.get("fieldname") == "total_socso"), None)
        self.assertIsNotNone(total_col, "total_socso column missing")
        self.assertEqual(total_col.get("fieldtype"), "Currency")


class TestSOCSOBorang8AData(FrappeTestCase):
    """Tests for get_data()."""

    def test_get_data_returns_list(self):
        filters = frappe._dict({"company": "_Test Company", "month": "01", "year": 2026})
        result = get_data(filters)
        self.assertIsInstance(result, list)

    def test_get_data_empty_for_distant_past(self):
        filters = frappe._dict({"company": "_Test Company", "month": "01", "year": 1900})
        result = get_data(filters)
        self.assertEqual(result, [])

    def test_get_data_none_filters(self):
        result = get_data(None)
        self.assertIsInstance(result, list)

    def test_get_data_rows_have_total_socso(self):
        filters = frappe._dict({"company": "_Test Company", "year": 2026})
        rows = get_data(filters)
        for row in rows:
            expected = (row.get("employee_socso") or 0) + (row.get("employer_socso") or 0)
            self.assertAlmostEqual(
                row.get("total_socso", 0),
                expected,
                places=2,
                msg=f"total_socso mismatch for {row.get('employee_name')}",
            )

    def test_execute_returns_columns_and_data(self):
        columns, data = execute(frappe._dict({"company": "_Test Company", "year": 2026}))
        self.assertIsInstance(columns, list)
        self.assertIsInstance(data, list)


class TestSOCSOMemberNumberField(FrappeTestCase):
    """Tests for custom_socso_member_number custom field on Employee."""

    def test_custom_socso_member_number_field_exists(self):
        exists = frappe.db.exists(
            "Custom Field", {"dt": "Employee", "fieldname": "custom_socso_member_number"}
        )
        self.assertTrue(exists, "Custom Field 'custom_socso_member_number' not found on Employee")

    def test_custom_socso_member_number_is_data_type(self):
        field = frappe.db.get_value(
            "Custom Field",
            {"dt": "Employee", "fieldname": "custom_socso_member_number"},
            "fieldtype",
        )
        self.assertEqual(field, "Data", "custom_socso_member_number should be fieldtype=Data")
