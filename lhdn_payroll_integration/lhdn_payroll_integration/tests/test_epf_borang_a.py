"""Tests for EPF Borang A Script Report.

US-015: Generate EPF Borang A monthly contribution schedule.

Acceptance criteria:
- New Script Report epf_borang_a with filters: Company, Month, Year
- Columns: Employee Name, NRIC, EPF Member Number, Wages,
           Employee EPF, Employer EPF, Total
- New field custom_epf_member_number (Data) on Employee
- CSV export compatible with EPF i-Akaun upload format
- Test verifies contribution amounts per employee
"""
import frappe
from frappe.tests.utils import FrappeTestCase

from lhdn_payroll_integration.lhdn_payroll_integration.report.epf_borang_a.epf_borang_a import (
    execute,
    get_columns,
    get_data,
)

REQUIRED_FIELDNAMES = {
    "employee",
    "employee_name",
    "nric",
    "epf_member_number",
    "wages",
    "employee_epf",
    "employer_epf",
    "total_epf",
}


class TestEPFBorangAColumns(FrappeTestCase):
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

    def test_total_epf_column_is_currency(self):
        columns = get_columns()
        total_col = next((c for c in columns if c.get("fieldname") == "total_epf"), None)
        self.assertIsNotNone(total_col, "total_epf column missing")
        self.assertEqual(total_col.get("fieldtype"), "Currency")


class TestEPFBorangAData(FrappeTestCase):
    """Tests for get_data()."""

    def test_get_data_returns_list(self):
        filters = frappe._dict({"company": "_Test Company", "month": "01", "year": 2026})
        result = get_data(filters)
        self.assertIsInstance(result, list)

    def test_get_data_empty_for_distant_past(self):
        """Returns empty list when no salary slips exist for given period."""
        filters = frappe._dict({"company": "_Test Company", "month": "01", "year": 1900})
        result = get_data(filters)
        self.assertEqual(result, [])

    def test_get_data_none_filters(self):
        """Accepts None filters without raising."""
        result = get_data(None)
        self.assertIsInstance(result, list)

    def test_get_data_rows_have_total_epf(self):
        """Each returned row has total_epf = employee_epf + employer_epf."""
        filters = frappe._dict({"company": "_Test Company", "year": 2026})
        rows = get_data(filters)
        for row in rows:
            expected = (row.get("employee_epf") or 0) + (row.get("employer_epf") or 0)
            self.assertAlmostEqual(
                row.get("total_epf", 0),
                expected,
                places=2,
                msg=f"total_epf mismatch for {row.get('employee_name')}",
            )

    def test_execute_returns_columns_and_data(self):
        """execute() returns a 2-tuple of (columns, data)."""
        columns, data = execute(frappe._dict({"company": "_Test Company", "year": 2026}))
        self.assertIsInstance(columns, list)
        self.assertIsInstance(data, list)


class TestEPFMemberNumberField(FrappeTestCase):
    """Tests for custom_epf_member_number custom field on Employee."""

    def test_custom_epf_member_number_field_exists(self):
        """custom_epf_member_number must be registered as a Custom Field on Employee."""
        exists = frappe.db.exists(
            "Custom Field", {"dt": "Employee", "fieldname": "custom_epf_member_number"}
        )
        self.assertTrue(exists, "Custom Field 'custom_epf_member_number' not found on Employee")

    def test_custom_epf_member_number_is_data_type(self):
        """Field type must be Data."""
        field = frappe.db.get_value(
            "Custom Field",
            {"dt": "Employee", "fieldname": "custom_epf_member_number"},
            "fieldtype",
        )
        self.assertEqual(field, "Data", "custom_epf_member_number should be fieldtype=Data")
