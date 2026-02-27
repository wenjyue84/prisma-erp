"""Tests for CP39 PCB Remittance script report.

Verifies output columns and data query shape.
"""
import frappe
from frappe.tests.utils import FrappeTestCase

from lhdn_payroll_integration.lhdn_payroll_integration.report.cp39_pcb_remittance.cp39_pcb_remittance import (
    execute,
    get_columns,
    get_data,
)

# Required fieldnames per acceptance criteria
REQUIRED_FIELDNAMES = {
    "employee_tin",
    "id_number",
    "employee_name",
    "gross_salary",
    "pcb_amount",
    "period",
}


class TestCP39ReportColumns(FrappeTestCase):
    """Tests for get_columns()."""

    def test_get_columns_returns_list(self):
        columns = get_columns()
        self.assertIsInstance(columns, list)

    def test_get_columns_minimum_count(self):
        """Must have at least 6 columns."""
        columns = get_columns()
        self.assertGreaterEqual(len(columns), 6)

    def test_get_columns_required_fieldnames(self):
        """All required fieldnames must be present."""
        columns = get_columns()
        fieldnames = {col.get("fieldname") for col in columns if isinstance(col, dict)}
        for required in REQUIRED_FIELDNAMES:
            self.assertIn(required, fieldnames, f"Missing fieldname: {required}")

    def test_get_columns_employee_tin_is_data(self):
        """employee_tin column must be Data type."""
        columns = get_columns()
        col_map = {c["fieldname"]: c for c in columns if isinstance(c, dict)}
        self.assertIn("employee_tin", col_map)
        self.assertEqual(col_map["employee_tin"]["fieldtype"], "Data")

    def test_get_columns_gross_salary_is_currency(self):
        """gross_salary column must be Currency type."""
        columns = get_columns()
        col_map = {c["fieldname"]: c for c in columns if isinstance(c, dict)}
        self.assertIn("gross_salary", col_map)
        self.assertEqual(col_map["gross_salary"]["fieldtype"], "Currency")

    def test_get_columns_pcb_amount_is_currency(self):
        """pcb_amount column must be Currency type."""
        columns = get_columns()
        col_map = {c["fieldname"]: c for c in columns if isinstance(c, dict)}
        self.assertIn("pcb_amount", col_map)
        self.assertEqual(col_map["pcb_amount"]["fieldtype"], "Currency")


class TestCP39ReportData(FrappeTestCase):
    """Tests for get_data()."""

    def test_get_data_returns_list(self):
        filters = frappe._dict({"month": "01", "year": 2026})
        result = get_data(filters)
        self.assertIsInstance(result, list)

    def test_get_data_no_filters_returns_list(self):
        result = get_data(frappe._dict())
        self.assertIsInstance(result, list)

    def test_get_data_rows_have_required_keys(self):
        """Rows must include all required keys."""
        filters = frappe._dict({"year": 2026})
        rows = get_data(filters)
        if not rows:
            self.skipTest("No submitted Salary Slips with PCB in test DB — shape test skipped")
        row = rows[0]
        for key in REQUIRED_FIELDNAMES:
            self.assertIn(key, row, f"Row missing key: {key}")

    def test_execute_returns_columns_and_data(self):
        """execute() must return (columns, data) tuple."""
        columns, data = execute(frappe._dict({"month": "01", "year": 2026}))
        self.assertIsInstance(columns, list)
        self.assertIsInstance(data, list)
        self.assertGreaterEqual(len(columns), 6)
