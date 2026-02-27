"""Tests for EIS Monthly Contribution Report Script Report.

US-017: Generate EIS monthly contribution report.

Acceptance criteria:
- New Script Report eis_monthly with filters: Company, Month, Year
- Columns: Employee Name, NRIC, Wages, EIS Employee, EIS Employer, Total
- Sources data from submitted Salary Slips with EIS deduction/earning lines
- Test verifies correct EIS amounts per employee
"""
import frappe
from frappe.tests.utils import FrappeTestCase

from lhdn_payroll_integration.lhdn_payroll_integration.report.eis_monthly.eis_monthly import (
    execute,
    get_columns,
    get_data,
)

REQUIRED_FIELDNAMES = {
    "employee",
    "employee_name",
    "nric",
    "wages",
    "eis_employee",
    "eis_employer",
    "total_eis",
}


class TestEISMonthlyColumns(FrappeTestCase):
    """Tests for get_columns()."""

    def test_get_columns_returns_list(self):
        columns = get_columns()
        self.assertIsInstance(columns, list)

    def test_get_columns_minimum_count(self):
        columns = get_columns()
        self.assertGreaterEqual(len(columns), 7)

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

    def test_total_eis_column_is_currency(self):
        columns = get_columns()
        total_col = next((c for c in columns if c.get("fieldname") == "total_eis"), None)
        self.assertIsNotNone(total_col, "total_eis column missing")
        self.assertEqual(total_col.get("fieldtype"), "Currency")


class TestEISMonthlyData(FrappeTestCase):
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

    def test_get_data_rows_have_total_eis(self):
        filters = frappe._dict({"company": "_Test Company", "year": 2026})
        rows = get_data(filters)
        for row in rows:
            expected = (row.get("eis_employee") or 0) + (row.get("eis_employer") or 0)
            self.assertAlmostEqual(
                row.get("total_eis", 0),
                expected,
                places=2,
                msg=f"total_eis mismatch for {row.get('employee_name')}",
            )

    def test_execute_returns_columns_and_data(self):
        columns, data = execute(frappe._dict({"company": "_Test Company", "year": 2026}))
        self.assertIsInstance(columns, list)
        self.assertIsInstance(data, list)
